"""统一的日志配置模块。

使用示例：
    from src.infra.logging_config import configure_logging
    configure_logging(level=logging.INFO)
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def configure_logging(
    level: int = logging.INFO,
    log_dir: Optional[Path] = None,
    log_to_file: bool = True,
    log_to_console: bool = True,
) -> None:
    """配置统一的日志系统。

    Args:
        level: 日志级别，默认 INFO
        log_dir: 日志文件目录，默认 ~/.toolsagent/logs
        log_to_file: 是否写入日志文件
        log_to_console: 是否输出到控制台
    """
    handlers: list[logging.Handler] = []

    # 日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    if log_to_file and log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        date_str = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"app_{date_str}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # 配置根日志器
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True,  # 强制重新配置，覆盖之前的设置
    )
