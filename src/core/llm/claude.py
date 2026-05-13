import os
import json
import anthropic
from typing import Dict, Any, List, Optional

from .base import BaseLLMProvider
from ...infra.constants import LLMConstants
from ...infra.utils import sanitize_for_json


class ClaudeProvider(BaseLLMProvider):
    """Claude API Provider"""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-6"):
        super().__init__()
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.client = anthropic.Anthropic(api_key=self.api_key, max_retries=self.max_retries, timeout=self.timeout)

    def build_assistant_message(self, content: Optional[str], tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Anthropic: assistant 消息 content 是 block 数组,工具调用以 tool_use block 表达

        Args:
            content: 助手回复内容
            tool_calls: 工具调用列表

        Returns:
            Anthropic 格式的消息列表
        """
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

    def build_tool_result_messages(self, tool_results: List[tuple[Dict[str, Any], Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Anthropic: 工具结果作为 user 消息中的 tool_result block 数组返回

        Args:
            tool_results: [(tool_call_dict, result_dict), ...]

        Returns:
            Anthropic 格式的消息列表
        """
        if not tool_results:
            return []
        blocks = [
            {
                "type": "tool_result",
                "tool_use_id": tc["id"],
                "content": json.dumps(sanitize_for_json(result), ensure_ascii=False),
            }
            for tc, result in tool_results
        ]
        return [{"role": "user", "content": blocks}]

    def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        params = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "max_tokens": LLMConstants.MAX_TOKENS,
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

    def chat_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        update_tokens_callback: Optional[Any] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        params = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "max_tokens": LLMConstants.MAX_TOKENS,
        }
        if system_prompt:
            params["system"] = system_prompt

        # 使用流式 API
        with self.client.messages.stream(**params) as stream:
            result = {
                "content": "",
                "tool_calls": []
            }

            last_input_tokens = 0
            last_output_tokens = 0
            final_input_tokens = 0
            final_output_tokens = 0

            for event in stream:
                # 处理不同类型的事件
                if hasattr(event, 'type'):
                    if event.type == 'message_delta':
                        # 消息增量事件，包含 usage 信息
                        if hasattr(event, 'usage') and event.usage:
                            # 同时获取输入和输出 token
                            if hasattr(event.usage, 'input_tokens'):
                                final_input_tokens = event.usage.input_tokens
                            if hasattr(event.usage, 'output_tokens'):
                                final_output_tokens = event.usage.output_tokens

                            if update_tokens_callback:
                                # 使用差值更新
                                input_delta = final_input_tokens - last_input_tokens
                                output_delta = final_output_tokens - last_output_tokens
                                if input_delta > 0 or output_delta > 0:
                                    update_tokens_callback(input_delta, output_delta)
                                last_input_tokens = final_input_tokens
                                last_output_tokens = final_output_tokens

            # 获取完整响应以获取准确的 token 统计
            response = stream.get_final_message()

        # 流式结束时，使用最终的 token 数量更新统计
        if update_tokens_callback and (last_input_tokens > 0 or last_output_tokens > 0):
            self._update_token_usage(last_input_tokens, last_output_tokens)

        # 直接使用 response.usage 的内容构建结果

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
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": LLMConstants.MAX_TOKENS,
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

        return {"content": response.content[0].text if response.content else "", "reasoning_content": None}

    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        update_tokens_callback: Optional[Any] = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        params = {
            "model": self.model,
            "messages": messages,
            "max_tokens": LLMConstants.MAX_TOKENS,
        }
        if system_prompt:
            params["system"] = system_prompt

        # 使用流式 API
        with self.client.messages.stream(**params) as stream:
            content = ""
            last_input_tokens = 0
            last_output_tokens = 0
            final_input_tokens = 0
            final_output_tokens = 0

            for event in stream:
                # 处理不同类型的事件
                if hasattr(event, 'type'):
                    if event.type == 'content_block_delta':
                        # 收集文本内容
                        if hasattr(event, 'delta') and hasattr(event.delta, 'type'):
                            if event.delta.type == 'text_delta':
                                text = getattr(event.delta, 'text', '')
                                content += text
                    elif event.type == 'message_delta':
                        # 消息增量事件，包含 usage 信息
                        if hasattr(event, 'usage') and event.usage:
                            # 同时获取输入和输出 token
                            if hasattr(event.usage, 'input_tokens'):
                                final_input_tokens = event.usage.input_tokens
                            if hasattr(event.usage, 'output_tokens'):
                                final_output_tokens = event.usage.output_tokens

                            if update_tokens_callback:
                                # 使用差值更新
                                input_delta = final_input_tokens - last_input_tokens
                                output_delta = final_output_tokens - last_output_tokens
                                if input_delta > 0 or output_delta > 0:
                                    update_tokens_callback(input_delta, output_delta)
                                last_input_tokens = final_input_tokens
                                last_output_tokens = final_output_tokens

            # 获取完整响应以获取准确的 token 统计
            response = stream.get_final_message()

        # 流式结束时，使用最终的 token 数量更新统计
        if update_tokens_callback and (last_input_tokens > 0 or last_output_tokens > 0):
            self._update_token_usage(last_input_tokens, last_output_tokens)

        final_content = response.content[0].text if response.content else content
        return {"content": final_content, "reasoning_content": None}
