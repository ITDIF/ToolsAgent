
import os
import re
import sys
from pathlib import Path


class PathSafetyError(Exception):
    """路径安全校验失败"""
    pass


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
    return [
        "/",
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
    """解析为绝对路径,即便目标不存在也能推断"""
    p = Path(path)
    try:
        return p.resolve(strict=False)
    except Exception:
        return p.absolute()


def _is_under(child: Path, parent: Path) -> bool:
    """child 是否等于或位于 parent 之下(不区分大小写,Windows 常见情形)"""
    try:
        child_str = str(child).lower() if sys.platform == "win32" else str(child)
        parent_str = str(parent).lower() if sys.platform == "win32" else str(parent)
        if child_str == parent_str:
            return True
        sep = "\\" if sys.platform == "win32" else "/"
        return child_str.startswith(parent_str.rstrip(sep) + sep)
    except Exception:
        return False


def _is_drive_root(path: Path) -> bool:
    """是否是盘符根(如 C:\\)"""
    if sys.platform != "win32":
        return str(path) == "/"
    s = str(path)
    return bool(re.match(r"^[a-zA-Z]:[/\\]?$", s))


def assert_safe_write_path(path, config=None):
    """
    校验路径是否允许写入(创建/修改/删除)。

    规则:
    - 拒绝符号链接(避免解析后绕过沙箱)
    - 若 config.allowed_roots 非空: 只允许在白名单目录内
    - 否则: 只要不落在 blocked_roots/盘符根 即可

    Raises:
        PathSafetyError: 校验不通过时
    """
    if os.path.islink(path):
        raise PathSafetyError(f"禁止操作符号链接: {path}")

    target = _resolve(path)
    cfg = config or {}

    if _is_drive_root(target):
        raise PathSafetyError(f"禁止操作盘符根目录: {path}")

    allowed_roots = cfg.get("allowed_roots") or []
    if allowed_roots:
        roots = [_resolve(r) for r in allowed_roots]
        if not any(_is_under(target, r) for r in roots):
            raise PathSafetyError(
                f"路径不在允许的根目录内: {path} (allowed_roots={allowed_roots})"
            )
        return

    blocked = cfg.get("blocked_roots")
    if blocked is None:
        blocked = _default_blocked_roots()
    for b in blocked:
        if _is_under(target, _resolve(b)):
            raise PathSafetyError(f"禁止操作系统目录: {path} (命中 {b})")
