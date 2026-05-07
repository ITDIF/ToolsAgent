
import os
import sys
import io
import time
from dotenv import load_dotenv

# 在 Windows 上设置标准输出为 UTF-8 以正确显示中文
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from providers import ClaudeProvider, KimiProvider, DoubaoProvider, GlmProvider, XiaomiProvider
from agent import FileAgent
from session import generate_session_id, save_session, load_session, list_sessions
from utils import get_recent_logs, cleanup_old_logs
from config import get_config
from file_ops import cleanup_old_backups


class _C:
    """终端颜色代码"""
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    GRAY = "\033[90m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


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
        print(f"{_C.GRAY}没有历史会话{_C.RESET}")
        return None, None
    print(f"{_C.GRAY}历史会话:{_C.RESET}")
    for i, s in enumerate(sessions, 1):
        print(f"  {i}. {s['id']} ({s['message_count']}条消息, {s['updated_at']})")
    idx = input(f"{_C.GREEN}> {_C.RESET}").strip()
    if not idx:
        return None, None
    try:
        idx = int(idx) - 1
        if 0 <= idx < len(sessions):
            sid = sessions[idx]['id']
            msgs = load_session(sid)
            if msgs is not None:
                print(f"{_C.GRAY}已加载会话: {sid}{_C.RESET}")
                return sid, msgs
            else:
                print(f"{_C.RED}加载失败{_C.RESET}")
                return None, None
        else:
            print(f"{_C.RED}无效选项{_C.RESET}")
            return None, None
    except ValueError:
        print(f"{_C.RED}无效输入{_C.RESET}")
        return None, None


def _cmd_logs():
    """查看操作日志"""
    logs = get_recent_logs(20)
    if not logs:
        print(f"{_C.GRAY}没有操作记录{_C.RESET}")
        return
    print(f"{_C.GRAY}最近操作记录:{_C.RESET}")
    for log in logs:
        result = log['result']
        mark = f"{_C.GREEN}✓{_C.RESET}" if result.get('success') else f"{_C.RED}✗{_C.RESET}"
        print(f"  [{log['timestamp']}] {mark} {log['action_type']}")


def _save_and_exit(session_id, agent):
    """保存会话并显示统计"""
    save_session(session_id, agent.messages)
    usage = agent.get_token_usage()
    print(f"\n{_C.GRAY}本次会话 Token 统计:{_C.RESET}")
    print(f"  输入: {usage['input']}  输出: {usage['output']}  总计: {usage['total']}")
    print(f"\n{_C.GRAY}会话已保存，再见!{_C.RESET}")


def _print_stats(elapsed, before_usage, after_usage):
    """打印时间和 Token 统计"""
    delta_total = after_usage["total"] - before_usage["total"]
    print(f"{_C.GRAY}  [{elapsed:.2f}s | +{delta_total}t | all：{after_usage['total']}]{_C.RESET}")


def _print_help():
    print(f"""{_C.GRAY}可用命令:{_C.RESET}
  {_C.YELLOW}/help{_C.RESET}       显示此帮助 (别名: /h)
  {_C.YELLOW}/history{_C.RESET}    加载历史会话 (别名: /his)
  {_C.YELLOW}/logs{_C.RESET}       查看最近操作日志 (别名: /log, /l)
  {_C.YELLOW}/save{_C.RESET}       手动保存当前会话 (别名: /s)
  {_C.YELLOW}/model{_C.RESET}      切换模型 (别名: /m)
  {_C.YELLOW}/undo{_C.RESET} [N]   撤销最近 N 次文件操作 (别名: /u)
  {_C.YELLOW}/undo-list{_C.RESET}  查看可撤销的操作历史 (别名: /ul, /undolist)
  {_C.YELLOW}/quit{_C.RESET}       退出程序 (别名: /q, /exit)""")


def main():
    load_dotenv()

    print(f"{_C.BOLD}本地文件操作助手{_C.RESET}  {_C.GRAY}—  输入 /help 查看命令{_C.RESET}")
    print()

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
        print(f"{_C.RED}无法加载默认模型 '{default_model}'{_C.RESET}")
        print()
        provider = select_model()
        if not provider:
            return
    else:
        print(f"{_C.GRAY}已加载默认模型: {default_model}{_C.RESET}")

    # 默认新建会话
    session_id = generate_session_id()
    agent = FileAgent(provider, session_id=session_id, interactive=True)

    print(f"{_C.GRAY}新会话 {session_id}{_C.RESET}")
    _print_help()

    while True:
        try:
            user_input = input(f"{_C.GREEN}> {_C.RESET}").strip()

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
                    print(f"{_C.GRAY}已保存{_C.RESET}")
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
                elif cmd in ["model", "m"]:
                    new_provider = select_model()
                    if new_provider:
                        agent.llm = new_provider
                        print(f"{_C.GREEN}模型已切换{_C.RESET}")
                    continue
                elif cmd in ["help", "h"]:
                    _print_help()
                    continue
                elif cmd in ["undo", "u"]:
                    from file_ops import undo_last, set_active_session
                    set_active_session(agent.session_id)
                    count = 1
                    if arg_str:
                        try:
                            count = max(1, int(arg_str.strip()))
                        except ValueError:
                            print(f"{_C.RED}无效步数: {arg_str}{_C.RESET}")
                            continue
                    result = undo_last(count=count)
                    if result["success"] or result.get("undone", 0) > 0:
                        for r in result.get("results", []):
                            if r["success"]:
                                msg = r["message"]
                                if isinstance(msg, dict):
                                    print(f"{_C.GREEN}✓{_C.RESET} {msg['label']}")
                                    for sr in msg.get("sub_results", []):
                                        mark = f"{_C.GREEN}✓{_C.RESET}" if sr["success"] else f"{_C.RED}✗{_C.RESET}"
                                        print(f"  {mark} {sr.get('message') or sr.get('error')}")
                                else:
                                    print(f"{_C.GREEN}✓{_C.RESET} {msg}")
                            else:
                                print(f"{_C.RED}✗{_C.RESET} {r.get('error')}")
                    else:
                        print(f"{_C.RED}撤销失败: {result.get('error')}{_C.RESET}")
                    continue
                elif cmd in ("undo-list", "undolist", "ul"):
                    from file_ops import get_undo_history, set_active_session
                    set_active_session(agent.session_id)
                    h = get_undo_history()
                    if not h["items"]:
                        print(f"{_C.GRAY}撤销栈为空{_C.RESET}")
                    else:
                        print(f"{_C.GRAY}撤销栈 ({h['count']} 条):{_C.RESET}")
                        for it in h["items"]:
                            print(f"  {it['index']}. [{it['type']}] {it['description']}")
                    continue
                else:
                    print(f"{_C.RED}未知命令{_C.RESET}  {user_input}")
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
            print(f"{_C.RED}错误: {e}{_C.RESET}")


if __name__ == "__main__":
    main()

