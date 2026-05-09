
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

from .constants import ConfigDefaults

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: Dict[str, Any] = {
    "tool_timeout": ConfigDefaults.TOOL_TIMEOUT,
    "default_model": "mimo-v2.5",
    "log_retention_days": ConfigDefaults.LOG_RETENTION_DAYS,
    "max_search_results": ConfigDefaults.MAX_SEARCH_RESULTS,
    "max_search_depth": ConfigDefaults.MAX_SEARCH_DEPTH,
    "max_tool_iterations": ConfigDefaults.MAX_TOOL_ITERATIONS,
    "max_request_time": ConfigDefaults.MAX_REQUEST_TIME,
    "max_read_bytes": ConfigDefaults.MAX_READ_BYTES,
    "confirm_delete": True,
    "confirm_overwrite": True,
    "allowed_roots": [],
}

CONFIG_PATH = Path.home() / ".toolsagent" / "config.json"

_cached_config: Optional[Dict[str, Any]] = None
_cached_mtime: Optional[float] = None


# 配置验证规则: (类型, 最小值, 最大值)
_CONFIG_VALIDATORS: Dict[str, tuple] = {
    "tool_timeout": (int, 1, 3600),
    "log_retention_days": (int, 1, 365),
    "max_search_results": (int, 1, 10000),
    "max_search_depth": (int, 1, 100),
    "max_tool_iterations": (int, 1, 50),
    "max_request_time": (int, 1, 3600),
    "max_read_bytes": (int, 1, 100 * 1024 * 1024),  # 最大 100MB
    "confirm_delete": (bool, None, None),
    "confirm_overwrite": (bool, None, None),
    "allowed_roots": (list, None, None),
}


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """验证并修正配置项。

    Args:
        config: 原始配置字典

    Returns:
        验证后的配置字典，无效值会被替换为默认值
    """
    validated = DEFAULT_CONFIG.copy()
    validated.update(config)

    errors = []
    for key, (expected_type, min_val, max_val) in _CONFIG_VALIDATORS.items():
        if key not in validated:
            continue
        value = validated[key]

        # 类型检查
        if expected_type == int and isinstance(value, float):
            value = int(value)
            validated[key] = value
        elif not isinstance(value, expected_type):
            errors.append(f"{key} 类型错误: 期望 {expected_type.__name__}, 实际 {type(value).__name__}")
            validated[key] = DEFAULT_CONFIG[key]
            continue

        # 范围检查
        if expected_type in (int, float) and min_val is not None and max_val is not None:
            if value < min_val or value > max_val:
                errors.append(f"{key} 值越界: {value} (范围 [{min_val}, {max_val}])")
                validated[key] = DEFAULT_CONFIG[key]

    if errors:
        for error in errors:
            logger.warning("配置验证错误: %s", error)

    return validated


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
            config = validate_config(config)
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
