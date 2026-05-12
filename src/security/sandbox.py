import os
import sys
import re
from pathlib import Path
from typing import Optional, List, Union
class PathSafetyError(Exception):
    """路径安全校验失败"""
    def __init__(self, message: str, type: Optional[str] = None):
        super().__init__(message)
        self.type = type
class PathSafetyErrorType:
    """路径安全错误类型常量"""
    SYMLINK_FORBIDDEN = "symlink_forbidden"
    DRIVE_ROOT_FORBIDDEN = "drive_root_forbidden"
    NOT_IN_ALLOWED_ROOTS = "not_in_allowed_roots"
    SYSTEM_DIR_FORBIDDEN = "system_dir_forbidden"
def _default_blocked_roots():
    """返回平台相关的禁止写入目录列表"""
    if sys.platform == "win32":
        return [
            r"C:\Windows",
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            r"C:\ProgramData",
            r"C:\System Volume Information",
            r"C:\Recovery",
            r"C:\$Recycle.Bin",
        ]
    # 注意: 不要把 "/" 放进黑名单。
    # 1) `_is_drive_root` 已经拦截裸 "/" 路径;
    # 2) `_is_under(child, "/")` 对任意绝对路径都成立,放进来会导致全拒。
    return [
        "/etc",
        "/usr",
        "/bin",
        "/sbin",
        "/boot",
        "/var",
        "/lib",
        "/lib64",
        "/sys",
        "/proc",
        "/dev",
    ]
def _resolve(path):
    """解析为绝对路径，即便目标不存在也能推断"""
    p = Path(path)
    try:
        return p.resolve(strict=False)
    except Exception:
        return p.absolute()
def _is_under(child: Path, parent: Path) -> bool:
    """child 是否等于或位于 parent 之下（不区分大小写，Windows 常见情形）"""
    try:
        # 两个都是已经解析过的绝对路径，通过路径部件判断从属关系
        # 避免字符串前缀匹配导致的短路径绕过问题
        parent_parts = parent.parts
        child_parts = child.parts
        if len(child_parts) < len(parent_parts):
            return False
        # Windows 路径不区分大小写
        if sys.platform == "win32":
            return all(c.lower() == p.lower() for c, p in zip(child_parts[:len(parent_parts)], parent_parts))
        else:
            return child_parts[:len(parent_parts)] == parent_parts
    except Exception:
        return False
def _is_drive_root(path: Path) -> bool:
    """是否是盘符根（如 C:\\）"""
    if sys.platform != "win32":
        return str(path) == "/"
    s = str(path)
    return bool(re.match(r"^[a-zA-Z]:[/\\]?$", s))
def assert_safe_write_path(path: Union[str, Path], config: Optional[dict] = None) -> None:
    """
    校验路径是否允许写入（创建/修改/删除）。
    规则：
    - 拒绝符号链接（避免解析后绕过沙箱）
    - 若 config.allowed_roots 非空：只允许在白名单目录内
    - 否则：只要不落在 blocked_roots/盘符根即可
    Args:
        path: 待校验的路径
        config: 配置字典，包含 allowed_roots 和 blocked_roots
    Raises:
        PathSafetyError: 校验不通过时，包含错误类型和详细信息
    """
    path_str = str(path)
    # 先解析路径为真实路径（解析所有符号链接）
    target = _resolve(path)
    # 检查原始路径是否是存在的符号链接
    if os.path.exists(path) and os.path.islink(path):
        raise PathSafetyError(
            f"禁止操作符号链接: {path}", PathSafetyErrorType.SYMLINK_FORBIDDEN
        )
    cfg = config or {}
    # 检查是否为盘符根目录
    if _is_drive_root(target):
        raise PathSafetyError(
            f"禁止操作盘符根目录: {path_str}", PathSafetyErrorType.DRIVE_ROOT_FORBIDDEN
        )
    # 白名单模式
    allowed_roots: List[str] = cfg.get("allowed_roots") or []
    if allowed_roots:
        roots = [_resolve(r) for r in allowed_roots]
        if not any(_is_under(target, r) for r in roots):
            raise PathSafetyError(
                f"路径不在允许的根目录内: {path_str} (allowed_roots={allowed_roots})",
                PathSafetyErrorType.NOT_IN_ALLOWED_ROOTS,
            )
        return
    # 黑名单模式
    blocked: Optional[List[str]] = cfg.get("blocked_roots")
    if blocked is None:
        blocked = _default_blocked_roots()
    for b in blocked:
        if _is_under(target, _resolve(b)):
            raise PathSafetyError(
                f"禁止操作系统目录: {path_str} (命中 {b})",
                PathSafetyErrorType.SYSTEM_DIR_FORBIDDEN,
            )
