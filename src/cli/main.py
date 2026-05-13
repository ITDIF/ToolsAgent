import os
import sys
import io
import time
import logging
import shutil
import threading
from pathlib import Path
from dotenv import load_dotenv

# 在 Windows 上设置标准输出为 UTF-8 以正确显示中文（仅在TTY环境下）
if sys.platform == 'win32':
    try:
        # 只有在stdout是TTY并且有buffer的情况下才替换
        if sys.stdout.isatty() and hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if sys.stderr.isatty() and hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        # 编码设置失败时忽略，不影响主功能
        pass

from src.core.llm import (
    BaseLLMProvider, OpenAICompatibleProvider,
    ClaudeProvider, KimiProvider, DoubaoProvider, GlmProvider, XiaomiProvider
)
from src.core.agent import FileAgent
from src.infra.session import (
    generate_session_id, save_session, load_session, list_sessions
)
from src.infra.utils import get_recent_logs, cleanup_old_logs, shutdown_log_writer
from src.infra.config import get_config
from src.infra.logging_config import configure_logging
from src.security.undo import cleanup_old_backups, undo_last, set_active_session, get_undo_history

from src.ui.console import Color

# 模型 Provider 注册表(主键即菜单顺序)
MODEL_PROVIDERS = {
    "claude": {
        "class": ClaudeProvider,
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-6",
        "name": "Claude (Anthropic)",
        "aliases": [],
        "needs_endpoint": False,
        "base_url_env": None,
        "base_url_default": None,
    },
    "kimi": {
        "class": KimiProvider,
        "env_key": "KIMI_API_KEY",
        "default_model": "moonshot-v1-8k",
        "name": "Kimi (月之暗面)",
        "aliases": ["moonshot"],
        "needs_endpoint": False,
        "base_url_env": None,
        "base_url_default": None,
    },
    "doubao": {
        "class": DoubaoProvider,
        "env_key": "DOUBAO_API_KEY",
        "default_model": "",
        "name": "豆包 (字节跳动)",
        "aliases": [],
        "needs_endpoint": True,
        "base_url_env": "DOUBAO_BASE_URL",
        "base_url_default": "https://ark.cn-beijing.volces.com/api/v3",
    },
    "glm": {
        "class": GlmProvider,
        "env_key": "GLM_API_KEY",
        "default_model": "glm-4",
        "name": "GLM (智谱 AI)",
        "aliases": [],
        "needs_endpoint": False,
        "base_url_env": None,
        "base_url_default": None,
    },
    "xiaomi": {
        "class": XiaomiProvider,
        "env_key": "XIAOMI_API_KEY",
        "default_model": "mimo-v2.5",
        "name": "小米 (MIMO)",
        "aliases": ["mimo"],
        "needs_endpoint": False,
        "base_url_env": "XIAOMI_BASE_URL",
        "base_url_default": "https://api.mimo.ai/v1",
    },
}


def _match_provider_key(model_name):
    """根据模型名前缀匹配 provider key,匹配主键或别名都返回主键"""
    name = (model_name or "").lower()
    for key, info in MODEL_PROVIDERS.items():
        if name.startswith(key):
            return key
        for alias in info.get("aliases", []):
            if name.startswith(alias):
                return key
    return None


def _build_provider(provider_key, model_name):
    """通用构造函数,屏蔽各 provider 的差异"""
    info = MODEL_PROVIDERS[provider_key]
    api_key = os.getenv(info["env_key"])
    if not api_key:
        print(f"未设置环境变量: {info['env_key']}")
        return None
    kwargs = {"api_key": api_key, "model": model_name}
    if info["base_url_env"]:
        kwargs["base_url"] = os.getenv(info["base_url_env"], info["base_url_default"])
    try:
        return info["class"](**kwargs)
    except Exception as e:
        print(f"创建 Provider 失败: {e}")
        return None


def create_provider(model_name):
    """根据完整模型名创建 Provider(用于配置文件中的 default_model)"""
    key = _match_provider_key(model_name)
    if not key:
        print(f"未知的模型: {model_name}")
        return None
    info = MODEL_PROVIDERS[key]
    if info["needs_endpoint"]:
        endpoint = input(f"请输入{info['name']}接入点 ID: ").strip()
        if not endpoint:
            print("必须输入接入点 ID")
            return None
        return _build_provider(key, endpoint)
    return _build_provider(key, model_name)


def select_model():
    """从菜单交互选择模型"""
    keys = list(MODEL_PROVIDERS.keys())
    print("请选择模型:")
    for i, k in enumerate(keys, 1):
        print(f"{i}. {MODEL_PROVIDERS[k]['name']}")
    choice = input(f"请输入选项 (1-{len(keys)}): ").strip()
    try:
        idx = int(choice) - 1
    except ValueError:
        print("无效输入")
        return None
    if not 0 <= idx < len(keys):
        print("无效选项")
        return None

    key = keys[idx]
    info = MODEL_PROVIDERS[key]
    if info["needs_endpoint"]:
        endpoint = input(f"请输入{info['name']}接入点 ID: ").strip()
        if not endpoint:
            print("必须输入接入点 ID")
            return None
        return _build_provider(key, endpoint)
    default = info["default_model"]
    prompt = f"请输入模型名称 (默认 {default}): " if default else "请输入模型名称: "
    model = input(prompt).strip() or default
    if not model:
        print("必须输入模型名称")
        return None
    return _build_provider(key, model)


def _cmd_history(agent):
    """加载历史会话"""
    sessions = list_sessions()
    if not sessions:
        print(f"{Color.GRAY}没有历史会话{Color.RESET}")
        return None, None
    print(f"{Color.GRAY}历史会话:{Color.RESET}")
    for i, s in enumerate(sessions, 1):
        print(f"  {i}. {s['id']} ({s['message_count']}条消息, {s['updated_at']})")
    idx = input(f"{Color.GRAY}输入序号加载会话 (按回车取消){Color.RESET}\n{Color.GREEN}> {Color.RESET}").strip()
    if not idx:
        return None, None
    try:
        idx = int(idx) - 1
        if 0 <= idx < len(sessions):
            sid = sessions[idx]['id']
            msgs = load_session(sid)
            if msgs is not None:
                print(f"{Color.GRAY}已加载会话: {sid}{Color.RESET}")
                return sid, msgs
            else:
                print(f"{Color.RED}加载失败{Color.RESET}")
                return None, None
        else:
            print(f"{Color.RED}无效选项{Color.RESET}")
            return None, None
    except ValueError:
        print(f"{Color.RED}无效输入{Color.RESET}")
        return None, None


def _cmd_logs():
    """查看操作日志"""
    logs = get_recent_logs(20)
    if not logs:
        print(f"{Color.GRAY}没有操作记录{Color.RESET}")
        return
    print(f"{Color.GRAY}最近操作记录:{Color.RESET}")
    for log in logs:
        result = log['result']
        mark = f"{Color.GREEN}✓{Color.RESET}" if result.get('success') else f"{Color.RED}✗{Color.RESET}"
        print(f"  [{log['timestamp']}] {mark} {log['action_type']}")


def _cmd_auth(agent):
    """查看/管理本次会话的工具授权"""
    granted = sorted(agent.session_authorized_tools)
    if not granted:
        print(f"{Color.GRAY}本次会话尚无工具授权{Color.RESET}")
        return
    print(f"{Color.GRAY}本次会话已授权的工具 ({len(granted)} 个):{Color.RESET}")
    for i, tool in enumerate(granted, 1):
        print(f"  {i}. {Color.YELLOW}{tool}{Color.RESET}")
    choice = input(
        f"{Color.GRAY}输入序号撤销 / 'all' 全部清空 / 回车退出{Color.RESET}\n{Color.GREEN}> {Color.RESET}"
    ).strip().lower()
    if not choice:
        return
    if choice in ("all", "a", "c", "clear"):
        n = agent.revoke_session_authorizations()
        print(f"{Color.GRAY}已清空 {n} 条会话授权{Color.RESET}")
        return
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(granted):
            tool = granted[idx]
            agent.session_authorized_tools.discard(tool)
            print(f"{Color.GRAY}已撤销授权: {tool}{Color.RESET}")
        else:
            print(f"{Color.RED}无效序号{Color.RESET}")
    except ValueError:
        print(f"{Color.RED}无效输入{Color.RESET}")


def _save_and_exit(session_id, agent):
    """保存会话并显示统计"""
    save_session(session_id, agent.messages)
    usage = agent.get_token_usage()
    print(f"\n{Color.GRAY}本次会话 Token 统计:{Color.RESET}")
    print(f"  输入: {usage['input']}  输出: {usage['output']}  总计: {usage['total']}")
    print(f"\n{Color.GRAY}会话已保存，再见!{Color.RESET}")
    shutdown_log_writer()


def _print_stats(elapsed, before_usage, after_usage):
    """打印时间和 Token 统计"""
    delta_total = after_usage["total"] - before_usage["total"]
    print(f"{Color.GRAY}  [{elapsed:.2f}s | +{delta_total}t | all：{after_usage['total']}]{Color.RESET}")


def _print_help():
    print(f"""{Color.GRAY}可用命令:{Color.RESET}
  {Color.YELLOW}/help{Color.RESET}       显示此帮助 (别名: /h)
  {Color.YELLOW}/history{Color.RESET}    加载历史会话 (别名: /his)
  {Color.YELLOW}/logs{Color.RESET}       查看最近操作日志 (别名: /log, /l)
  {Color.YELLOW}/save{Color.RESET}       手动保存当前会话 (别名: /s)
  {Color.YELLOW}/model{Color.RESET}      切换模型 (别名: /m)
  {Color.YELLOW}/auth{Color.RESET}       查看/管理本次会话的工具授权
  {Color.YELLOW}/undo{Color.RESET} [N]   撤销最近 N 次文件操作 (别名: /u)
  {Color.YELLOW}/undo-list{Color.RESET}  查看可撤销的操作历史 (别名: /ul, /undolist)
  {Color.YELLOW}/quit{Color.RESET}       退出程序 (别名: /q, /exit)""")


def _run_tui(provider, default_model, session_id):
    """启动 TUI 模式"""
    from src.ui.tui_bridge import TuiBridge
    from src.ui.tui_commands import dispatch_command
    import threading
    import subprocess

    bridge = TuiBridge()
    port = bridge.start_server()
    node_process_ref = [None]  # 可变容器，供闭包引用 node 子进程

    # 构造工具状态回调
    def _build_tool_status_sender(tui_bridge):
        _active_tools = {}  # key -> msg_id
        _tool_counter = {}  # tool_name -> 计数器，避免同名工具并发冲突

        def sender(status, tool_name, args_or_result, description):
            import time as _t
            if status == "running":
                _tool_counter[tool_name] = _tool_counter.get(tool_name, 0) + 1
                seq = _tool_counter[tool_name]
                msg_id = f"{tool_name}_{int(_t.time() * 1000)}_{seq}"
                _active_tools[f"{tool_name}_{seq}"] = msg_id
                tui_bridge.send("tool_status", {
                    "id": msg_id,
                    "toolName": tool_name,
                    "status": status,
                    "description": description,
                    "parameters": args_or_result if isinstance(args_or_result, dict) else None,
                })
            else:
                # 找到该工具最近的一个 active key
                matching_keys = [k for k in _active_tools if k.startswith(f"{tool_name}_")]
                if matching_keys:
                    key = matching_keys[-1]
                    msg_id = _active_tools.pop(key)
                else:
                    msg_id = f"{tool_name}_unknown"
                tui_bridge.send("tool_status", {
                    "id": msg_id,
                    "toolName": tool_name,
                    "status": status,
                    "description": description,
                    "result": args_or_result if isinstance(args_or_result, dict) and status == "success" else None,
                    "error": str(args_or_result) if status == "error" else None,
                })
        return sender

    agent = FileAgent(
        provider, session_id=session_id,
        interactive=False,
        tool_status_callback=_build_tool_status_sender(bridge),
        confirm_callback=bridge.request_confirmation,
    )

    def _process_user_input(content, tui_bridge, file_agent, sid):
        """在独立线程中处理用户输入"""
        try:
            before = time.time()
            before_usage = file_agent.get_token_usage()
            stop_update_event = threading.Event()

            # 后台线程：定期发送思考状态更新
            def _send_thinking_updates():
                """后台线程：定期发送思考状态更新"""
                while not stop_update_event.is_set():
                    elapsed = time.time() - before
                    current_usage = file_agent.get_token_usage()
                    token_delta = current_usage["total"] - before_usage["total"]
                    tui_bridge.send_thinking_update(elapsed, token_delta)
                    if stop_update_event.wait(0.1):
                        break

            try:
                tui_bridge.send_thinking_start()
                update_thread = threading.Thread(target=_send_thinking_updates, daemon=True)
                update_thread.start()
                response = file_agent.process(content)
                stop_update_event.set()
                update_thread.join(timeout=0.5)
                elapsed = time.time() - before
                after_usage = file_agent.get_token_usage()

                tui_bridge.send_thinking_end(elapsed, {
                    "input": after_usage["input"] - before_usage["input"],
                    "output": after_usage["output"] - before_usage["output"],
                    "total": after_usage["total"] - before_usage["total"],
                })

                tui_bridge.send("assistant_msg", {
                    "content": response,
                    "elapsed": elapsed,
                    "tokenUsage": {
                        "input": after_usage["input"] - before_usage["input"],
                        "output": after_usage["output"] - before_usage["output"],
                        "total": after_usage["total"] - before_usage["total"],
                    },
                })
            except Exception as e:
                import traceback
                logging.error(f"处理消息失败: {e}\n{traceback.format_exc()}")
                stop_update_event.set()
                tui_bridge.send("error", {"content": f"处理失败: {e}"})

            save_session(sid, file_agent.messages)
        except Exception as e:
            import traceback
            logging.error(f"消息处理循环异常: {e}\n{traceback.format_exc()}")
            try:
                tui_bridge.send("error", {"content": f"系统错误: {e}"})
            except Exception:
                pass

    def _handle_tui_message(message, tui_bridge, file_agent, sid):
        """处理来自 TUI 的消息"""
        msg_type = message.get("type")
        payload = message.get("payload", message)

        if msg_type == "user_input":
            content = payload.get("content", "")
            if not content:
                return

            # 斜杠命令
            if content.startswith("/"):
                parts = content[1:].split(maxsplit=1)
                cmd_name = parts[0].lower() if parts else ""
                cmd_args = {}
                if len(parts) > 1:
                    if cmd_name in ("undo", "u"):
                        try:
                            cmd_args["count"] = int(parts[1].strip())
                        except ValueError:
                            pass
                if cmd_name in ("exit", "quit", "q"):
                    tui_bridge.send("system_notify", {"content": "正在退出...", "level": "info"})
                    tui_bridge.send("exit", {})  # 通知前端退出
                    # 后端主动清理，不依赖前端 process.exit
                    tui_bridge.close()
                    proc = node_process_ref[0]
                    if proc and proc.poll() is None:
                        proc.terminate()
                    return
                # /model <name> 快捷切换
                if cmd_name in ("model", "m") and len(parts) > 1:
                    from src.ui.tui_commands import handle_model_switch_direct
                    handle_model_switch_direct(tui_bridge, file_agent, parts[1].strip())
                    return
                dispatch_command(tui_bridge, file_agent, sid, cmd_name, cmd_args)
                return

            # 异步处理用户输入
            threading.Thread(
                target=_process_user_input,
                args=(content, tui_bridge, file_agent, sid),
                daemon=True
            ).start()

        elif msg_type == "command":
            name = payload.get("name", "")
            cmd_args = payload.get("args", {}) or {}
            if name in ("exit", "quit", "q"):
                tui_bridge.send("system_notify", {"content": "正在退出...", "level": "info"})
                tui_bridge.send("exit", {})  # 通知前端退出
                # 后端主动清理，不依赖前端 process.exit
                tui_bridge.close()
                proc = node_process_ref[0]
                if proc and proc.poll() is None:
                    proc.terminate()
                return
            dispatch_command(tui_bridge, file_agent, sid, name, cmd_args)

    # 注册消息处理器
    bridge.on_message(lambda msg: _handle_tui_message(msg, bridge, agent, session_id))

    # 启动 Node.js TUI 应用
    tui_dir = Path(__file__).parent.parent.parent / "tui"
    tui_script = tui_dir / "dist" / "main.js"

    # 检测 npm 和 node 命令
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    node_cmd = "node.exe" if sys.platform == "win32" else "node"

    npm_available = shutil.which(npm_cmd) is not None
    node_available = shutil.which(node_cmd) is not None

    if not npm_available or not node_available:
        print(f"{Color.RED}错误: Node.js 和 npm 未安装或不在 PATH 中{Color.RESET}")
        print(f"{Color.GRAY}请安装 Node.js: https://nodejs.org/{Color.RESET}")
        print(f"{Color.GRAY}或使用传统 CLI 模式: python -m src.cli.main{Color.RESET}")
        return

    if not tui_script.exists():
        print(f"{Color.YELLOW}Node.js TUI 未构建，正在构建...{Color.RESET}")
        try:
            subprocess.run(
                [npm_cmd, "run", "build"],
                cwd=tui_dir,
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            print(f"{Color.RED}Node.js TUI 构建失败{Color.RESET}")
            if e.stderr:
                print(f"{Color.RED}{e.stderr}{Color.RESET}")
            print(f"\n{Color.GRAY}请手动运行: cd tui && npm install && npm run build{Color.RESET}")
            print(f"{Color.GRAY}或使用传统 CLI 模式: python -m src.cli.main{Color.RESET}")
            return

    # 设置环境变量，传递端口
    env = os.environ.copy()
    env["TUI_BACKEND_PORT"] = str(port)

    try:
        print(f"{Color.GRAY}正在启动 TUI 界面...{Color.RESET}")

        node_process = subprocess.Popen(
            [node_cmd, str(tui_script)],
            cwd=tui_dir,
            env=env
        )
        node_process_ref[0] = node_process

        bridge.wait_for_connection()

        bridge.send("ready", {
            "model": default_model,
            "sessionId": session_id,
        })

        node_process.wait()
        bridge.close()
        print(f"\n{Color.GRAY}会话已保存，再见!{Color.RESET}")
        shutdown_log_writer()
    except FileNotFoundError:
        print(f"{Color.RED}错误: 找不到 node 命令{Color.RESET}")
        print(f"{Color.GRAY}请确保 Node.js 已安装并在 PATH 中{Color.RESET}")
    except KeyboardInterrupt:
        bridge.close()
        print(f"\n{Color.GRAY}会话已保存，再见!{Color.RESET}")
        shutdown_log_writer()


def main():
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description="本地文件操作助手")
    parser.add_argument("--tui", action="store_true", help="启动现代化终端界面")
    args = parser.parse_args()

    load_dotenv()

    # 配置日志
    log_dir = Path.home() / ".toolsagent" / "logs"
    log_level = logging.INFO
    if args.tui:
        configure_logging(level=logging.WARNING, log_dir=log_dir, log_to_console=False)
    else:
        configure_logging(level=log_level, log_dir=log_dir)

    # 检查是否有默认模型配置
    config = get_config()
    default_model = config.get("default_model", "mimo-v2.5")

    # 启动时清理过期日志与旧备份
    cleanup_old_logs(config.get("log_retention_days", 30))
    cleanup_old_backups()

    # 尝试使用默认模型
    provider = create_provider(default_model)

    # 如果默认模型加载失败，提示用户选择
    if not provider:
        print(f"{Color.RED}无法加载默认模型 '{default_model}'{Color.RESET}")
        print()
        provider = select_model()
        if not provider:
            return

    # 默认新建会话
    session_id = generate_session_id()

    # ===== TUI 模式 =====
    if args.tui:
        _run_tui(provider, default_model, session_id)
        return

    # ===== CLI 模式 =====
    agent = FileAgent(provider, session_id=session_id, interactive=True)

    print(
        f"{Color.BOLD}本地文件操作助手{Color.RESET}  {Color.GRAY}—  输入 /help 查看命令，或使用 --tui 参数启动现代化界面{Color.RESET}")
    print()
    if provider:
        print(f"{Color.GRAY}已加载默认模型: {default_model}{Color.RESET}")
    print(f"{Color.GRAY}新会话 {session_id}{Color.RESET}")
    _print_help()

    while True:
        try:
            user_input = input(f"{Color.GREEN}> {Color.RESET}").strip()

            if not user_input:
                continue

            # 斜杠命令解析
            if user_input.startswith("/"):
                parts = user_input[1:].split(maxsplit=1)
                cmd = parts[0].lower() if parts else ""
                arg_str = parts[1] if len(parts) > 1 else ""

                if cmd in ["quit", "exit", "q"]:
                    _save_and_exit(session_id, agent)
                    break
                elif cmd in ["save", "s"]:
                    save_session(session_id, agent.messages)
                    print(f"{Color.GRAY}已保存{Color.RESET}")
                    continue
                elif cmd in ["history", "his"]:
                    sid, msgs = _cmd_history(agent)
                    if sid and msgs is not None:
                        session_id = sid
                        agent.set_session(sid)
                        agent.messages = msgs
                    continue
                elif cmd in ["logs", "log", "l"]:
                    _cmd_logs()
                    continue
                elif cmd == "auth":
                    _cmd_auth(agent)
                    continue
                elif cmd in ["model", "m"]:
                    new_provider = select_model()
                    if new_provider:
                        agent.llm = new_provider
                        print(f"{Color.GREEN}模型已切换{Color.RESET}")
                    continue
                elif cmd in ["help", "h"]:
                    _print_help()
                    continue
                elif cmd in ["undo", "u"]:
                    set_active_session(agent.session_id)
                    count = 1
                    if arg_str:
                        try:
                            count = max(1, int(arg_str.strip()))
                        except ValueError:
                            print(f"{Color.RED}无效步数: {arg_str}{Color.RESET}")
                            continue
                    result = undo_last(count=count)
                    if result["success"] or result.get("undone", 0) > 0:
                        for r in result.get("results", []):
                            if r["success"]:
                                msg = r["message"]
                                if isinstance(msg, dict):
                                    print(f"{Color.GREEN}✓{Color.RESET} {msg['label']}")
                                    for sr in msg.get("sub_results", []):
                                        mark = f"{Color.GREEN}✓{Color.RESET}" if sr[
                                            "success"] else f"{Color.RED}✗{Color.RESET}"
                                        print(f"  {mark} {sr.get('message') or sr.get('error')}")
                                else:
                                    print(f"{Color.GREEN}✓{Color.RESET} {msg}")
                            else:
                                print(f"{Color.RED}✗{Color.RESET} {r.get('error')}")
                    else:
                        print(f"{Color.RED}撤销失败: {result.get('error')}{Color.RESET}")
                    continue
                elif cmd in ("undo-list", "undolist", "ul"):
                    set_active_session(agent.session_id)
                    h = get_undo_history()
                    if not h["items"]:
                        print(f"{Color.GRAY}撤销栈为空{Color.RESET}")
                    else:
                        print(f"{Color.GRAY}撤销栈 ({h['count']} 条):{Color.RESET}")
                        for it in h["items"]:
                            print(f"  {it['index']}. [{it['type']}] {it['description']}")
                    continue
                else:
                    print(f"{Color.RED}未知命令{Color.RESET}  {user_input}")
                    continue

            # 普通对话
            before = time.time()
            before_usage = agent.get_token_usage()
            response = agent.process(user_input)
            elapsed = time.time() - before
            after_usage = agent.get_token_usage()

            print(response)
            _print_stats(elapsed, before_usage, after_usage)

            # 自动保存会话
            save_session(session_id, agent.messages)

        except KeyboardInterrupt:
            _save_and_exit(session_id, agent)
            break
        except Exception as e:
            print(f"{Color.RED}错误: {e}{Color.RESET}")
            shutdown_log_writer()


if __name__ == "__main__":
    main()
