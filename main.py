
import os
import sys
import io
from dotenv import load_dotenv

# 在 Windows 上设置标准输出为 UTF-8 以正确显示中文
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from providers import ClaudeProvider, KimiProvider, DoubaoProvider, GlmProvider, XiaomiProvider
from agent import FileAgent
from session import generate_session_id, save_session, load_session, list_sessions
from utils import get_recent_logs
from config import get_config


# 模型名称到 Provider 的映射
MODEL_PROVIDERS = {
    "claude": {
        "class": ClaudeProvider,
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-3-5-sonnet-20241022",
        "name": "Claude (Anthropic)"
    },
    "moonshot": {
        "class": KimiProvider,
        "env_key": "KIMI_API_KEY",
        "default_model": "moonshot-v1-8k",
        "name": "Kimi (月之暗面)"
    },
    "kimi": {
        "class": KimiProvider,
        "env_key": "KIMI_API_KEY",
        "default_model": "moonshot-v1-8k",
        "name": "Kimi (月之暗面)"
    },
    "doubao": {
        "class": DoubaoProvider,
        "env_key": "DOUBAO_API_KEY",
        "default_model": "",  # 豆包需要手动输入 Endpoint ID
        "name": "豆包 (字节跳动)"
    },
    "glm": {
        "class": GlmProvider,
        "env_key": "GLM_API_KEY",
        "default_model": "glm-4",
        "name": "GLM (智谱 AI)"
    },
    "xiaomi": {
        "class": XiaomiProvider,
        "env_key": "XIAOMI_API_KEY",
        "default_model": "mimo-v2.5",
        "name": "小米 (MIMO)"
    },
    "mimo": {
        "class": XiaomiProvider,
        "env_key": "XIAOMI_API_KEY",
        "default_model": "mimo-v2.5",
        "name": "小米 (MIMO)"
    },
}


def create_provider(model_name):
    """
    根据模型名称创建对应的 Provider

    Args:
        model_name: 模型名称，如 "claude", "moonshot-v1-8k", "mimo-v2.5"

    Returns:
        Provider 实例，如果创建失败返回 None
    """
    # 查找匹配的 provider
    provider_key = None
    for key in MODEL_PROVIDERS:
        if model_name.lower().startswith(key):
            provider_key = key
            break

    if not provider_key:
        print(f"未知的模型: {model_name}")
        return None

    provider_config = MODEL_PROVIDERS[provider_key]
    api_key = os.getenv(provider_config["env_key"])

    if not api_key:
        print(f"未设置环境变量: {provider_config['env_key']}")
        return None

    try:
        if provider_key in ["doubao"]:
            # 豆包需要手动输入 Endpoint ID
            endpoint_id = input(f"请输入豆包接入点 ID (Endpoint ID): ").strip()
            if not endpoint_id:
                print("必须输入豆包接入点 ID")
                return None
            base_url = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
            return provider_config["class"](api_key=api_key, model=endpoint_id, base_url=base_url)
        elif provider_key in ["xiaomi", "mimo"]:
            base_url = os.getenv("XIAOMI_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
            return provider_config["class"](api_key=api_key, model=model_name, base_url=base_url)
        else:
            return provider_config["class"](api_key=api_key, model=model_name)
    except Exception as e:
        print(f"创建 Provider 失败: {e}")
        return None


def select_model():
    """选择模型选择"""
    print("请选择模型:")
    print("1. Claude (Anthropic)")
    print("2. Kimi (月之暗面)")
    print("3. 豆包 (字节跳动)")
    print("4. GLM (智谱 AI)")
    print("5. 小米 (MIMO)")

    choice = input("请输入选项 (1-5): ").strip()

    if choice == "1":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("请先在 .env 文件中设置 ANTHROPIC_API_KEY")
            return None
        model = input("请输入模型名称 (默认 claude-3-5-sonnet-20241022): ").strip()
        model = model or "claude-3-5-sonnet-20241022"
        return ClaudeProvider(api_key=api_key, model=model)
    elif choice == "2":
        api_key = os.getenv("KIMI_API_KEY")
        if not api_key:
            print("请先在 .env 文件中设置 KIMI_API_KEY")
            return None
        model = input("请输入模型名称 (默认 moonshot-v1-8k): ").strip()
        model = model or "moonshot-v1-8k"
        return KimiProvider(api_key=api_key, model=model)
    elif choice == "3":
        api_key = os.getenv("DOUBAO_API_KEY")
        if not api_key:
            print("请先在 .env 文件中设置 DOUBAO_API_KEY")
            return None
        model = input("请输入模型接入点 ID (Endpoint ID): ").strip()
        if not model:
            print("请输入豆包接入点 ID")
            return None
        base_url = os.getenv("DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
        return DoubaoProvider(api_key=api_key, model=model, base_url=base_url)
    elif choice == "4":
        api_key = os.getenv("GLM_API_KEY")
        if not api_key:
            print("请先在 .env 文件中设置 GLM_API_KEY")
            return None
        model = input("请输入模型名称 (默认 glm-4): ").strip()
        model = model or "glm-4"
        return GlmProvider(api_key=api_key, model=model)
    elif choice == "5":
        api_key = os.getenv("XIAOMI_API_KEY")
        if not api_key:
            print("请先在 .env 文件中设置 XIAOMI_API_KEY")
            return None
        model = input("请输入模型名称 (默认 mimo-v2.5): ").strip()
        model = model or "mimo-v2.5"
        base_url = os.getenv("XIAOMI_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
        return XiaomiProvider(api_key=api_key, model=model, base_url=base_url)
    else:
        print("无效选项")
        return None


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

            response = agent.process(user_input)
            print(f"助手: {response}")
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

