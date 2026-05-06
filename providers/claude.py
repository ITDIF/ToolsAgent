
import os
import json
import anthropic

from .base import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):
    """Claude API Provider"""

    def __init__(self, api_key=None, model="claude-sonnet-4-6"):
        super().__init__()
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.client = anthropic.Anthropic(api_key=self.api_key, max_retries=self.max_retries, timeout=self.timeout)

    def build_assistant_message(self, content, tool_calls):
        """Anthropic: assistant 消息 content 是 block 数组,工具调用以 tool_use block 表达"""
        blocks = []
        if content:
            blocks.append({"type": "text", "text": content})
        for tc in tool_calls or []:
            blocks.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["arguments"],
            })
        if not blocks:
            return []
        return [{"role": "assistant", "content": blocks}]

    def build_tool_result_messages(self, tool_results):
        """Anthropic: 工具结果作为 user 消息中的 tool_result block 数组返回"""
        if not tool_results:
            return []
        blocks = [
            {
                "type": "tool_result",
                "tool_use_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            }
            for tc, result in tool_results
        ]
        return [{"role": "user", "content": blocks}]

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

