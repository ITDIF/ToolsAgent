from typing import NamedTuple


class Color(NamedTuple):
    green: str = "\033[32m"
    red: str = "\033[31m"
    yellow: str = "\033[33m"
    gray: str = "\033[90m"
    bold: str = "\033[1m"
    reset: str = "\033[0m"


# 控制台颜色常量
_COLOR = Color()


def get_color() -> Color:
    """获取当前颜色配置"""
    return _COLOR


def print_green(text: str) -> None:
    """打印绿色文本"""
    print(f"{_COLOR.green}{text}{_COLOR.reset}")


def print_red(text: str) -> None:
    """打印红色文本"""
    print(f"{_COLOR.red}{text}{_COLOR.reset}")


def print_yellow(text: str) -> None:
    """打印黄色文本"""
    print(f"{_COLOR.yellow}{text}{_COLOR.reset}")


def print_gray(text: str) -> None:
    """打印灰色文本"""
    print(f"{_COLOR.gray}{text}{_COLOR.reset}")


def print_bold(text: str) -> None:
    """打印加粗文本"""
    print(f"{_COLOR.bold}{text}{_COLOR.reset}")
