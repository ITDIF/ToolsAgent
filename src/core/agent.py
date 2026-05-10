import sys
import threading
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..file.basic import TOOL_REGISTRY, TOOL_SCHEMAS, ToolNames
from ..security.undo import set_active_session
from ..infra.utils import log_action
from ..infra.config import get_config
from ..infra.constants import ConfigDefaults
from ..ui.tui import select_option

logger = logging.getLogger(__name__)


def _thinking_animation(stop_event: threading.Event) -> None:
    """后台线程：在模型调用期间显示递增的 token 计数动画"""
    n = 0
    start = time.time()
    while not stop_event.is_set():
        elapsed = time.time() - start
        sys.stdout.write(f"\r  \033[90m⋯  +{n}t  ({elapsed:.1f}s)\033[0m")
        sys.stdout.flush()
        n += 1
        stop_event.wait(0.1)
    # 清除动画行
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()


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
- 扫描磁盘占用（统计各文件夹大小）
- 撤销最近的操作（支持指定步数,批量操作算一步整体撤销）
- 查看撤销历史
- 批量执行多个操作（适合需要一次完成多个相关写操作的场景,如整理目录、批量改名;失败可一次撤销全部）

请先理解用户的意图，然后选择合适的工具执行操作。

涉及大量同类操作（>=3 个相关步骤）时,优先使用 batch_operations,这样用户可以一次撤销整个批量。
执行危险操作（如删除、覆盖写入）前，请确保用户明确确认。
如果完成用户的请求需要多步工具操作，请逐步进行，每一步根据上一步结果决定下一步动作。"""


class FileAgent:
    """文件操作代理"""

    def __init__(self, llm_provider, session_id=None, interactive=True):
        self.llm = llm_provider
        self.messages = []
        self.total_tokens = {"input": 0, "output": 0, "total": 0}
        self.session_id = session_id or "default"
        self.interactive = interactive
        # 本次进程生命周期内已被\"会话级\"授权的工具类型集合
        # 切换 session_id / 模型时不清空,仅在进程退出时丢失
        self.session_authorized_tools: set[str] = set()

    def set_session(self, session_id):
        """切换当前会话 ID,后续工具调用会使用对应的撤销栈"""
        self.session_id = session_id or "default"

    def revoke_session_authorizations(self) -> int:
        """清空所有会话级授权,返回清空前的条数"""
        n = len(self.session_authorized_tools)
        self.session_authorized_tools.clear()
        return n

    def _is_session_authorized(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        if tool_name == ToolNames.BATCH_OPERATIONS:
            for op in tool_args.get("operations", []) or []:
                if not isinstance(op, dict):
                    continue
                sub_tool = op.get("tool")
                sub_args = op.get("arguments") or {}
                if self._need_confirm(sub_tool, sub_args) and sub_tool not in self.session_authorized_tools:
                    return False
            return True
        return tool_name in self.session_authorized_tools

    def _add_session_authorization(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
        if tool_name == ToolNames.BATCH_OPERATIONS:
            for op in tool_args.get("operations", []) or []:
                if not isinstance(op, dict):
                    continue
                sub_tool = op.get("tool")
                sub_args = op.get("arguments") or {}
                if sub_tool and self._need_confirm(sub_tool, sub_args):
                    self.session_authorized_tools.add(sub_tool)
        else:
            self.session_authorized_tools.add(tool_name)

    def get_token_usage(self):
        """获取 token 使用统计"""
        return self.total_tokens.copy()

    def _update_total_tokens(self):
        """从 LLM Provider 获取并汇总 token 使用,返回本次增量"""
        usage = self.llm.get_token_usage()
        self.total_tokens["input"] += usage["input"]
        self.total_tokens["output"] += usage["output"]
        self.total_tokens["total"] += usage["total"]
        self.llm.reset_token_usage()
        return usage.copy()

    def _need_confirm(self, tool_name: str, tool_args: Dict[str, Any]) -> bool:
        """根据 config 判断该工具调用是否需要用户确认"""
        cfg = get_config()
        if tool_name == "delete_file":
            return cfg.get("confirm_delete", True)
        if tool_name == "write_file" and not tool_args.get("append", False):
            return cfg.get("confirm_overwrite", True)
        if tool_name == ToolNames.BATCH_OPERATIONS:
            for op in tool_args.get("operations", []) or []:
                if not isinstance(op, dict):
                    continue
                if self._need_confirm(op.get("tool"), op.get("arguments") or {}):
                    return True
        return False

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个工具调用,返回结果 dict"""
        if tool_name not in TOOL_REGISTRY:
            error_msg = f"未知工具: {tool_name}"
            logger.warning(error_msg)
            return {"success": False, "error": error_msg}

        timeout = get_config().get("tool_timeout", ConfigDefaults.TOOL_TIMEOUT)
        # 对 batch_operations 自动注入 interactive 参数以显示进度
        effective_args = dict(tool_args)
        if tool_name == "batch_operations" and self.interactive:
            effective_args["interactive"] = True

        # 用 daemon 线程跑工具,join(timeout) 触发后线程仍在后台跑,
        # 但函数会立刻返回错误。Python 无法强制 kill 线程,daemon 标记
        # 保证进程退出时残留线程不阻塞退出。
        # (此前用 ThreadPoolExecutor 的 with 块会在 __exit__ 时
        #  shutdown(wait=True) 等待 worker 完成,导致 timeout 形同虚设。)
        result_box: Dict[str, Any] = {}

        def runner() -> None:
            try:
                result_box["result"] = TOOL_REGISTRY[tool_name](**effective_args)
            except BaseException as exc:  # noqa: BLE001 - 捕获后下面分类处理
                result_box["error"] = exc

        worker = threading.Thread(
            target=runner,
            name=f"tool-{tool_name}",
            daemon=True,
        )
        worker.start()
        worker.join(timeout=timeout)

        if worker.is_alive():
            error_msg = f"工具执行超时（{timeout}秒）: {tool_name}"
            logger.warning(error_msg)
            return {"success": False, "error": error_msg}

        if "error" in result_box:
            exc = result_box["error"]
            if isinstance(exc, TypeError):
                error_msg = f"工具参数错误 [{tool_name}]: {exc}"
                logger.error(error_msg)
            else:
                error_msg = f"工具执行异常 [{tool_name}]: {exc}"
                logger.exception(error_msg, exc_info=exc)
            return {"success": False, "error": error_msg}

        result = result_box.get("result", {"success": False, "error": "工具未返回结果"})
        log_action(tool_name, tool_args, result)
        return result

    def _handle_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        confirm_required: bool,
        confirmed_operations: Optional[set] = None
    ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
        """对一组 tool_calls 依次取得用户确认并执行,返回 [(tool_call, result)]

        Args:
            tool_calls: 工具调用列表
            confirm_required: 是否需要确认
            confirmed_operations: 已确认的操作集合

        Returns:
            [(tool_call, result), ...] 执行结果列表
        """
        if confirmed_operations is None:
            confirmed_operations = set()
        executed = []
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["arguments"]
            desc = self._format_tool_call(tool_name, tool_args)

            operation_key = f"{tool_name}:{tuple(sorted((k, str(v)) for k, v in tool_args.items()))}"

            need_confirm = confirm_required and self._need_confirm(tool_name, tool_args)

            if need_confirm:
                if self._is_session_authorized(tool_name, tool_args):
                    if self.interactive:
                        print(f"  ⎿  {desc} … (会话已授权)")
                elif operation_key in confirmed_operations:
                    if self.interactive:
                        print(f"  ⎿  {desc} … (已确认)")
                else:
                    if self.interactive:
                        print(f"  ⎿  {desc}")
                    choice = select_option(
                        "  请选择操作:",
                        ["本次允许", "本次会话允许", "取消"],
                        default=0,
                    )
                    if choice == 1:
                        self._add_session_authorization(tool_name, tool_args)
                        confirmed_operations.add(operation_key)
                        if self.interactive:
                            print(f"  ⎿  本次会话内已授权同类操作")
                    elif choice == 0:
                        confirmed_operations.add(operation_key)
                    else:
                        if self.interactive:
                            print("  ⎿  Cancelled")
                        executed.append((tool_call, {"success": False, "error": "用户取消操作"}))
                        continue
            else:
                if self.interactive:
                    print(f"  ⎿  {desc} …")

            result = self._execute_tool(tool_name, tool_args)
            if self.interactive:
                msg = result.get("message")
                err = result.get("error")
                if msg:
                    print(f"  ⎿  {msg}")
                elif err:
                    print(f"  ⎿  Error: {err}")
            executed.append((tool_call, result))
        return executed

    def process(self, user_input: str, confirm_required: bool = True) -> str:
        """处理用户输入,支持多轮工具调用直到模型给出最终回复"""
        set_active_session(self.session_id)
        self.messages.append({"role": "user", "content": user_input})
        start_time = time.time()
        cfg = get_config()
        max_iterations = int(cfg.get("max_tool_iterations", ConfigDefaults.MAX_TOOL_ITERATIONS))
        max_time = float(cfg.get("max_request_time", ConfigDefaults.MAX_REQUEST_TIME))

        confirmed_operations = set()

        for _ in range(max_iterations):
            if time.time() - start_time > max_time:
                msg = "请求处理时间过长，已中断。请简化需求后重试。"
                self.messages.append({"role": "assistant", "content": msg})
                return msg

            iter_start = time.time()
            stop_event = threading.Event()
            anim_thread = None
            if self.interactive:
                anim_thread = threading.Thread(target=_thinking_animation, args=(stop_event,))
                anim_thread.start()

            try:
                response = self.llm.chat_with_tools(
                    messages=self.messages,
                    tools=TOOL_SCHEMAS,
                    system_prompt=SYSTEM_PROMPT,
                )
            finally:
                stop_event.set()
                if anim_thread is not None:
                    anim_thread.join()

            delta = self._update_total_tokens()
            iter_elapsed = time.time() - iter_start

            if self.interactive and delta["total"] > 0:
                print(f"\033[90m  [{iter_elapsed:.2f}s | +{delta['total']}t]\033[0m")

            if not response["tool_calls"]:
                final = response["content"] or ""
                self.messages.append({"role": "assistant", "content": final})
                return final

            executed = self._handle_tool_calls(response["tool_calls"], confirm_required, confirmed_operations)

            self.messages.extend(
                self.llm.build_assistant_message(response["content"], response["tool_calls"])
            )
            self.messages.extend(self.llm.build_tool_result_messages(executed))

        # 达到最大迭代次数仍未结束
        iter_start = time.time()
        stop_event = threading.Event()
        anim_thread = None
        if self.interactive:
            anim_thread = threading.Thread(target=_thinking_animation, args=(stop_event,))
            anim_thread.start()

        try:
            final_response = self.llm.chat(messages=self.messages, system_prompt=SYSTEM_PROMPT)
        finally:
            stop_event.set()
            if anim_thread is not None:
                anim_thread.join()

        delta = self._update_total_tokens()
        iter_elapsed = time.time() - iter_start

        if self.interactive and delta["total"] > 0:
            print(f"\033[90m  [{iter_elapsed:.2f}s | +{delta['total']}t]\033[0m")

        self.messages.append({"role": "assistant", "content": final_response})
        return final_response

    def _format_tool_call(self, tool_name, args):
        """格式化工具调用描述"""
        if tool_name == ToolNames.UNDO_LAST:
            count = args.get("count", 1)
            return f"撤销最近 {count} 次操作" if count != 1 else "撤销最后一次操作"
        elif tool_name == ToolNames.UNDO_HISTORY:
            return "查看撤销历史"
        elif tool_name == "batch_operations":
            ops = args.get("operations", []) or []
            label = args.get("label")
            head = label or f"批量执行 {len(ops)} 个操作"
            preview_lines = []
            for op in ops[:5]:
                if not isinstance(op, dict):
                    continue
                sub_name = op.get("tool", "?")
                sub_args = op.get("arguments") or {}
                preview_lines.append(f"  - {self._format_tool_call(sub_name, sub_args)}")
            more = len(ops) - len(preview_lines)
            if more > 0:
                preview_lines.append(f"  - ... 共 {len(ops)} 步,省略 {more} 步")
            preview = "\n".join(preview_lines)
            return f"{head}\n{preview}" if preview else head
        elif tool_name == "move_file":
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
        elif tool_name == "scan_disk":
            path = args.get("path", ".")
            return f"扫描 {path} 的磁盘占用"
        elif tool_name == "extract_archive":
            output = args.get("output_path")
            if output:
                return f"解压 {args['archive_path']} 到 {output}"
            else:
                return f"解压 {args['archive_path']}"
        elif tool_name == "create_archive":
            srcs = args.get("source_paths")
            if isinstance(srcs, list):
                if len(srcs) == 1:
                    src_str = srcs[0]
                else:
                    src_str = f"{len(srcs)} 个文件"
            else:
                src_str = srcs
            return f"压缩 {src_str} -> {args['archive_path']}"
        else:
            return f"{tool_name} {args}"
