
import json
import datetime
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

LOG_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")


def get_log_dir():
    """获取日志目录"""
    log_dir = Path.home() / ".toolsagent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_path():
    """获取日志文件路径"""
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return get_log_dir() / f"{date_str}.jsonl"


def cleanup_old_logs(retention_days):
    """删除超过保留天数的日志文件"""
    if not retention_days or retention_days <= 0:
        return 0
    cutoff = datetime.date.today() - datetime.timedelta(days=int(retention_days))
    log_dir = get_log_dir()
    removed = 0
    for f in log_dir.iterdir():
        m = LOG_FILENAME_RE.match(f.name)
        if not m:
            continue
        try:
            file_date = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if file_date < cutoff:
            try:
                f.unlink()
                removed += 1
            except Exception as e:
                logger.warning("failed to remove old log %s: %s", f, e)
    return removed


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
    except Exception as e:
        logger.warning("log_action(%s) failed: %s", action_type, e)


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
    except Exception as e:
        logger.warning("get_recent_logs failed: %s", e)
        return []

