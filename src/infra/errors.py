"""
统一错误处理体系
定义统一的异常类、错误码和返回格式
"""
from enum import Enum
from typing import Dict, Any, Optional


class ErrorCode(Enum):
    """错误码枚举"""
    # 通用错误 1xxxx
    SUCCESS = 0, "成功"
    UNKNOWN_ERROR = 10001, "未知错误"
    INVALID_PARAMETER = 10002, "参数错误"
    PERMISSION_DENIED = 10003, "权限不足"
    TIMEOUT = 10004, "操作超时"
    NOT_IMPLEMENTED = 10005, "功能未实现"

    # 文件操作错误 2xxxx
    FILE_NOT_FOUND = 20001, "文件不存在"
    DIR_NOT_FOUND = 20002, "目录不存在"
    PATH_ALREADY_EXISTS = 20003, "路径已存在"
    PATH_IS_NOT_FILE = 20004, "路径不是文件"
    PATH_IS_NOT_DIR = 20005, "路径不是目录"
    FILE_READ_ERROR = 20006, "文件读取失败"
    FILE_WRITE_ERROR = 20007, "文件写入失败"
    FILE_DELETE_ERROR = 20008, "文件删除失败"
    FILE_MOVE_ERROR = 20009, "文件移动失败"
    FILE_COPY_ERROR = 20010, "文件复制失败"
    FILE_RENAME_ERROR = 20011, "文件重命名失败"
    CREATE_DIR_ERROR = 20012, "创建目录失败"

    # 安全相关错误 3xxxx
    PATH_NOT_SAFE = 30001, "路径不安全"
    SYMLINK_FORBIDDEN = 30002, "禁止操作符号链接"
    DRIVE_ROOT_FORBIDDEN = 30003, "禁止操作盘符根目录"
    NOT_IN_ALLOWED_ROOTS = 30004, "路径不在允许的根目录内"
    SYSTEM_DIR_FORBIDDEN = 30005, "禁止操作系统目录"
    SYSTEM_DIR_READ_FORBIDDEN = 30006, "禁止读取系统目录"

    # LLM相关错误 4xxxx
    LLM_API_ERROR = 40001, "LLM API调用失败"
    LLM_RESPONSE_PARSE_ERROR = 40002, "LLM响应解析失败"
    LLM_TOOL_CALL_ERROR = 40003, "工具调用错误"
    LLM_TOKEN_EXCEEDED = 40004, "Token超出限制"

    # 撤销相关错误 5xxxx
    UNDO_STACK_EMPTY = 50001, "撤销栈为空"
    UNDO_FAILED = 50002, "撤销失败"
    INVALID_UNDO_ACTION = 50003, "无效的撤销操作"

    # 批量操作错误 6xxxx
    BATCH_OPERATION_FAILED = 60001, "批量操作失败"
    BATCH_ROLLBACK_FAILED = 60002, "批量操作回滚失败"
    NESTED_BATCH_FORBIDDEN = 60003, "不允许嵌套批量操作"

    def __new__(cls, code: int, message: str):
        obj = object.__new__(cls)
        obj._value_ = code
        obj.message = message
        return obj


class BaseError(Exception):
    """基础异常类"""
    def __init__(
        self,
        code: ErrorCode,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message or code.message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "code": self.code.value,
            "error": self.code.name,
            "message": self.message,
            "details": self.details
        }


# 具体异常类
class ParameterError(BaseError):
    """参数错误"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.INVALID_PARAMETER, message, details)


class PermissionError(BaseError):
    """权限错误"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.PERMISSION_DENIED, message, details)


class TimeoutError(BaseError):
    """超时错误"""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(ErrorCode.TIMEOUT, message, details)


class PathSafetyError(BaseError):
    """路径安全错误"""
    def __init__(self, message: str, code: ErrorCode = ErrorCode.PATH_NOT_SAFE, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class FileOperationError(BaseError):
    """文件操作错误"""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class LLMError(BaseError):
    """LLM相关错误"""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class UndoError(BaseError):
    """撤销相关错误"""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


class BatchOperationError(BaseError):
    """批量操作错误"""
    def __init__(self, code: ErrorCode, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(code, message, details)


def success_response(data: Optional[Dict[str, Any]] = None, message: str = "操作成功") -> Dict[str, Any]:
    """构造成功响应"""
    return {
        "success": True,
        "code": ErrorCode.SUCCESS.value,
        "message": message,
        "data": data or {}
    }


def error_response(
    code: ErrorCode,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """构造错误响应"""
    return {
        "success": False,
        "code": code.value,
        "error": code.name,
        "message": message or code.message,
        "details": details or {}
    }


def exception_to_response(e: Exception) -> Dict[str, Any]:
    """将异常转换为统一响应格式"""
    if isinstance(e, BaseError):
        return {
            "success": False,
            "code": e.code.value,
            "error": e.code.name,
            "message": e.message,
            "details": e.details
        }
    else:
        return {
            "success": False,
            "code": ErrorCode.UNKNOWN_ERROR.value,
            "error": ErrorCode.UNKNOWN_ERROR.name,
            "message": str(e),
            "details": {}
        }
