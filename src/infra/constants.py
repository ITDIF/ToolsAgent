"""项目常量定义"""


class ConfigDefaults:
    """配置默认值"""
    TOOL_TIMEOUT = 30
    LOG_RETENTION_DAYS = 30
    MAX_SEARCH_RESULTS = 100
    MAX_SEARCH_DEPTH = 10
    MAX_TOOL_ITERATIONS = 8
    MAX_REQUEST_TIME = 300
    MAX_READ_BYTES = 1024 * 1024  # 1MB
    SCAN_MAX_WORKERS = 4  # 磁盘扫描最大并发数


class LLMConstants:
    """LLM 相关常量"""
    MAX_TOKENS = 4096
    TIMEOUT = 60.0
    MAX_RETRIES = 3


class UndoConstants:
    """撤销相关常量"""
    MAX_UNDO = 50
    BACKUP_MAX_AGE_HOURS = 24
    SECONDS_PER_HOUR = 3600
    MAX_BACKUP_SIZE = 100 * 1024 * 1024  # 最大备份大小100MB，避免磁盘耗尽


class FileConstants:
    """文件操作常量"""
    BYTES_PER_KB = 1024
    CHUNK_READ_SIZE = 8192


class UIConstants:
    """UI 相关常量"""
    KEY_SEQUENCE_TIMEOUT_MS = 50