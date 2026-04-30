
import json
import datetime
from pathlib import Path


def get_log_path():
    """获取日志文件路径"""
    log_dir = Path.home() / ".toolsagent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return log_dir / f"{date_str}.jsonl"


def log_action(action_type, params, result):
    """记录操作日志"""
    log_path = get_log_path()

    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action_type": action_type,
        "params": params,
        "result": result
    }

    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 静默失败，不影响主流程


def get_recent_logs(limit=10):
    """获取最近的操作记录"""
    log_path = get_log_path()

    if not log_path.exists():
        return []

    try:
        logs = []
        with open(log_path, "rb") as f:
            # 移动到文件末尾
            f.seek(0, 2)
            file_size = f.tell()

            # 从后往前逐行读取
            pos = file_size
            while pos > 0 and len(logs) < limit:
                # 每次读取一个块
                read_size = min(8192, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size).decode("utf-8", errors="ignore")

                # 按换行符分割，处理最后一行可能不完整
                lines = chunk.split("\n")
                if pos > 0 and lines:
                    lines = lines[1:]  # 跳过第一行（可能不完整）

                for line in reversed(lines):
                    line = line.strip()
                    if line:
                        logs.append(json.loads(line))
                        if len(logs) >= limit:
                            break

        return logs
    except Exception:
        return []

