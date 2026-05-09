"""安全与可逆性包，包含路径安全和撤销管理"""

from .sandbox import assert_safe_write_path, PathSafetyError
from .undo import (
    push_undo,
    get_undo_history,
    undo_last,
    clear_undo_stack,
    get_active_session,
    set_active_session,
)

__all__ = [
    "assert_safe_write_path",
    "PathSafetyError",
    "push_undo",
    "get_undo_history",
    "undo_last",
    "clear_undo_stack",
    "get_active_session",
    "set_active_session",
]
