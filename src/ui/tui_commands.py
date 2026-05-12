"""
TUI 模式命令处理器。

每个处理器通过 bridge 发送结果给前端，不直接 print。
"""

import logging
import os
import time
from typing import TYPE_CHECKING, Optional

from ..infra.session import save_session, load_session, list_sessions, generate_session_id
from ..infra.utils import get_recent_logs
from ..security.undo import undo_last, set_active_session, get_undo_history

if TYPE_CHECKING:
    from ..core.agent import FileAgent
    from .tui_bridge import TuiBridge

logger = logging.getLogger(__name__)


def handle_help(bridge: 'TuiBridge') -> None:
    """发送帮助信息"""
    bridge.send("assistant_msg", {
        "content": (
            "可用命令:\n"
            "  /help, /h        显示帮助信息\n"
            "  /model, /m       切换模型\n"
            "  /undo [N], /u    撤销最近 N 次文件操作\n"
            "  /undo-list, /ul  查看可撤销的操作历史\n"
            "  /history, /his   加载历史会话\n"
            "  /logs, /log, /l  查看操作日志\n"
            "  /save, /s        保存当前会话\n"
            "  /auth            查看/管理工具授权\n"
            "  /exit, /q        退出程序"
        ),
        "elapsed": 0,
        "tokenUsage": {"input": 0, "output": 0, "total": 0},
    })


def handle_model_switch(bridge: 'TuiBridge', agent: 'FileAgent') -> None:
    """通过 TUI 确认弹窗切换模型"""
    from ..cli.main import MODEL_PROVIDERS, _build_provider
    keys = list(MODEL_PROVIDERS.keys())
    names = [MODEL_PROVIDERS[k]['name'] for k in keys]

    choice = bridge.request_confirmation("选择模型:", names, default=0)
    if choice is None:
        bridge.send("system_notify", {"content": "已取消模型切换", "level": "info"})
        return

    key = keys[choice]
    info = MODEL_PROVIDERS[key]

    # 需要接入点的模型
    if info["needs_endpoint"]:
        endpoint = bridge.request_confirmation(
            f"请输入{info['name']}接入点 ID:",
            ["使用默认接入点", "取消"],
            default=0,
        )
        if choice is None or choice != 0:
            bridge.send("system_notify", {"content": "已取消模型切换", "level": "info"})
            return
        model_name = ""
    else:
        model_name = info.get("default_model", "")

    api_key = os.getenv(info["env_key"])
    if not api_key:
        bridge.send("error", {"content": f"未设置环境变量: {info['env_key']}"})
        return

    kwargs: dict = {"api_key": api_key, "model": model_name}
    if info.get("base_url_env"):
        kwargs["base_url"] = os.getenv(info["base_url_env"], info.get("base_url_default"))

    try:
        new_provider = info["class"](**kwargs)
        agent.llm = new_provider
        model_name = getattr(new_provider, 'model', str(new_provider))
        bridge.send("model_update", {"model": model_name})
        bridge.send("assistant_msg", {
            "content": f"模型已切换为: {model_name}",
            "elapsed": 0,
            "tokenUsage": {"input": 0, "output": 0, "total": 0},
        })
    except Exception as e:
        bridge.send("error", {"content": f"创建 Provider 失败: {e}"})


def handle_undo(bridge: 'TuiBridge', agent: 'FileAgent', count: int = 1) -> None:
    """撤销操作"""
    set_active_session(agent.session_id)
    result = undo_last(count=count)
    bridge.send("undo_result", {
        "success": result.get("success", False),
        "results": result.get("results", []),
        "error": result.get("error"),
    })


def handle_undo_list(bridge: 'TuiBridge', agent: 'FileAgent') -> None:
    """查看撤销历史"""
    set_active_session(agent.session_id)
    h = get_undo_history()
    if not h["items"]:
        bridge.send("system_notify", {"content": "撤销栈为空", "level": "info"})
    else:
        lines = [f"撤销栈 ({h['count']} 条):"]
        for it in h["items"]:
            lines.append(f"  {it['index']}. [{it['type']}] {it['description']}")
        bridge.send("system_notify", {"content": "\n".join(lines), "level": "info"})


def handle_history(bridge: 'TuiBridge', agent: 'FileAgent') -> None:
    """加载历史会话"""
    sessions = list_sessions()
    if not sessions:
        bridge.send("system_notify", {"content": "没有历史会话", "level": "info"})
        return

    names = [
        f"{s['id']} ({s['message_count']}条消息, {s['updated_at']})"
        for s in sessions[:20]
    ]
    names.append("取消")

    choice = bridge.request_confirmation("选择会话:", names, default=0)
    if choice is None or choice >= len(sessions):
        bridge.send("system_notify", {"content": "已取消", "level": "info"})
        return

    sid = sessions[choice]['id']
    msgs = load_session(sid)
    if msgs is not None:
        agent.set_session(sid)
        agent.messages = msgs
        bridge.send("session_info", {"sessionId": sid, "messageCount": len(msgs)})
        bridge.send("system_notify", {"content": f"已加载会话: {sid}", "level": "info"})
    else:
        bridge.send("error", {"content": "加载会话失败"})


def handle_logs(bridge: 'TuiBridge') -> None:
    """查看操作日志"""
    logs = get_recent_logs(20)
    if not logs:
        bridge.send("system_notify", {"content": "没有操作记录", "level": "info"})
        return
    lines = ["最近操作记录:"]
    for log in logs:
        result = log.get('result', {})
        mark = "✓" if result.get('success') else "✗"
        lines.append(f"  [{log['timestamp']}] {mark} {log['action_type']}")
    bridge.send("system_notify", {"content": "\n".join(lines), "level": "info"})


def handle_auth(bridge: 'TuiBridge', agent: 'FileAgent') -> None:
    """管理工具授权"""
    granted = sorted(agent.session_authorized_tools)
    if not granted:
        bridge.send("system_notify", {"content": "本次会话尚无工具授权", "level": "info"})
        return

    lines = [f"本次会话已授权的工具 ({len(granted)} 个):"]
    for i, tool in enumerate(granted, 1):
        lines.append(f"  {i}. {tool}")

    options = ["全部清空", "取消"]
    choice = bridge.request_confirmation(
        "\n".join(lines) + "\n\n选择操作:",
        options,
        default=1,
    )

    if choice == 0:
        n = agent.revoke_session_authorizations()
        bridge.send("system_notify", {"content": f"已清空 {n} 条会话授权", "level": "info"})


def handle_save(bridge: 'TuiBridge', session_id: str, agent: 'FileAgent') -> None:
    """保存会话"""
    save_session(session_id, agent.messages)
    bridge.send("system_notify", {"content": "会话已保存", "level": "info"})


def dispatch_command(bridge: 'TuiBridge', agent: 'FileAgent', session_id: str, name: str, args: dict) -> None:
    """命令路由"""
    if name in ("help", "h"):
        handle_help(bridge)
    elif name in ("model", "m"):
        handle_model_switch(bridge, agent)
    elif name in ("undo", "u"):
        count = 1
        if args and args.get("count"):
            try:
                count = max(1, int(args["count"]))
            except (ValueError, TypeError):
                pass
        handle_undo(bridge, agent, count)
    elif name in ("undo-list", "undolist", "ul"):
        handle_undo_list(bridge, agent)
    elif name in ("history", "his"):
        handle_history(bridge, agent)
    elif name in ("logs", "log", "l"):
        handle_logs(bridge)
    elif name == "auth":
        handle_auth(bridge, agent)
    elif name in ("save", "s"):
        handle_save(bridge, session_id, agent)
    else:
        bridge.send("error", {"content": f"未知命令: /{name}"})
