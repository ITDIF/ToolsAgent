import os
import sys
import io
import time
import logging
import shutil
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
    # TUI模式下禁用stdout日志输出，避免污染界面
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
    # TUI模式下禁用Agent的交互式输出，改为通过消息机制通知
    agent = FileAgent(provider, session_id=session_id, interactive=not args.tui)

    # 非TUI模式下才打印欢迎信息和帮助
    if not args.tui:
        print(
            f"{Color.BOLD}本地文件操作助手{Color.RESET}  {Color.GRAY}—  输入 /help 查看命令，或使用 --tui 参数启动现代化界面{Color.RESET}")
        print()
        if provider:
            print(f"{Color.GRAY}已加载默认模型: {default_model}{Color.RESET}")
        print(f"{Color.GRAY}新会话 {session_id}{Color.RESET}")
        _print_help()

    # TUI 相关全局变量
    client_socket = None
    send_message_to_tui = None
    MSG_START = b"<<<MSG_START>>>"  # 字节形式用于解析
    MSG_END = b"<<<MSG_END>>>"
    MSG_START_STR = MSG_START.decode('utf-8')
    MSG_END_STR = MSG_END.decode('utf-8')

    # 如果指定了 --tui 参数，启动 Node.js TUI 界面
    if args.tui:
        import sys
        import json
        import uuid
        import socket
        import threading
        import subprocess

        try:
            # 启动本地 Socket 服务
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.bind(('127.0.0.1', 0))  # 绑定随机端口
            server_socket.listen(1)
            server_socket.settimeout(None)
            port = server_socket.getsockname()[1]

            is_running = True

            def _send_message_to_tui(msg_type: str, payload: dict):
                """发送消息给 TUI 界面"""
                if not client_socket:
                    import logging
                    logging.warning("无法发送消息：client_socket为空")
                    return
                message = {
                    "type": msg_type,
                    "id": str(uuid.uuid4()),
                    "timestamp": int(time.time() * 1000),
                    **payload
                }
                msg_str = f"{MSG_START_STR}\n{json.dumps(message, ensure_ascii=False)}\n{MSG_END_STR}\n"
                try:
                    client_socket.sendall(msg_str.encode('utf-8'))
                except Exception as e:
                    import logging
                    logging.error(f"发送消息给TUI失败: {str(e)}")

            send_message_to_tui = _send_message_to_tui

            def process_user_input(content: str):
                """在独立线程中处理用户输入"""
                try:
                    import logging

                    # 不需要确认消息，直接开始思考动画

                    # 调用 Agent 处理
                    before = time.time()
                    before_usage = agent.get_token_usage()
                    try:
                        logging.info("开始调用agent.process")
                        response = agent.process(content)
                        logging.info(f"agent处理完成，响应长度: {len(response)}")

                        elapsed = time.time() - before
                        after_usage = agent.get_token_usage()

                        # 发送助手回复
                        send_message_to_tui("assistant_msg", {
                            "content": response,
                            "elapsed": elapsed,
                            "token_usage": {
                                "input": after_usage["input"] - before_usage["input"],
                                "output": after_usage["output"] - before_usage["output"],
                                "total": after_usage["total"] - before_usage["total"]
                            }
                        })
                    except Exception as e:
                        import traceback
                        error_detail = traceback.format_exc()
                        # 把错误详情写入日志
                        logging.error(f"处理消息失败: {str(e)}\n{error_detail}")
                        # 发送简化的错误信息给TUI
                        send_message_to_tui("error", {
                            "content": f"处理失败: {str(e)}"
                        })

                    # 自动保存会话
                    save_session(session_id, agent.messages)
                    logging.info("会话已保存")
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    import logging
                    logging.error(f"消息处理循环异常: {str(e)}\n{error_detail}")
                    try:
                        send_message_to_tui("error", {
                            "content": f"系统错误: {str(e)}"
                        })
                    except:
                        pass

            def handle_tui_message(message: dict):
                """处理来自 TUI 的消息"""
                try:
                    import logging
                    logging.info(f"收到TUI消息: {message}")


                    msg_type = message.get("type")
                    if msg_type == "user_input":
                        content = message.get("content", "")
                        logging.info(f"用户输入: {content}")

                        # 处理TUI命令
                        if content.startswith("/"):
                            if content.lower() in ["/exit", "/quit", "/q"]:
                                send_message_to_tui("system_notify", {
                                    "content": "正在退出...",
                                    "level": "info"
                                })
                                global is_running
                                is_running = False
                                return
                            elif content.lower() in ["/help", "/h"]:
                                help_text = """可用命令:
/help, /h    显示帮助信息
/model, /m   切换模型
/exit, /q    退出程序
"""
                                send_message_to_tui("assistant_msg", {
                                    "content": help_text
                                })
                                return
                            elif content.lower() in ["/model", "/m"]:
                                # 切换模型
                                send_message_to_tui("system_notify", {
                                    "content": "请在终端中选择模型...",
                                    "level": "info"
                                })
                                # 因为select_model函数会直接打印到终端
                                new_provider = select_model()
                                if new_provider:
                                    agent.llm = new_provider
                                    # 提取模型名（兼容不同provider的格式）
                                    model_name = getattr(new_provider, 'model', str(new_provider))
                                    send_message_to_tui("model_update", {
                                        "model": model_name
                                    })
                                    send_message_to_tui("assistant_msg", {
                                        "content": f"✅ 模型已切换为: {model_name}"
                                    })
                                return

                        # 异步处理用户输入，避免阻塞socket线程
                        import threading
                        threading.Thread(target=process_user_input, args=(content,), daemon=True).start()
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    import logging
                    logging.error(f"消息处理循环异常: {str(e)}\n{error_detail}")
                    try:
                        send_message_to_tui("error", {
                            "content": f"系统错误: {str(e)}"
                        })
                    except:
                        pass

            def socket_server_thread():
                """Socket服务线程，处理与TUI的通信"""
                nonlocal client_socket
                try:
                    client_socket, addr = server_socket.accept()
                    client_socket.settimeout(None)

                    # 连接成功后，发送当前模型信息给前端
                    send_message_to_tui("model_update", {
                        "model": default_model
                    })

                    buffer = b""

                    while is_running:
                        try:
                            data = client_socket.recv(4096)  # 增大缓冲区
                            if not data:
                                break

                            buffer += data

                            # 在字节层面搜索消息边界，避免字节/字符索引不匹配问题
                            while True:
                                # 查找消息开始标记
                                start_pos = buffer.find(MSG_START)
                                if start_pos == -1:
                                    break  # 没有完整消息，继续接收

                                # 查找消息结束标记（从开始标记后面找）
                                end_pos = buffer.find(MSG_END, start_pos + len(MSG_START))
                                if end_pos == -1:
                                    break  # 消息不完整，继续接收

                                # 提取消息内容（去掉开始和结束标记）
                                msg_bytes = buffer[start_pos + len(MSG_START) : end_pos]

                                # 移除已处理的部分（包括结束标记）
                                buffer = buffer[end_pos + len(MSG_END) :]

                                # 解码并解析JSON
                                try:
                                    msg_str = msg_bytes.decode('utf-8')
                                    message = json.loads(msg_str)
                                    handle_tui_message(message)
                                except (UnicodeDecodeError, json.JSONDecodeError):
                                    import logging
                                    logging.error(f"解析 TUI 消息失败")
                                    continue
                        except Exception as e:
                            import traceback
                            error_detail = traceback.format_exc()
                            import logging
                            logging.error(f"Socket接收/处理消息异常: {str(e)}\n{error_detail}")
                            break

                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    import logging
                    logging.error(f"Socket 服务错误: {str(e)}\n{error_detail}")
                finally:
                    if client_socket:
                        try:
                            client_socket.close()
                        except:
                            pass
                    try:
                        server_socket.close()
                    except:
                        pass

            # 启动Socket服务线程
            threading.Thread(target=socket_server_thread, daemon=True).start()

            # 启动 Node.js TUI 应用
            tui_dir = Path(__file__).parent.parent.parent / "tui"
            tui_script = tui_dir / "dist" / "main.js"

            # 检测 npm 和 node 命令
            npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
            node_cmd = "node.exe" if sys.platform == "win32" else "node"

            # 检查 npm 和 node 是否可用
            npm_available = shutil.which(npm_cmd) is not None
            node_available = shutil.which(node_cmd) is not None

            if not npm_available or not node_available:
                print(f"{Color.RED}错误: Node.js 和 npm 未安装或不在 PATH 中{Color.RESET}")
                print(f"{Color.GRAY}请安装 Node.js: https://nodejs.org/{Color.RESET}")
                print(f"{Color.GRAY}或使用传统 CLI 模式: python -m src.cli.main{Color.RESET}")
                return

            if not tui_script.exists():
                # 如果构建文件不存在，尝试自动构建
                print(f"{Color.YELLOW}Node.js TUI 未构建，正在构建...{Color.RESET}")
                try:
                    result = subprocess.run(
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

            # 启动 Node.js TUI 进程
            try:
                print(f"{Color.GRAY}正在启动 TUI 界面...{Color.RESET}")
                node_process = subprocess.Popen(
                    [node_cmd, str(tui_script)],
                    cwd=tui_dir,
                    env=env
                )

                # 等待 TUI 进程结束
                node_process.wait()
                is_running = False
                print(f"\n{Color.GRAY}会话已保存，再见!{Color.RESET}")
                shutdown_log_writer()
            except FileNotFoundError:
                print(f"{Color.RED}错误: 找不到 node 命令{Color.RESET}")
                print(f"{Color.GRAY}请确保 Node.js 已安装并在 PATH 中{Color.RESET}")
            except KeyboardInterrupt:
                is_running = False
                print(f"\n{Color.GRAY}会话已保存，再见!{Color.RESET}")
                shutdown_log_writer()


        except Exception as e:
            print(f"{Color.RED}TUI 运行错误: {str(e)}{Color.RESET}")
        return

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
                        # 如果是TUI模式，同步更新前端显示的模型名
                        if args.tui and send_message_to_tui and client_socket:
                            # 提取模型名（兼容不同provider的格式）
                            model_name = getattr(new_provider, 'model', str(new_provider))
                            send_message_to_tui("model_update", {
                                "model": model_name
                            })
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
