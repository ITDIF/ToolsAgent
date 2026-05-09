#!/usr/bin/env python3
"""本地文件操作 Agent 入口点"""


def main():
    """主函数入口"""
    from src.cli.main import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()

