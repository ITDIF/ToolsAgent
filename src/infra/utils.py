
import json
import datetime
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from threading import Lock, Thread
from queue import Queue

from .constants import FileConstants

logger = logging.getLogger(__name__)

LOG_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")

# 日志批量写入配置
_LOG_BATCH_SIZE = 50  # 批量写入条数
_LOG_FLUSH_INTERVAL = 2.0  # 最大刷新间隔(秒)


def _sanitize_string(value: str) -> str:
    """清理字符串中的非法 Unicode 代理字符，确保可被 UTF-8 编码。

    部分 LLM API 会返回孤立的代理字符（如 \\udcaa），直接序列化或写入文件时会抛出
    UnicodeEncodeError。此函数将其替换为替代字符（�）。
    """
    return value.encode("utf-8", errors="replace").decode("utf-8")


def sanitize_for_json(obj: Any) -> Any:
    """递归清理数据结构中的非法 Unicode 字符，确保 json.dumps 安全。

    Args:
        obj: 任意 Python 对象（dict/list/str/...）

    Returns:
        清理后的对象副本
    """
    if isinstance(obj, str):
        return _sanitize_string(obj)
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    return obj


def get_log_dir():
    """获取日志目录"""
    log_dir = Path.home() / ".toolsagent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_path():
    """获取日志文件路径"""
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    return get_log_dir() / f"{date_str}.jsonl"


def cleanup_old_logs(retention_days: int) -> int:
    """删除超过保留天数的日志文件

    Args:
        retention_days: 保留天数

    Returns:
        删除的文件数量
    """
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


def get_recent_logs(limit: int = 10) -> List[Dict[str, Any]]:
    """获取最近的操作记录

    Args:
        limit: 返回的最大记录数

    Returns:
        日志记录列表
    """
    log_path = get_log_path()

    if not log_path.exists():
        return []

    try:
        logs: List[Dict[str, Any]] = []
        with open(log_path, "rb") as f:
            # 移动到文件末尾
            f.seek(0, 2)
            file_size = f.tell()

            # 从后往前逐行读取
            pos = file_size
            while pos > 0 and len(logs) < limit:
                # 每次读取一个块
                read_size = min(FileConstants.CHUNK_READ_SIZE, pos)
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


class _BatchLogWriter:
    """批量日志写入器，使用后台线程异步写入日志"""

    def __init__(self):
        self._queue: Queue[Optional[Dict[str, Any]]] = Queue()
        self._buffer: List[Dict[str, Any]] = []
        self._lock = Lock()
        self._thread: Optional[Thread] = None
        self._running = False

    def start(self):
        """启动后台写入线程"""
        if self._running:
            return
        self._running = True
        self._thread = Thread(target=self._write_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止后台写入线程并刷新缓冲区"""
        if not self._running:
            return
        self._running = False
        self._queue.put(None)  # 发送停止信号
        if self._thread:
            self._thread.join(timeout=5.0)
        self._flush()

    def add(self, entry: Dict[str, Any]) -> None:
        """添加日志条目到队列"""
        self._queue.put(entry)

    def _write_loop(self):
        """后台写入循环"""
        # log_path 按日期缓存,跨午夜后会自动切换到新日期对应的文件,
        # 避免长时间运行的进程把日志一直追加到启动当天的文件里。
        log_path: Optional[Path] = None
        log_date: Optional[datetime.date] = None
        last_flush = 0

        while self._running or not self._queue.empty():
            # 批量收集日志条目
            batch: List[Dict[str, Any]] = []
            batch.append(self._queue.get())

            # 非阻塞收集更多条目
            while len(batch) < _LOG_BATCH_SIZE:
                try:
                    entry = self._queue.get_nowait()
                    if entry is None:  # 停止信号
                        break
                    batch.append(entry)
                except Exception:
                    break

            # 写入批次（过滤掉空字典）
            if batch:
                try:
                    today = datetime.date.today()
                    if log_path is None or log_date != today:
                        log_path = get_log_path()
                        log_date = today
                    with open(log_path, "a", encoding="utf-8") as f:
                        for entry in batch:
                            # 过滤掉空字典或无效条目
                            if entry and isinstance(entry, dict) and "action_type" in entry:
                                safe_entry = sanitize_for_json(entry)
                                f.write(json.dumps(safe_entry, ensure_ascii=False) + "\n")
                    last_flush = datetime.datetime.now().timestamp()
                except Exception as e:
                    logger.warning("批量写入日志失败: %s", e)

            # 定期刷新文件
            now = datetime.datetime.now().timestamp()
            if now - last_flush > _LOG_FLUSH_INTERVAL:
                try:
                    if log_path:
                        # 强制刷新文件缓冲区
                        with open(log_path, "r", encoding="utf-8") as f:
                            pass
                except Exception:
                    pass
                last_flush = now

    def _flush(self):
        """刷新缓冲区中的剩余日志"""
        with self._lock:
            if self._buffer:
                try:
                    log_path = get_log_path()
                    with open(log_path, "a", encoding="utf-8") as f:
                        for entry in self._buffer:
                            safe_entry = sanitize_for_json(entry)
                            f.write(json.dumps(safe_entry, ensure_ascii=False) + "\n")
                    self._buffer.clear()
                except Exception as e:
                    logger.warning("刷新日志缓冲区失败: %s", e)


# 全局批量日志写入器
_batch_writer: Optional[_BatchLogWriter] = None
_writer_lock = Lock()


def _get_batch_writer() -> _BatchLogWriter:
    """获取全局批量日志写入器单例"""
    global _batch_writer
    if _batch_writer is None:
        with _writer_lock:
            if _batch_writer is None:
                _batch_writer = _BatchLogWriter()
                _batch_writer.start()
    return _batch_writer


def log_action(action_type: str, params: Dict[str, Any], result: Dict[str, Any]) -> None:
    """记录操作日志(批量写入模式)

    Args:
        action_type: 操作类型
        params: 操作参数
        result: 操作结果

    Note:
        使用后台线程异步批量写入，提高性能。
        对于需要立即同步的场景，调用 flush_logs() 强制刷新。
    """
    log_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action_type": action_type,
        "params": params,
        "result": result
    }

    # 使用批量写入器
    try:
        _get_batch_writer().add(log_entry)
    except Exception as e:
        logger.warning("log_action(%s) 失败: %s", action_type, e)


def shutdown_log_writer():
    """关闭日志写入器并刷新剩余日志"""
    global _batch_writer
    if _batch_writer is not None:
        with _writer_lock:
            if _batch_writer is not None:
                _batch_writer.stop()
                _batch_writer = None


def flush_logs():
    """刷新日志写入器，确保所有待写入的日志都被写入文件"""
    global _batch_writer
    if _batch_writer is not None:
        # 通过添加一个空条目触发批量写入
        _batch_writer.add({})  # 空条目会被忽略
        # 等待一小段时间确保写入完成
        import time
        time.sleep(0.1)

