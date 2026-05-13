import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from ...infra.constants import LLMConstants
from ...infra.utils import sanitize_for_json


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(self):
        self.token_usage: Dict[str, int] = {"input": 0, "output": 0, "total": 0}
        self.max_retries: int = LLMConstants.MAX_RETRIES
        self.timeout: float = LLMConstants.TIMEOUT

    def reset_token_usage(self) -> None:
        """重置 token 计数"""
        self.token_usage = {"input": 0, "output": 0, "total": 0}

    def get_token_usage(self) -> Dict[str, int]:
        """获取 token 使用统计

        Returns:
            {"input": int, "output": int, "total": int}
        """
        return self.token_usage.copy()

    def _update_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        """更新 token 计数

        Args:
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
        """
        self.token_usage["input"] += input_tokens
        self.token_usage["output"] += output_tokens
        self.token_usage["total"] += input_tokens + output_tokens

    def build_assistant_message(self, content: Optional[str], tool_calls: List[Dict[str, Any]], reasoning_content: Optional[str] = None) -> List[Dict[str, Any]]:
        """构造一轮 assistant 消息(默认 OpenAI 风格)。返回应 extend 到对话历史的消息列表。

        Args:
            content: 助手回复内容
            tool_calls: 工具调用列表
            reasoning_content: 思考模式模型的推理内容（如 MIMO）

        Returns:
            消息列表
        """
        msg = {"role": "assistant", "content": content or None}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(sanitize_for_json(tc["arguments"]), ensure_ascii=False),
                    },
                }
                for tc in tool_calls
            ]
        return [msg]

    def build_tool_result_messages(self, tool_results: List[tuple[Dict[str, Any], Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """
        构造工具结果消息(默认 OpenAI 风格)。

        Args:
            tool_results: [(tool_call_dict, result_dict), ...]

        Returns:
            list of message dicts to extend into history
        """
        return [
            {
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(sanitize_for_json(result), ensure_ascii=False),
            }
            for tc, result in tool_results
        ]

    @abstractmethod
    def chat_with_tools(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            **kwargs: Any
    ) -> Dict[str, Any]:
        """
        与LLM对话，支持工具调用

        Args:
            messages: 对话历史 [{"role": "user", "content": "..."}]
            tools: 工具定义列表
            system_prompt: 系统提示词
            **kwargs: 其他参数

        Returns:
            {
                "content": "回复内容",
                "tool_calls": [{"name": "...", "arguments": {...}}]
            }
        """
        pass

    def chat_with_tools_stream(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            update_tokens_callback: Optional[Any] = None,
            **kwargs: Any
    ) -> Dict[str, Any]:
        """
        流式调用 chat_with_tools，实时更新 token 统计（可选实现）

        Args:
            messages: 对话历史
            tools: 工具定义列表
            system_prompt: 系统提示词
            update_tokens_callback: token 更新回调函数 callback(input_tokens, output_tokens)
            **kwargs: 其他参数

        Returns:
            {
                "content": "回复内容",
                "tool_calls": [{"name": "...", "arguments": {...}}]
            }
        """
        # 默认回退到非流式调用
        return self.chat_with_tools(messages, tools, system_prompt, **kwargs)

    @abstractmethod
    def chat(
            self,
            messages: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            **kwargs: Any
    ) -> Dict[str, Any]:
        """
        普通对话，不使用工具

        Args:
            messages: 对话历史
            system_prompt: 系统提示词
            **kwargs: 其他参数

        Returns:
            {"content": str, "reasoning_content": Optional[str]}
        """

    def chat_stream(
            self,
            messages: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            update_tokens_callback: Optional[Any] = None,
            **kwargs: Any
    ) -> Dict[str, Any]:
        """
        流式调用 chat，实时更新 token 统计（可选实现）

        Args:
            messages: 对话历史
            system_prompt: 系统提示词
            update_tokens_callback: token 更新回调函数 callback(input_tokens, output_tokens)
            **kwargs: 其他参数

        Returns:
            {"content": str, "reasoning_content": Optional[str]}
        """
        # 默认回退到非流式调用
        return self.chat(messages, system_prompt, **kwargs)
        pass


class OpenAICompatibleProvider(BaseLLMProvider):
    """OpenAI 兼容 API Provider 基类"""

    def __init__(self, api_key: str, base_url: str, model: str):
        from openai import OpenAI
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url, max_retries=self.max_retries, timeout=self.timeout)

    def chat_with_tools(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            **kwargs: Any
    ) -> Dict[str, Any]:
        return self.chat_with_tools_stream(messages, tools, system_prompt, **kwargs)

    def chat_with_tools_stream(
            self,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            update_tokens_callback: Optional[Any] = None,
            **kwargs: Any
    ) -> Dict[str, Any]:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"]
                }
            }
            for tool in tools
        ]

        final_messages: List[Dict[str, Any]] = []
        if system_prompt:
            final_messages.append({"role": "system", "content": system_prompt})
        final_messages.extend(messages)

        # 使用流式 API
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=final_messages,
            tools=openai_tools if openai_tools else None,
            stream=True,
            **kwargs
        )

        result = {"content": "", "tool_calls": []}
        current_tool_calls = {}  # id -> {name, arguments}
        last_output_tokens = 0

        for chunk in stream:
            if hasattr(chunk, 'usage') and chunk.usage:
                if update_tokens_callback and chunk.usage.completion_tokens > last_output_tokens:
                    delta = chunk.usage.completion_tokens - last_output_tokens
                    update_tokens_callback(0, delta)
                    last_output_tokens = chunk.usage.completion_tokens

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # 处理文本内容
            if hasattr(delta, 'content') and delta.content:
                result["content"] += delta.content
                if update_tokens_callback:
                    # 估计文本 token 数（大约每 4 字符 1 token）
                    estimated_tokens = len(delta.content) // 4 + 1
                    update_tokens_callback(0, estimated_tokens)

            # 保留 reasoning_content（思考模式模型如 MIMO 需要传回此字段）
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                result["reasoning_content"] = delta.reasoning_content
                if update_tokens_callback:
                    # 估计 reasoning token 数
                    estimated_tokens = len(delta.reasoning_content) // 4 + 1
                    update_tokens_callback(0, estimated_tokens)

            # 处理工具调用
            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                for tc in delta.tool_calls:
                    tc_id = tc.id
                    if tc_id not in current_tool_calls:
                        current_tool_calls[tc_id] = {"id": tc_id, "name": None, "arguments": ""}

                    if hasattr(tc, 'function'):
                        if hasattr(tc.function, 'name') and tc.function.name:
                            current_tool_calls[tc_id]["name"] = tc.function.name
                        if hasattr(tc.function, 'arguments') and tc.function.arguments:
                            current_tool_calls[tc_id]["arguments"] += tc.function.arguments

        # 构建最终的工具调用列表
        for tc in current_tool_calls.values():
            result["tool_calls"].append({
                "id": tc["id"],
                "name": tc["name"],
                "arguments": json.loads(tc["arguments"]) if tc["arguments"] else {}
            })

        # 重新调用一次非流式获取准确的 token 统计
        response = self.client.chat.completions.create(
            model=self.model,
            messages=final_messages,
            tools=openai_tools if openai_tools else None,
            **kwargs
        )

        # 统计 token
        if response.usage:
            self._update_token_usage(
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )

        return result

    def chat(
            self,
            messages: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            **kwargs: Any
    ) -> str:
        return self.chat_stream(messages, system_prompt, **kwargs)

    def chat_stream(
            self,
            messages: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            update_tokens_callback: Optional[Any] = None,
            **kwargs: Any
    ) -> Dict[str, Any]:
        final_messages: List[Dict[str, Any]] = []
        if system_prompt:
            final_messages.append({"role": "system", "content": system_prompt})
        final_messages.extend(messages)

        # 使用流式 API
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=final_messages,
            stream=True,
            **kwargs
        )

        content = ""
        reasoning_content = None
        last_output_tokens = 0

        for chunk in stream:
            if hasattr(chunk, 'usage') and chunk.usage:
                if update_tokens_callback and chunk.usage.completion_tokens > last_output_tokens:
                    delta = chunk.usage.completion_tokens - last_output_tokens
                    update_tokens_callback(0, delta)
                    last_output_tokens = chunk.usage.completion_tokens

            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # 处理文本内容
            if hasattr(delta, 'content') and delta.content:
                content += delta.content
                if update_tokens_callback:
                    # 估计文本 token 数（大约每 4 字符 1 token）
                    estimated_tokens = len(delta.content) // 4 + 1
                    update_tokens_callback(0, estimated_tokens)

            # 保留 reasoning_content（思考模式模型如 MIMO 需要传回此字段）
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                reasoning_content = delta.reasoning_content
                if update_tokens_callback:
                    # 估计 reasoning token 数
                    estimated_tokens = len(delta.reasoning_content) // 4 + 1
                    update_tokens_callback(0, estimated_tokens)

        # 重新调用一次非流式获取准确的 token 统计
        response = self.client.chat.completions.create(
            model=self.model,
            messages=final_messages,
            **kwargs
        )

        # 统计 token
        if response.usage:
            self._update_token_usage(
                response.usage.prompt_tokens,
                response.usage.completion_tokens
            )

        return {"content": content, "reasoning_content": reasoning_content}
