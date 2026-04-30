
import pytest
from providers.base import BaseLLMProvider, OpenAICompatibleProvider


class TestBaseLLMProvider:
    def test_init_token_usage(self):
        class TestProvider(BaseLLMProvider):
            def chat_with_tools(self, messages, tools, system_prompt=None, **kwargs):
                return {"content": "", "tool_calls": []}

            def chat(self, messages, system_prompt=None, **kwargs):
                return ""

        p = TestProvider()
        assert p.get_token_usage() == {"input": 0, "output": 0, "total": 0}

    def test_update_token_usage(self):
        class TestProvider(BaseLLMProvider):
            def chat_with_tools(self, messages, tools, system_prompt=None, **kwargs):
                return {"content": "", "tool_calls": []}

            def chat(self, messages, system_prompt=None, **kwargs):
                return ""

        p = TestProvider()
        p._update_token_usage(100, 50)
        usage = p.get_token_usage()
        assert usage["input"] == 100
        assert usage["output"] == 50
        assert usage["total"] == 150

        p._update_token_usage(200, 100)
        usage = p.get_token_usage()
        assert usage["input"] == 300
        assert usage["output"] == 150
        assert usage["total"] == 450

    def test_reset_token_usage(self):
        class TestProvider(BaseLLMProvider):
            def chat_with_tools(self, messages, tools, system_prompt=None, **kwargs):
                return {"content": "", "tool_calls": []}

            def chat(self, messages, system_prompt=None, **kwargs):
                return ""

        p = TestProvider()
        p._update_token_usage(100, 50)
        p.reset_token_usage()
        assert p.get_token_usage() == {"input": 0, "output": 0, "total": 0}
