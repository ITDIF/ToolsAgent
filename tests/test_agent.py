import pytest
from src.core import agent as agent_module
from src.core.agent import FileAgent
from src.core.llm.base import BaseLLMProvider


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
        return {"content": self.final_chat, "reasoning_content": None}


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
        monkeypatch.setattr(agent_module, "select_option", lambda *a, **kw: 2)
        provider = MockProvider(responses=[
            {"content": "", "tool_calls": [{"id": "t1", "name": "delete_file", "arguments": {"path": "/tmp/dummy.txt"}}]},
            {"content": "cancelled", "tool_calls": []},
        ])
        agent = FileAgent(provider)
        result = agent.process("delete it", confirm_required=True)
        assert result == "cancelled"

    def test_confirm_esc_cancels(self, monkeypatch):
        # ESC/Ctrl+C 让 select_option 返回 None,效果同选 "取消"
        monkeypatch.setattr(agent_module, "select_option", lambda *a, **kw: None)
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
        from src.infra.config import get_config
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
        from src.infra.config import get_config
        agent = self._agent()
        monkeypatch.setattr(agent_module, "get_config", lambda: {"confirm_delete": True, "confirm_overwrite": True})
        ops = [
            {"tool": "create_file", "arguments": {"path": "/tmp/a"}},
            {"tool": "delete_file", "arguments": {"path": "/tmp/b"}},
        ]
        assert agent._need_confirm("batch_operations", {"operations": ops}) is True

    def test_batch_without_sensitive_ops_no_confirm(self, monkeypatch):
        from src.infra.config import get_config
        agent = self._agent()
        monkeypatch.setattr(agent_module, "get_config", lambda: {"confirm_delete": True, "confirm_overwrite": True})
        ops = [
            {"tool": "create_file", "arguments": {"path": "/tmp/a"}},
            {"tool": "create_folder", "arguments": {"path": "/tmp/b"}},
        ]
        assert agent._need_confirm("batch_operations", {"operations": ops}) is False

    def test_batch_with_overwrite_respects_config(self, monkeypatch):
        from src.infra.config import get_config
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


class TestSessionAuthorization:
    """会话级工具授权"""

    DEFAULT_CFG = {
        "confirm_delete": True,
        "confirm_overwrite": True,
        "max_tool_iterations": 8,
        "max_request_time": 300,
        "tool_timeout": 30,
    }

    def _patch_common(self, monkeypatch, cfg=None):
        from src.infra.config import get_config
        from src.infra.utils import log_action
        monkeypatch.setattr(agent_module, "get_config", lambda: cfg or self.DEFAULT_CFG)
        monkeypatch.setattr(agent_module, "log_action", lambda *a, **kw: None)

    def _patch_tool(self, monkeypatch, name, fn=None):
        fn = fn or (lambda **kw: {"success": True, "message": "ok"})
        monkeypatch.setattr(agent_module, "TOOL_REGISTRY", {name: fn})

    def test_is_session_authorized_normal(self):
        agent = FileAgent(MockProvider())
        agent.session_authorized_tools.add("delete_file")
        assert agent._is_session_authorized("delete_file", {"path": "/tmp/x"}) is True
        assert agent._is_session_authorized("write_file", {"path": "/tmp/x", "content": ""}) is False

    def test_is_session_authorized_batch_partial(self, monkeypatch):
        self._patch_common(monkeypatch)
        agent = FileAgent(MockProvider())
        agent.session_authorized_tools.add("delete_file")
        ops = [
            {"tool": "delete_file", "arguments": {"path": "/tmp/a"}},
            {"tool": "write_file", "arguments": {"path": "/tmp/b", "content": "x"}},
        ]
        # 只授权了 delete_file,batch 整体仍未完全授权
        assert agent._is_session_authorized("batch_operations", {"operations": ops}) is False
        agent.session_authorized_tools.add("write_file")
        assert agent._is_session_authorized("batch_operations", {"operations": ops}) is True

    def test_is_session_authorized_batch_only_safe_subops(self, monkeypatch):
        """batch 内全是不需要确认的子工具时,即使授权集为空也视为已授权"""
        self._patch_common(monkeypatch)
        agent = FileAgent(MockProvider())
        ops = [
            {"tool": "create_folder", "arguments": {"path": "/tmp/a"}},
            {"tool": "create_file", "arguments": {"path": "/tmp/b"}},
        ]
        assert agent._is_session_authorized("batch_operations", {"operations": ops}) is True

    def test_y_does_not_persist(self, monkeypatch):
        self._patch_common(monkeypatch)
        self._patch_tool(monkeypatch, "delete_file")
        # 0 = 本次允许
        monkeypatch.setattr(agent_module, "select_option", lambda *a, **kw: 0)

        provider = MockProvider(responses=[
            {"content": "", "tool_calls": [
                {"id": "t1", "name": "delete_file", "arguments": {"path": "/tmp/x"}}
            ]},
            {"content": "done", "tool_calls": []},
        ])
        agent = FileAgent(provider, interactive=False)
        agent.process("delete x", confirm_required=True)
        assert "delete_file" not in agent.session_authorized_tools

    def test_a_persists_across_requests(self, monkeypatch):
        self._patch_common(monkeypatch)
        self._patch_tool(monkeypatch, "delete_file")
        # select_option 仅会被消费一次 (1=本次会话允许);若第二次请求又问就会 StopIteration
        choices = iter([1])
        monkeypatch.setattr(agent_module, "select_option", lambda *a, **kw: next(choices))

        provider = MockProvider(responses=[
            {"content": "", "tool_calls": [
                {"id": "t1", "name": "delete_file", "arguments": {"path": "/tmp/x"}}
            ]},
            {"content": "done", "tool_calls": []},
            {"content": "", "tool_calls": [
                {"id": "t2", "name": "delete_file", "arguments": {"path": "/tmp/y"}}
            ]},
            {"content": "done", "tool_calls": []},
        ])
        agent = FileAgent(provider, interactive=False)
        agent.process("delete x", confirm_required=True)
        assert "delete_file" in agent.session_authorized_tools

        # 第二次请求,不应触发 select_option
        agent.process("delete y", confirm_required=True)
        assert "delete_file" in agent.session_authorized_tools

    def test_batch_a_authorizes_sub_tools(self, monkeypatch):
        self._patch_common(monkeypatch)
        self._patch_tool(monkeypatch, "batch_operations")
        # 1 = 本次会话允许
        monkeypatch.setattr(agent_module, "select_option", lambda *a, **kw: 1)

        ops = [
            {"tool": "delete_file", "arguments": {"path": "/tmp/a"}},
            {"tool": "write_file", "arguments": {"path": "/tmp/b", "content": "x"}},
            {"tool": "create_folder", "arguments": {"path": "/tmp/c"}},
        ]
        provider = MockProvider(responses=[
            {"content": "", "tool_calls": [
                {"id": "t1", "name": "batch_operations", "arguments": {"operations": ops}}
            ]},
            {"content": "done", "tool_calls": []},
        ])
        agent = FileAgent(provider, interactive=False)
        agent.process("organize", confirm_required=True)
        assert "delete_file" in agent.session_authorized_tools
        assert "write_file" in agent.session_authorized_tools
        # create_folder 本身不需确认,不应被加入授权集
        assert "create_folder" not in agent.session_authorized_tools

    def test_set_session_keeps_authorization(self):
        agent = FileAgent(MockProvider())
        agent.session_authorized_tools.add("delete_file")
        agent.set_session("another_session")
        assert "delete_file" in agent.session_authorized_tools

    def test_revoke_clears_all(self):
        agent = FileAgent(MockProvider())
        agent.session_authorized_tools.update({"delete_file", "write_file"})
        n = agent.revoke_session_authorizations()
        assert n == 2
        assert agent.session_authorized_tools == set()
        # 再次 revoke 返回 0
        assert agent.revoke_session_authorizations() == 0
