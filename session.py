
import json
import time
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_session_dir():
    """获取会话存储目录"""
    session_dir = Path.home() / ".toolsagent" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def save_session(session_id: str, messages: List[Dict[str, Any]]) -> bool:
    """保存会话历史

    Args:
        session_id: 会话 ID
        messages: 消息列表

    Returns:
        是否保存成功
    """
    session_dir = get_session_dir()
    session_path = session_dir / f"{session_id}.json"

    try:
        data = {
            "session_id": session_id,
            "updated_at": datetime.datetime.now().isoformat(),
            "messages": messages
        }
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("save_session(%s) failed: %s", session_id, e)
        return False


def load_session(session_id: str) -> Optional[List[Dict[str, Any]]]:
    """加载会话历史

    Args:
        session_id: 会话 ID

    Returns:
        消息列表，失败返回 None
    """
    session_dir = get_session_dir()
    session_path = session_dir / f"{session_id}.json"

    if not session_path.exists():
        return None

    try:
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])
    except Exception as e:
        logger.warning("load_session(%s) failed: %s", session_id, e)
        return None


def list_sessions() -> List[Dict[str, Any]]:
    """列出所有会话

    Returns:
        会话列表，按更新时间降序排列
    """
    session_dir = get_session_dir()
    sessions: List[Dict[str, Any]] = []

    try:
        for session_file in session_dir.glob("*.json"):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sessions.append({
                    "id": session_file.stem,
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(data.get("messages", []))
                })
            except Exception as e:
                logger.warning("skip session file %s: %s", session_file, e)
        # 按时间排序，最新的在前
        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions
    except Exception as e:
        logger.warning("list_sessions failed: %s", e)
        return []


def delete_session(session_id: str) -> bool:
    """删除会话

    Args:
        session_id: 会话 ID

    Returns:
        是否删除成功
    """
    session_dir = get_session_dir()
    session_path = session_dir / f"{session_id}.json"

    if session_path.exists():
        session_path.unlink()
        return True
    return False


def generate_session_id() -> str:
    """生成会话 ID（时间戳 + 性能计数器后缀，保证唯一性）

    Returns:
        会话 ID
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{time.perf_counter_ns()}"

