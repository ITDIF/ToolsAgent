"""跨平台终端 TUI 工具:单键读取 + 方向键单选菜单。

仅依赖标准库:Windows 真 console 走 msvcrt,POSIX 走 termios + select。
非真 console 环境(如 Git Bash/mintty、被重定向的 stdin)自动 fallback 到
数字+回车输入,保证可用性。
"""

import sys
from typing import List, Optional


# ANSI 转义码
_CLEAR_LINE = "\033[2K"
_MOVE_UP = "\033[1A"
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"
_GREEN = "\033[32m"
_GRAY = "\033[90m"
_RESET = "\033[0m"


def _read_key_windows() -> Optional[str]:
    """Windows 单键读取,返回逻辑键名"""
    import msvcrt
    ch = msvcrt.getwch()
    # 方向键/功能键前缀
    if ch in ("\x00", "\xe0"):
        ch2 = msvcrt.getwch()
        if ch2 == "H":
            return "UP"
        if ch2 == "P":
            return "DOWN"
        return None
    if ch == "\r":
        return "ENTER"
    if ch == "\x1b":
        return "ESC"
    if ch == "\x03":
        raise KeyboardInterrupt
    return ch


def _read_key_posix() -> Optional[str]:
    """POSIX 单键读取,返回逻辑键名"""
    import termios
    import tty
    import select as _sel

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            # 50ms 内有后续输入则视为方向键转义序列;否则单 ESC
            r, _, _ = _sel.select([sys.stdin], [], [], 0.05)
            if not r:
                return "ESC"
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return "UP"
                if ch3 == "B":
                    return "DOWN"
            return None
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_key() -> Optional[str]:
    """跨平台读取一个按键,返回 'UP'/'DOWN'/'ENTER'/'ESC' 或单字符,Ctrl+C 抛 KeyboardInterrupt"""
    if sys.platform == "win32":
        return _read_key_windows()
    return _read_key_posix()


def _can_use_arrow_keys() -> bool:
    """检测当前终端是否支持方向键单键交互。
    - stdin/stdout 任一不是 tty: 不支持
    - Windows: 必须是真 console handle (Git Bash/mintty 不是,会失败)
    - POSIX: isatty 已足够
    """
    try:
        if not sys.stdout.isatty() or not sys.stdin.isatty():
            return False
    except Exception:
        return False

    if sys.platform == "win32":
        try:
            import msvcrt
            import ctypes
            from ctypes import wintypes
            handle = msvcrt.get_osfhandle(sys.stdin.fileno())
            mode = wintypes.DWORD()
            # GetConsoleMode 仅对真 Windows console 句柄成功
            return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
        except Exception:
            return False
    return True


def _select_option_arrow(title: str, options: List[str], default: int = 0) -> Optional[int]:
    """方向键单选菜单(真 console 模式)"""
    idx = max(0, min(default, len(options) - 1))
    n_lines = len(options) + 1  # 选项 + 提示行

    sys.stdout.write(f"{title}\n")
    sys.stdout.write(_HIDE_CURSOR)
    sys.stdout.flush()

    first = True
    try:
        while True:
            if not first:
                sys.stdout.write(_MOVE_UP * n_lines)
            first = False

            for i, opt in enumerate(options):
                arrow = f"{_GREEN}>{_RESET}" if i == idx else " "
                radio = f"{_GREEN}[×]{_RESET}" if i == idx else "[ ]"
                sys.stdout.write(f"\r{_CLEAR_LINE}  {arrow} {radio} {opt}\n")
            sys.stdout.write(
                f"\r{_CLEAR_LINE}  {_GRAY}↑/↓ 选择   ⏎ 确认   ESC 取消{_RESET}\n"
            )
            sys.stdout.flush()

            try:
                key = read_key()
            except KeyboardInterrupt:
                return None

            if key == "UP":
                idx = (idx - 1) % len(options)
            elif key == "DOWN":
                idx = (idx + 1) % len(options)
            elif key == "ENTER":
                return idx
            elif key == "ESC":
                return None
    finally:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()


def _select_option_fallback(title: str, options: List[str], default: int = 0) -> Optional[int]:
    """数字+回车 fallback(适用于 Git Bash/mintty 等非真 console)"""
    idx = max(0, min(default, len(options) - 1))
    print(title)
    for i, opt in enumerate(options, 1):
        suffix = f"  {_GRAY}(默认){_RESET}" if i - 1 == idx else ""
        print(f"  {_GREEN}{i}{_RESET}) {opt}{suffix}")
    while True:
        try:
            raw = input(f"  请选择 [1-{len(options)}] (回车=默认): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if raw == "":
            return idx
        try:
            n = int(raw)
            if 1 <= n <= len(options):
                return n - 1
        except ValueError:
            pass
        print(f"  {_GRAY}无效输入,请重新选择{_RESET}")


def select_option(title: str, options: List[str], default: int = 0) -> Optional[int]:
    """方向键单选菜单。
    返回选中项索引;ESC / Ctrl+C 取消时返回 None。
    在不支持方向键的终端(如 Git Bash/mintty)自动 fallback 到数字+回车输入。
    """
    if not options:
        return None
    if _can_use_arrow_keys():
        return _select_option_arrow(title, options, default)
    return _select_option_fallback(title, options, default)
