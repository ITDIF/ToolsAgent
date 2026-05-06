
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


def session_menu():
    """会话菜单"""
    print("\n会话选项:")
    print("1. 新建会话")
    print("2. 加载历史会话")
    print("3. 查看操作日志")

    choice = input("请输入选项 (1-3): ").strip()

    if choice == "1":
        return generate_session_id(), []
    elif choice == "2":
        sessions = list_sessions()
        if not sessions:
            print("没有历史会话")
            return None, None
        print("\n历史会话:")
        for i, s in enumerate(sessions, 1):
            print(f"{i}. {s['id']} ({s['message_count']}条消息, 更新于{s['updated_at']}")
        idx = input("\n选择会话编号: ").strip()
        try:
            idx = int(idx) - 1
            if 0 <= idx < len(sessions):
                session_id = sessions[idx]['id']
                messages = load_session(session_id)
                return session_id, messages
            else:
                print("无效选项")
                return None, None
        except ValueError:
            print("无效输入")
            return None, None
    elif choice == "3":
        logs = get_recent_logs(20)
        if not logs:
            print("没有操作记录")
            return None, None
        print("\n最近操作记录:")
        for log in logs:
            result = log['result']
            status = "成功" if result.get('success') else "失败"
            print(f"[{log['timestamp']}] {log['action_type']} - {status}")
        return None, None
    else:
        print("无效选项")
        return None, None


def main():
    load_dotenv()

    print("=" * 50)
    print("       本地文件操作助手")
    print("=" * 50)
    print()

    # 检查是否有默认模型配置
    config = get_config()
    default_model = config.get("default_model", "mimo-v2.5")

    # 启动时清理过期日志
    cleanup_old_logs(config.get("log_retention_days", 30))

    # 尝试使用默认模型
    provider = create_provider(default_model)

    # 如果默认模型加载失败，提示用户选择
    if not provider:
        print(f"无法加载默认模型 '{default_model}'")
        print()
        provider = select_model()
        if not provider:
            return
    else:
        print(f"已加载默认模型: {default_model}")

    session_id, messages = session_menu()
    if not session_id:
        return

    agent = FileAgent(provider)
    if messages:
        agent.messages = messages

    print(f"\n会话 ID: {session_id}")
    print("输入 'quit' 或 'exit' 退出，'save' 保存会话")
    print()

    last_usage = agent.get_token_usage()

    while True:
        try:
            user_input = input("你: ").strip()

            if user_input.lower() in ["quit", "exit", "退出"]:
                save_session(session_id, agent.messages)
                usage = agent.get_token_usage()
                print(f"\n本次会话 Token 统计:")
                print(f"  输入: {usage['input']}")
                print(f"  输出: {usage['output']}")
                print(f"  总计: {usage['total']}")
                print("\n会话已保存，再见!")
                break
            if user_input.lower() == "save":
                save_session(session_id, agent.messages)
                print("会话已保存!")
                continue
            if not user_input:
                continue

            before = time.time()
            before_usage = agent.get_token_usage()
            response = agent.process(user_input)
            elapsed = time.time() - before
            after_usage = agent.get_token_usage()

            delta_in = after_usage["input"] - before_usage["input"]
            delta_out = after_usage["output"] - before_usage["output"]
            delta_total = after_usage["total"] - before_usage["total"]

            print(f"助手: {response}")
            print(f"  [{elapsed:.2f}s | 本次 Token 输入:{delta_in} 输出:{delta_out} 总计:{delta_total} | 累计:{after_usage['total']}]")
            print()

            # 自动保存会话
            save_session(session_id, agent.messages)

        except KeyboardInterrupt:
            save_session(session_id, agent.messages)
            usage = agent.get_token_usage()
            print(f"\n本次会话 Token 统计:")
            print(f"  输入: {usage['input']}")
            print(f"  输出: {usage['output']}")
            print(f"  总计: {usage['total']}")
            print("\n会话已保存，再见!")
            break
        except Exception as e:
            print(f"发生错误: {e}")


if __name__ == "__main__":
    main()

