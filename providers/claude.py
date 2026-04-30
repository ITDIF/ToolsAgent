
import os
import anthropic

from .base import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):
    """Claude API Provider"""

    def __init__(self, api_key=None, model="claude-3-5-sonnet-20241022"):
        super().__init__()
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def chat_with_tools(
        self,
        messages,
        tools,
        system_prompt=None,
        **kwargs
    ):
        params = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "max_tokens": 4096,
        }
        if system_prompt:
            params["system"] = system_prompt

        response = self.client.messages.create(**params)

        # 统计 token
        if response.usage:
            self._update_token_usage(
                response.usage.input_tokens,
                response.usage.output_tokens
            )

        result = {
            "content": "",
            "tool_calls": []
        }

        for block in response.content:
            if block.type == "text":
                result["content"] += block.text
            elif block.type == "tool_use":
                result["tool_calls"].append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input
                })

        return result

    def chat(
        self,
        messages,
        system_prompt=None,
        **kwargs
    ):
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
        }
        if system_prompt:
            params["system"] = system_prompt

        response = self.client.messages.create(**params)

        # 统计 token
        if response.usage:
            self._update_token_usage(
                response.usage.input_tokens,
                response.usage.output_tokens
            )

        return response.content[0].text if response.content else ""

