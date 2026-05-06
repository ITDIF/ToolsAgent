import pytest
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
    def test_max_iterations_fallback(self):
        responses = [
            {"content": "", "tool_calls": [{"id": f"t{i}", "name": "list_files", "arguments": {"path": "."}}]}
            for i in range(10)
        ]
        provider = MockProvider(responses=responses, final_chat="fallback")
        agent = FileAgent(provider)
        agent.config["max_tool_iterations"] = 2
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
