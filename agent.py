
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from file_ops import TOOL_REGISTRY, TOOL_SCHEMAS
from utils import log_action
from config import get_config


SYSTEM_PROMPT = """你是一个本地文件操作助手。你可以帮助用户管理本地文件和文件夹。

支持的操作：
- 移动文件/文件夹
- 复制文件/文件夹
- 删除文件/文件夹（危险操作，执行前请确认用户意图）
- 创建文件夹
- 创建文件
- 读取文件内容
- 写入文件内容（覆盖或追加）
- 重命名文件/文件夹
- 搜索文件/文件夹
- 列出文件

请先理解用户的意图，然后选择合适的工具执行操作。执行危险操作（如删除、覆盖写入）前，请确保用户明确确认。"""


class FileAgent:
    """文件操作代理"""

    def __init__(self, llm_provider):
        self.llm = llm_provider
        self.messages = []
        self.config = get_config()
        self.total_tokens = {"input": 0, "output": 0, "total": 0}

    def get_token_usage(self):
        """获取 token 使用统计"""
        return self.total_tokens.copy()

    def _update_total_tokens(self):
        """从 LLM Provider 获取并汇总 token 使用"""
        usage = self.llm.get_token_usage()
        self.total_tokens["input"] += usage["input"]
        self.total_tokens["output"] += usage["output"]
        self.total_tokens["total"] += usage["total"]
        self.llm.reset_token_usage()

    def process(self, user_input, confirm_required=True):
        """处理用户输入"""
        self.messages.append({"role": "user", "content": user_input})

        # 第一轮：LLM 决定调用工具
        response = self.llm.chat_with_tools(
            messages=self.messages,
            tools=TOOL_SCHEMAS,
            system_prompt=SYSTEM_PROMPT
        )
        self._update_total_tokens()

        if response["tool_calls"]:
            tool_results = []
            for tool_call in response["tool_calls"]:
                tool_name = tool_call["name"]
                tool_args = tool_call["arguments"]

                # 对删除操作和覆盖写入询问确认
                need_confirm = confirm_required and (
                    tool_name == "delete_file" or
                    (tool_name == "write_file" and not tool_args.get("append", False))
                )

                if need_confirm:
                    action_desc = self._format_tool_call(tool_name, tool_args)
                    confirm = input(f"即将执行: {action_desc}\n确认执行? (y/n): ")
                    if confirm.lower() != "y":
                        tool_results.append({"tool_name": tool_name, "result": "用户取消操作", "id": tool_call["id"]})
                        continue

                # 执行工具（带超时保护）
                if tool_name in TOOL_REGISTRY:
                    try:
                        timeout = self.config.get("tool_timeout", 30)
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(TOOL_REGISTRY[tool_name], **tool_args)
                            result = future.result(timeout=timeout)
                        log_action(tool_name, tool_args, result)
                        tool_results.append({"tool_name": tool_name, "result": result, "id": tool_call["id"]})
                    except FuturesTimeoutError:
                        error_msg = f"工具执行超时（{timeout}秒）"
                        tool_results.append({"tool_name": tool_name, "result": {"success": False, "error": error_msg}, "id": tool_call["id"]})
                    except TypeError as e:
                        error_msg = f"工具参数错误: {e}"
                        tool_results.append({"tool_name": tool_name, "result": {"success": False, "error": error_msg}, "id": tool_call["id"]})
                else:
                    tool_results.append({"tool_name": tool_name, "result": {"success": False, "error": "未知工具"}, "id": tool_call["id"]})

            # 构建 assistant 消息 - 兼容 OpenAI 格式
            assistant_msg = {"role": "assistant", "content": response["content"] or None}
            if response["tool_calls"]:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"])
                        }
                    }
                    for tc in response["tool_calls"]
                ]
            self.messages.append(assistant_msg)

            # 构建 tool 结果消息
            for tr in tool_results:
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tr["id"],
                    "content": json.dumps(tr["result"])
                })

            # 获取最终回复（使用普通 chat）
            final_response = self.llm.chat(
                messages=self.messages,
                system_prompt=SYSTEM_PROMPT
            )
            self._update_total_tokens()
            self.messages.append({"role": "assistant", "content": final_response})
            return final_response
        else:
            self.messages.append({"role": "assistant", "content": response["content"]})
            return response["content"]

    def _format_tool_call(self, tool_name, args):
        """格式化工具调用描述"""
        if tool_name == "move_file":
            return f"移动 {args['src']} 到 {args['dst']}"
        elif tool_name == "copy_file":
            return f"复制 {args['src']} 到 {args['dst']}"
        elif tool_name == "delete_file":
            return f"删除 {args['path']}"
        elif tool_name == "create_folder":
            return f"创建文件夹 {args['path']}"
        elif tool_name == "create_file":
            content = args.get("content", "")
            if content:
                return f"创建文件 {args['path']} (包含内容)"
            else:
                return f"创建文件 {args['path']}"
        elif tool_name == "read_file":
            return f"读取文件 {args['path']}"
        elif tool_name == "write_file":
            append = args.get("append", False)
            mode = "追加" if append else "覆盖"
            return f"{mode}文件 {args['path']}"
        elif tool_name == "rename_file":
            return f"重命名 {args['src']} 到 {args['dst']}"
        elif tool_name == "search_files":
            path = args.get("path", ".")
            search_type = args.get("search_type", "all")
            return f"在 {path} 搜索 {search_type} 匹配 '{args['pattern']}'"
        elif tool_name == "list_files":
            path = args.get("path", ".")
            return f"列出 {path} 的文件"
        else:
            return f"{tool_name} {args}"

