"""界面交互包，包含控制台输出和用户授权"""

from .console import (
    print_green, print_red, print_yellow, print_gray, print_bold, get_color
)
from .prompts import select_operation, select_allow_once
from .tui import select_option, read_key

