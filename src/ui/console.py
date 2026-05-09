class Color:
    """终端颜色代码"""
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    GRAY = "\033[90m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# 保留向后兼容的便捷函数
def print_green(text: str) -> None:
    """打印绿色文本"""
    print(f"{Color.GREEN}{text}{Color.RESET}")


def print_red(text: str) -> None:
    """打印红色文本"""
    print(f"{Color.RED}{text}{Color.RESET}")


def print_yellow(text: str) -> None:
    """打印黄色文本"""
    print(f"{Color.YELLOW}{text}{Color.RESET}")


def print_gray(text: str) -> None:
    """打印灰色文本"""
    print(f"{Color.GRAY}{text}{Color.RESET}")


def print_bold(text: str) -> None:
    """打印加粗文本"""
    print(f"{Color.BOLD}{text}{Color.RESET}")
