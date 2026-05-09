
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "tool_timeout": 30,
    "default_model": "mimo-v2.5",
    "log_retention_days": 30,
    "max_search_results": 100,
    "max_search_depth": 10,
    "max_tool_iterations": 8,
    "max_request_time": 300,
    "max_read_bytes": 1024 * 1024,
    "confirm_delete": True,
    "confirm_overwrite": True,
    "allowed_roots": [],
}

CONFIG_PATH = Path.home() / ".toolsagent" / "config.json"

_cached_config: Optional[Dict[str, Any]] = None
_cached_mtime: Optional[float] = None


def load_config() -> Dict[str, Any]:
    """加载配置，不存在则使用默认值

    Returns:
        配置字典
    """
    config = DEFAULT_CONFIG.copy()

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update(user_config)
        except Exception as e:
            logger.warning("load_config failed: %s", e)

    return config


def save_config(config: Dict[str, Any]) -> None:
    """保存配置

    Args:
        config: 配置字典
    """
    global _cached_config, _cached_mtime
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    _cached_config = None
    _cached_mtime = None


def get_config() -> Dict[str, Any]:
    """获取当前配置，带 mtime 缓存，避免频繁读盘

    Returns:
        配置字典的副本
    """
    global _cached_config, _cached_mtime
    mtime = None
    if CONFIG_PATH.exists():
        try:
            mtime = CONFIG_PATH.stat().st_mtime
        except Exception:
            pass
    if _cached_config is not None and _cached_mtime == mtime:
        return _cached_config.copy()
    _cached_config = load_config()
    _cached_mtime = mtime
    return _cached_config.copy()
