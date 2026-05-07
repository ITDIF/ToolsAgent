
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from file_ops import TOOL_REGISTRY, TOOL_SCHEMAS, set_active_session
from utils import log_action
from config import get_config


def _thinking_animation(stop_event):
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

    def set_session(self, session_id):
        """切换当前会话 ID,后续工具调用会使用对应的撤销栈"""
        self.session_id = session_id or "default"

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

    def _need_confirm(self, tool_name, tool_args):
        """根据 config 判断该工具调用是否需要用户确认"""
        cfg = get_config()
        if tool_name == "delete_file":
            return cfg.get("confirm_delete", True)
        if tool_name == "write_file" and not tool_args.get("append", False):
            return cfg.get("confirm_overwrite", True)
        if tool_name == "batch_operations":
            # 任一子操作需要确认,批量整体就需要确认
            for op in tool_args.get("operations", []) or []:
                if not isinstance(op, dict):
                    continue
                if self._need_confirm(op.get("tool"), op.get("arguments") or {}):
                    return True
        return False

    def _execute_tool(self, tool_name, tool_args):
        """执行单个工具调用,返回结果 dict"""
        if tool_name not in TOOL_REGISTRY:
            return {"success": False, "error": "未知工具"}
        timeout = get_config().get("tool_timeout", 30)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(TOOL_REGISTRY[tool_name], **tool_args)
                result = future.result(timeout=timeout)
            log_action(tool_name, tool_args, result)
            return result
        except FuturesTimeoutError:
            return {"success": False, "error": f"工具执行超时（{timeout}秒）"}
        except TypeError as e:
            return {"success": False, "error": f"工具参数错误: {e}"}

    def _handle_tool_calls(self, tool_calls, confirm_required, confirmed_operations=None):
        """对一组 tool_calls 依次取得用户确认并执行,返回 [(tool_call, result)]

        confirmed_operations: 已确认的操作集合，用于避免重复询问相同操作
        """
        if confirmed_operations is None:
            confirmed_operations = set()
        executed = []
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["arguments"]
            desc = self._format_tool_call(tool_name, tool_args)

            # 生成操作标识用于去重
            operation_key = f"{tool_name}:{tuple(sorted((k, str(v)) for k, v in tool_args.items()))}"

            need_confirm = confirm_required and self._need_confirm(tool_name, tool_args)

            # 如果是需要确认的操作，检查是否已经确认过了
            if need_confirm:
                if operation_key in confirmed_operations:
                    # 已经确认过了，跳过再次询问
                    if self.interactive:
                        print(f"  ⎿  {desc} … (已确认)")
                else:
                    # 还没确认过，询问用户
                    if self.interactive:
                        print(f"  ⎿  {desc}")
                    confirm = input("  Allow? (y/n): ")
                    if confirm.lower() != "y":
                        if self.interactive:
                            print("  ⎿  Cancelled")
                        executed.append((tool_call, {"success": False, "error": "用户取消操作"}))
                        continue
                    # 记录已确认的操作
                    confirmed_operations.add(operation_key)
            else:
                # 不需要确认的操作
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

    def process(self, user_input, confirm_required=True):
        """处理用户输入,支持多轮工具调用直到模型给出最终回复"""
        set_active_session(self.session_id)
        self.messages.append({"role": "user", "content": user_input})
        start_time = time.time()
        cfg = get_config()
        max_iterations = int(cfg.get("max_tool_iterations", 8))
        max_time = float(cfg.get("max_request_time", 300))

        # 在同一次请求中记录已确认的操作，避免重复询问
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

        # 达到最大迭代次数仍未结束,要求模型用普通对话给出总结
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
        if tool_name == "undo_last":
            count = args.get("count", 1)
            return f"撤销最近 {count} 次操作" if count != 1 else "撤销最后一次操作"
        elif tool_name == "undo_history":
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

