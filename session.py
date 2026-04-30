
import json
import random
import string
import datetime
from pathlib import Path


def get_session_dir():
    """获取会话存储目录"""
    session_dir = Path.home() / ".toolsagent" / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def save_session(session_id, messages):
    """保存会话历史"""
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
    except Exception:
        return False


def load_session(session_id):
    """加载会话历史"""
    session_dir = get_session_dir()
    session_path = session_dir / f"{session_id}.json"

    if not session_path.exists():
        return None

    try:
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("messages", [])
    except Exception:
        return None


def list_sessions():
    """列出所有会话"""
    session_dir = get_session_dir()
    sessions = []

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
            except Exception:
                pass
        # 按时间排序，最新的在前
        sessions.sort(key=lambda x: x["updated_at"], reverse=True)
        return sessions
    except Exception:
        return []


def delete_session(session_id):
    """删除会话"""
    session_dir = get_session_dir()
    session_path = session_dir / f"{session_id}.json"

    if session_path.exists():
        session_path.unlink()
        return True
    return False


def generate_session_id():
    """生成会话 ID（时间戳 + 4位随机后缀，避免同秒冲突）"""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = ''.join(random.choices(string.digits, k=4))
    return f"{ts}_{suffix}"

