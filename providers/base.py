import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类"""

    def __init__(self):
        self.token_usage: Dict[str, int] = {"input": 0, "output": 0, "total": 0}
        self.max_retries: int = 3
        self.timeout: float = 60.0

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

    def build_assistant_message(self, content: Optional[str], tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构造一轮 assistant 消息(默认 OpenAI 风格)。返回应 extend 到对话历史的消息列表。

        Args:
            content: 助手回复内容
            tool_calls: 工具调用列表

        Returns:
            消息列表
        """
        msg = {"role": "assistant", "content": content or None}
        if tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
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
                "content": json.dumps(result, ensure_ascii=False),
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

    @abstractmethod
    def chat(
            self,
            messages: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            **kwargs: Any
    ) -> str:
        """
        普通对话，不使用工具

        Args:
            messages: 对话历史
            system_prompt: 系统提示词
            **kwargs: 其他参数

        Returns:
            回复内容字符串
        """
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

        choice = response.choices[0]
        result = {"content": choice.message.content or "", "tool_calls": []}

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })

        return result

    def chat(
            self,
            messages: List[Dict[str, Any]],
            system_prompt: Optional[str] = None,
            **kwargs: Any
    ) -> str:
        final_messages: List[Dict[str, Any]] = []
        if system_prompt:
            final_messages.append({"role": "system", "content": system_prompt})
        final_messages.extend(messages)

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

        return response.choices[0].message.content
