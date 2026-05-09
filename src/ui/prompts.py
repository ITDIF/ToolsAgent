import sys
from typing import List, Optional


# 重用原来的 tui.py 中的功能
from .tui import select_option as _select_option


def select_operation(prompt: str) -> Optional[int]:
    """显示操作选择菜单并返回用户选择

    Args:
        prompt: 提示文本

    Returns:
        选中的索引，0=本次允许，1=本次会话允许，2=取消，None=中断
    """
    options = ["本次允许", "本次会话允许", "取消"]
    return _select_option(prompt, options, default=0)


def select_allow_once() -> bool:
    """快捷函数：询问用户是否允许本次操作"""
    result = select_operation("请选择操作")
    return result == 0
