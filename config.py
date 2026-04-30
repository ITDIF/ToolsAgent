
import json
from pathlib import Path

DEFAULT_CONFIG = {
    "tool_timeout": 30,
    "default_model": "mimo-v2.5",
    "log_retention_days": 30,
    "max_search_results": 100,
    "confirm_delete": True,
    "confirm_overwrite": True,
}

CONFIG_PATH = Path.home() / ".toolsagent" / "config.json"


def load_config():
    """加载配置，不存在则使用默认值"""
    config = DEFAULT_CONFIG.copy()

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            config.update(user_config)
        except Exception:
            pass

    return config


def save_config(config):
    """保存配置"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_config():
    """获取当前配置"""
    return load_config()
