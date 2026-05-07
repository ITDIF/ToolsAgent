import pytest
import agent as agent_module
from agent import FileAgent
from providers.base import BaseLLMProvider


class MockProvider(BaseLLMProvider):
    """用于测试的 mock LLM Provider"""

    def __init__(self, responses=None, final_chat="final"):
        super().__init__()
        self.responses = responses or []
        self.final_chat = final_chat
        self.call_count = 0

    def chat_with_tools(self, messages, tools, system_prompt=None, **kwargs):
        if self.call_count >= len(self.responses):
            return {"content": self.final_chat, "tool_calls": []}
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp

    def chat(self, messages, system_prompt=None, **kwargs):
        return self.final_chat


class TestProcessSingleTurn:
    def test_no_tool_call(self):
        provider = MockProvider(responses=[{"content": "hello", "tool_calls": []}])
        agent = FileAgent(provider)
        result = agent.process("hi", confirm_required=False)
        assert result == "hello"
        assert len(agent.messages) == 2  # user + assistant (system 不存入 messages)


class TestProcessMultiTurn:
    def test_tool_call_then_answer(self):
        provider = MockProvider(responses=[
            {"content": "", "tool_calls": [{"id": "t1", "name": "list_files", "arguments": {"path": "."}}]},
            {"content": "done", "tool_calls": []},
        ])
        agent = FileAgent(provider)
        result = agent.process("list files", confirm_required=False)
        assert result == "done"
        assert provider.call_count == 2


class TestConfirm:
    def test_confirm_reject(self, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "n")
        provider = MockProvider(responses=[
            {"content": "", "tool_calls": [{"id": "t1", "name": "delete_file", "arguments": {"path": "/tmp/dummy.txt"}}]},
            {"content": "cancelled", "tool_calls": []},
        ])
        agent = FileAgent(provider)
        result = agent.process("delete it", confirm_required=True)
        assert result == "cancelled"


class TestMaxIterations:
    def test_max_iterations_fallback(self, monkeypatch):
        responses = [
            {"content": "", "tool_calls": [{"id": f"t{i}", "name": "list_files", "arguments": {"path": "."}}]}
            for i in range(10)
        ]
        provider = MockProvider(responses=responses, final_chat="fallback")
        agent = FileAgent(provider)
        monkeypatch.setattr(agent_module, "get_config", lambda: {"max_tool_iterations": 2})
        result = agent.process("loop", confirm_required=False)
        assert result == "fallback"


class TestTokenUsage:
    def test_token_usage_accumulates(self):
        provider = MockProvider(responses=[{"content": "ok", "tool_calls": []}])
        provider._update_token_usage(10, 5)
        agent = FileAgent(provider)
        agent.process("test", confirm_required=False)
        usage = agent.get_token_usage()
        assert usage["input"] == 10
        assert usage["output"] == 5
        assert usage["total"] == 15


class TestNeedConfirmBatch:
    def _agent(self):
        return FileAgent(MockProvider())

    def test_batch_with_delete_needs_confirm(self, monkeypatch):
        agent = self._agent()
        monkeypatch.setattr(agent_module, "get_config", lambda: {"confirm_delete": True, "confirm_overwrite": True})
        ops = [
            {"tool": "create_file", "arguments": {"path": "/tmp/a"}},
            {"tool": "delete_file", "arguments": {"path": "/tmp/b"}},
        ]
        assert agent._need_confirm("batch_operations", {"operations": ops}) is True

    def test_batch_without_sensitive_ops_no_confirm(self, monkeypatch):
        agent = self._agent()
        monkeypatch.setattr(agent_module, "get_config", lambda: {"confirm_delete": True, "confirm_overwrite": True})
        ops = [
            {"tool": "create_file", "arguments": {"path": "/tmp/a"}},
            {"tool": "create_folder", "arguments": {"path": "/tmp/b"}},
        ]
        assert agent._need_confirm("batch_operations", {"operations": ops}) is False

    def test_batch_with_overwrite_respects_config(self, monkeypatch):
        agent = self._agent()
        monkeypatch.setattr(agent_module, "get_config", lambda: {"confirm_delete": True, "confirm_overwrite": False})
        ops = [
            {"tool": "write_file", "arguments": {"path": "/tmp/a", "content": "x"}},
        ]
        assert agent._need_confirm("batch_operations", {"operations": ops}) is False
        monkeypatch.setattr(agent_module, "get_config", lambda: {"confirm_delete": True, "confirm_overwrite": True})
        assert agent._need_confirm("batch_operations", {"operations": ops}) is True


class TestFormatToolCall:
    def test_format_undo_with_count(self):
        agent = FileAgent(MockProvider())
        assert agent._format_tool_call("undo_last", {}) == "撤销最后一次操作"
        assert "3" in agent._format_tool_call("undo_last", {"count": 3})

    def test_format_batch_preview(self):
        agent = FileAgent(MockProvider())
        ops = [
            {"tool": "create_file", "arguments": {"path": "/tmp/a"}},
            {"tool": "delete_file", "arguments": {"path": "/tmp/b"}},
        ]
        desc = agent._format_tool_call("batch_operations", {"operations": ops, "label": "整理"})
        assert "整理" in desc
        assert "/tmp/a" in desc
        assert "/tmp/b" in desc

    def test_format_batch_truncates(self):
        agent = FileAgent(MockProvider())
        ops = [
            {"tool": "create_file", "arguments": {"path": f"/tmp/f{i}.txt"}}
            for i in range(10)
        ]
        desc = agent._format_tool_call("batch_operations", {"operations": ops})
        assert "10" in desc
        assert "省略" in desc
