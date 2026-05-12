#!/usr/bin/env python3
"""
纯Python实现的ToolsAgent TUI界面，零依赖，风格类似Claude Code
支持现代终端的ANSI转义序列，兼容Windows Terminal/PowerShell/IDE内置终端
"""
import socket
import json
import sys
import os
import time
import threading
from typing import Dict, Any, List, Optional
# 消息边界（字节形式，用于直接在字节buffer中搜索）
MSG_START = b"<<<MSG_START>>>"
MSG_END = b"<<<MSG_END>>>"
MSG_START_STR = MSG_START.decode('utf-8')
MSG_END_STR = MSG_END.decode('utf-8')
# ANSI 颜色和样式
class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # 前景色
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    # 背景色
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"
    # 光标控制
    CLEAR_SCREEN = "\033[2J"
    CLEAR_LINE = "\033[2K"
    CURSOR_UP = "\033[{n}A"
    CURSOR_DOWN = "\033[{n}B"
    CURSOR_RIGHT = "\033[{n}C"
    CURSOR_LEFT = "\033[{n}D"
    CURSOR_HOME = "\033[H"
    CURSOR_SAVE = "\033[s"
    CURSOR_RESTORE = "\033[u"
    CURSOR_HIDE = "\033[?25l"
    CURSOR_SHOW = "\033[?25h"
# 图标（兼容纯文本终端，fallback为文字符号）
class Icon:
    # 带fallback的图标定义
    @staticmethod
    def USER() -> str:
        return Icon.get(f"{Style.BLUE}👤{Style.RESET} ", f"{Style.BLUE}U{Style.RESET} ")

    @staticmethod
    def ASSISTANT() -> str:
        return Icon.get(f"{Style.GREEN}🤖{Style.RESET} ", f"{Style.GREEN}A{Style.RESET} ")

    @staticmethod
    def SYSTEM() -> str:
        return Icon.get(f"{Style.YELLOW}ℹ️{Style.RESET} ", f"{Style.YELLOW}i{Style.RESET} ")

    @staticmethod
    def TOOL_RUNNING() -> str:
        return Icon.get(f"{Style.CYAN}⚙️{Style.RESET} ", f"{Style.CYAN}*{Style.RESET} ")

    @staticmethod
    def TOOL_SUCCESS() -> str:
        return Icon.get(f"{Style.GREEN}✅{Style.RESET} ", f"{Style.GREEN}+{Style.RESET} ")

    @staticmethod
    def TOOL_ERROR() -> str:
        return Icon.get(f"{Style.RED}❌{Style.RESET} ", f"{Style.RED}x{Style.RESET} ")

    @staticmethod
    def ERROR() -> str:
        return Icon.get(f"{Style.RED}❌{Style.RESET} ", f"{Style.RED}x{Style.RESET} ")

    @staticmethod
    def WARNING() -> str:
        return Icon.get(f"{Style.YELLOW}⚠️{Style.RESET} ", f"{Style.YELLOW}!{Style.RESET} ")

    @staticmethod
    def INFO() -> str:
        return Icon.get(f"{Style.BLUE}ℹ️{Style.RESET} ", f"{Style.BLUE}i{Style.RESET} ")

    @staticmethod
    def TIP() -> str:
        return Icon.get(f"{Style.CYAN}💡{Style.RESET} ", f"{Style.CYAN}$ {Style.RESET} ")

    @staticmethod
    def MODEL() -> str:
        return Icon.get(f"{Style.MAGENTA}🔄{Style.RESET} ", f"{Style.MAGENTA}@{Style.RESET} ")

    @staticmethod
    def TIME() -> str:
        return Icon.get(f"{Style.GRAY}⏱️{Style.RESET} ", f"{Style.GRAY}t{Style.RESET} ")

    @staticmethod
    def TOKEN() -> str:
        return Icon.get(f"{Style.GRAY}🔢{Style.RESET} ", f"{Style.GRAY}#{Style.RESET} ")

    @staticmethod
    def CONNECT() -> str:
        return Icon.get(f"{Style.BLUE}🔌{Style.RESET} ", f"{Style.BLUE}C{Style.RESET} ")

    @staticmethod
    def CHECK() -> str:
        return Icon.get(f"{Style.GREEN}✅{Style.RESET} ", f"{Style.GREEN}V{Style.RESET} ")

    @staticmethod
    def TARGET() -> str:
        return Icon.get(f"{Style.GREEN}🎯{Style.RESET} ", f"{Style.GREEN}>{Style.RESET} ")

    @staticmethod
    def IDEA() -> str:
        return Icon.get(f"{Style.CYAN}💡{Style.RESET} ", f"{Style.CYAN}?{Style.RESET} ")

    @staticmethod
    def BYE() -> str:
        return Icon.get(f"{Style.GREEN}👋{Style.RESET} ", f"{Style.GREEN}b{Style.RESET} ")

    @staticmethod
    def get(icon_text: str, fallback: str) -> str:
        """根据终端编码自动选择图标或fallback"""
        if sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
            return fallback
        # 检查Windows版本是否支持emoji
        if sys.platform == "win32":
            try:
                win_version = sys.getwindowsversion()
                # Windows 10 1607+ 才支持emoji
                if win_version.major < 10 or (win_version.major == 10 and win_version.build < 14393):
                    return fallback
            except:
                return fallback
        return icon_text
class Message:
    """消息基类"""
    def __init__(self, content: str, timestamp: Optional[float] = None):
        self.content = content
        self.timestamp = timestamp or time.time()
class UserMessage(Message):
    """用户消息"""
    def render(self, width: int) -> List[str]:
        lines = []
        # 极简用户消息风格，类似Claude Code
        header = f"{Style.BOLD}{Style.BLUE}>{Style.RESET} {Style.BOLD}You{Style.RESET}"
        lines.append(header)
        # 内容自动换行，左对齐
        content_lines = self.wrap_text(self.content, width - 2)
        for line in content_lines:
            lines.append(f"  {line}")
        lines.append("")
        return lines
    @staticmethod
    def wrap_text(text: str, width: int) -> List[str]:
        """简单的文本换行"""
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append("")
                continue
            current_line = []
            current_length = 0
            for word in paragraph.split(' '):
                word_length = len(word) + 1  # +1 for space
                if current_length + word_length <= width:
                    current_line.append(word)
                    current_length += word_length
                else:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                    current_length = len(word)
            if current_line:
                lines.append(' '.join(current_line))
        return lines
class AssistantMessage(Message):
    """助手回复消息"""
    def __init__(self, content: str, elapsed: float = 0, token_usage: Optional[Dict] = None, timestamp: Optional[float] = None):
        super().__init__(content, timestamp)
        self.elapsed = elapsed
        self.token_usage = token_usage or {}
    def render(self, width: int) -> List[str]:
        lines = []
        # 极简助手消息风格，类似Claude Code
        header = f"{Style.BOLD}{Style.GREEN}>{Style.RESET} {Style.BOLD}Assistant{Style.RESET}"
        # 元信息显示在右侧
        meta_info = []
        if self.elapsed > 0:
            meta_info.append(f"{self.elapsed:.2f}s")
        if self.token_usage and self.token_usage.get('total', 0) > 0:
            meta_info.append(f"+{self.token_usage['total']} tokens")

        if meta_info:
            meta_str = " · ".join(meta_info)
            # 计算填充让元信息右对齐
            padding = " " * max(0, width - len(header.replace(Style.RESET, "").replace(Style.BOLD, "").replace(Style.GREEN, "")) - len(meta_str) - 2)
            header += f"{padding}{Style.DIM}{meta_str}{Style.RESET}"

        lines.append(header)
        # 内容自动换行
        content_lines = UserMessage.wrap_text(self.content, width - 2)
        for line in content_lines:
            lines.append(f"  {line}")
        lines.append("")
        return lines
class SystemMessage(Message):
    """系统通知消息"""
    def render(self, width: int) -> List[str]:
        lines = []
        # 极简系统消息风格
        lines.append(f"{Style.DIM}• {self.content}{Style.RESET}")
        lines.append("")
        return lines
class ToolMessage(Message):
    """工具调用消息"""
    def __init__(self, status: str, tool_name: str, parameters: Optional[Dict] = None, result: Optional[Dict] = None, error: Optional[str] = None, content: str = "", timestamp: Optional[float] = None):
        super().__init__(content, timestamp)
        self.status = status  # running, success, error
        self.tool_name = tool_name
        self.parameters = parameters
        self.result = result
        self.error = error
    def render(self, width: int) -> List[str]:
        lines = []
        # 极简工具消息风格
        if self.status == "running":
            status_icon = Style.CYAN + "•" + Style.RESET
            status_color = Style.CYAN
        elif self.status == "success":
            status_icon = Style.GREEN + "✓" + Style.RESET
            status_color = Style.GREEN
        else:  # error
            status_icon = Style.RED + "✗" + Style.RESET
            status_color = Style.RED

        header = f"{status_icon} {status_color}{self.tool_name}{Style.RESET}"
        if self.content:
            header += f": {self.content}"
        lines.append(header)

        # 只在出错时显示详细错误信息
        if self.status == "error" and self.error:
            lines.append(f"  {Style.RED}{self.error}{Style.RESET}")
        lines.append("")
        return lines
class TUIApp:
    def __init__(self, port: int):
        self.port = port
        self.socket = None
        self.connected = False
        self.buffer = b""
        self.running = True
        self.messages: List[Message] = []
        self.current_input = ""
        self.input_cursor_pos = 0
        self.thinking = False
        self.thinking_animation_thread: Optional[threading.Thread] = None
        self.thinking_stop_event = threading.Event()
        self.terminal_width = 80
        self.terminal_height = 24
        self.scroll_offset = 0
        self.current_model = "Default Model"
        # 初始化终端
        self.init_terminal()
    def init_terminal(self) -> None:
        """初始化终端设置，完美兼容伪终端，类似Claude Code"""
        # 检测是否是TTY终端
        self.is_tty = sys.stdin.isatty() and sys.stdout.isatty()
        # Windows下特殊处理
        if sys.platform == "win32":
            try:
                # 设置控制台输出编码为UTF-8
                sys.stdout.reconfigure(encoding='utf-8')
                sys.stderr.reconfigure(encoding='utf-8')
            except:
                pass
            try:
                from ctypes import windll
                # 启用控制台虚拟终端处理
                windll.kernel32.SetConsoleMode(windll.kernel32.GetStdHandle(-11), 7)
                # 设置控制台代码页为UTF-8
                windll.kernel32.SetConsoleCP(65001)
                windll.kernel32.SetConsoleOutputCP(65001)
            except:
                # 启用失败也没关系，自动降级
                pass
        # 检测终端大小
        self.update_terminal_size()
        # 注册窗口大小改变信号
        if sys.platform != "win32":
            try:
                import signal
                signal.signal(signal.SIGWINCH, lambda sig, frame: self.update_terminal_size())
            except:
                pass
        # 隐藏光标
        if self.is_tty:
            print(Style.CURSOR_HIDE, end="", flush=True)
            # 清屏
            print(Style.CLEAR_SCREEN + Style.CURSOR_HOME, end="", flush=True)
        # 伪终端下不需要多余提示，直接进入交互，和Claude Code体验一致
    def update_terminal_size(self) -> None:
        """更新终端大小"""
        try:
            if sys.platform == "win32":
                # Windows下获取终端大小
                from ctypes import windll, create_string_buffer
                h = windll.kernel32.GetStdHandle(-11)
                csbi = create_string_buffer(22)
                res = windll.kernel32.GetConsoleScreenBufferInfo(h, csbi)
                if res:
                    import struct
                    (bufx, bufy, curx, cury, wattr, left, top, right, bottom, maxx, maxy) = struct.unpack("hhhhHhhhhhh", csbi.raw)
                    self.terminal_width = right - left + 1
                    self.terminal_height = bottom - top + 1
            else:
                # Unix/Linux/Mac下获取终端大小
                import fcntl
                import termios
                import struct
                res = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, struct.pack('HHHH', 0, 0, 0, 0))
                rows, cols, _, _ = struct.unpack('HHHH', res)
                self.terminal_width = cols
                self.terminal_height = rows
        except:
            # 获取失败使用默认值
            pass
    def cleanup_terminal(self) -> None:
        """清理终端设置"""
        print(Style.CURSOR_SHOW + Style.RESET, end="", flush=True)
        print("\n" + Style.CLEAR_LINE, end="", flush=True)
    def _print(self, text: str = "", end: str = "\n") -> None:
        """安全打印，处理编码问题"""
        try:
            print(text, end=end, flush=True)
        except UnicodeEncodeError:
            # 编码不支持时移除特殊字符
            cleaned_text = text.encode('ascii', errors='replace').decode('ascii')
            print(cleaned_text, end=end, flush=True)
    def render_header(self) -> str:
        """渲染顶部启动信息，类似Claude Code风格"""
        lines = []
        # 小图标 + 产品信息
        icon = Icon.get("🤖", ">>")
        lines.append(f"{Style.BOLD}{Style.YELLOW}{icon}{Style.RESET}  {Style.BOLD}ToolsAgent v1.0{Style.RESET}")
        # 模型信息
        lines.append(f"   {Style.DIM}{self.current_model} · Local File Operations{Style.RESET}")
        # 工作目录
        import os
        cwd = os.getcwd()
        lines.append(f"   {Style.DIM}{cwd}{Style.RESET}")
        # 分隔线
        lines.append(f"{Style.DIM}{'─' * self.terminal_width}{Style.RESET}")
        return "\n".join(lines) + "\n"
    def render_input_area(self) -> str:
        """渲染底部输入区域，Claude Code风格"""
        prompt = f"{Style.BOLD}{Style.WHITE}>{Style.RESET} "
        input_display = self.current_input
        # 处理光标位置
        cursor_prefix = input_display[:self.input_cursor_pos]
        cursor_suffix = input_display[self.input_cursor_pos:]
        # 简单光标，没有多余样式
        input_line = f"{prompt}{cursor_prefix}{Style.RESET}{cursor_suffix}"
        return input_line
    def render_messages(self) -> List[str]:
        """渲染所有消息，自动滚动到最新"""
        lines = []
        # 计算可用于消息显示的区域（减去头部、输入区域和分隔线）
        header_height = 4 if len(self.messages) <= 5 else 0  # 头部高度
        input_area_height = 3  # 输入区 + 2分隔线 + 底部提示
        available_height = self.terminal_height - header_height - input_area_height - 1

        if available_height <= 0:
            return []

        # 渲染所有消息
        all_lines = []
        for msg in self.messages:
            msg_lines = msg.render(self.terminal_width)
            all_lines.extend(msg_lines)

        # 处理滚动 - 默认显示最新的消息
        if len(all_lines) > available_height:
            start_idx = max(0, len(all_lines) - available_height + self.scroll_offset)
            visible_lines = all_lines[start_idx:start_idx + available_height]
        else:
            visible_lines = all_lines

        return visible_lines
    def render_thinking_indicator(self) -> str:
        """渲染思考指示器，Claude Code风格"""
        if not self.thinking:
            return ""
        # 极简思考动画
        animation_frames = [".", "..", "...", ".."]
        current_frame = animation_frames[int(time.time() * 2) % len(animation_frames)]
        return f"{Style.DIM}Thinking{current_frame}{Style.RESET}"
    def render(self) -> None:
        """渲染整个界面，Claude Code极简风格"""
        if not self.is_tty:
            # 非TTY环境下使用简单打印模式
            return
        try:
            # 清屏
            print(Style.CLEAR_SCREEN + Style.CURSOR_HOME, end="")

            # 渲染头部信息（仅首次显示，有新消息时不再重复）
            if len(self.messages) <= 5:  # 只在初始状态显示头部
                header = self.render_header()
                print(header, end="")

            # 渲染消息区域
            message_lines = self.render_messages()
            for line in message_lines:
                print(Style.CLEAR_LINE + line)

            # 渲染思考指示器
            thinking_line = self.render_thinking_indicator()
            if thinking_line:
                print(Style.CLEAR_LINE + thinking_line)
            else:
                # 填充空白行，让输入区域保持在底部
                available_height = self.terminal_height - 3  # 输入区高度
                current_lines = len(message_lines) + (1 if thinking_line else 0)
                for _ in range(max(0, available_height - current_lines)):
                    print(Style.CLEAR_LINE)

            # 输入区上分隔线
            print(f"{Style.DIM}{'─' * self.terminal_width}{Style.RESET}")

            # 渲染输入区域
            input_line = self.render_input_area()
            print(Style.CLEAR_LINE + input_line, end="")

            # 输入区下分隔线 + 底部提示
            print(f"\n{Style.DIM}{'─' * self.terminal_width}{Style.RESET}")
            print(f"{Style.DIM} ? for shortcuts · Ctrl+C to exit{Style.RESET}", end="")

            # 恢复光标位置到输入框
            prompt_length = 2  # "> "的长度
            # 移动光标回到输入行
            print(f"\033[{self.terminal_height - 2}A", end="")  # 上移2行到输入行
            print(f"\r{Style.CURSOR_RIGHT.replace('{n}', str(prompt_length + self.input_cursor_pos))}", end="", flush=True)
        except Exception as e:
            # 渲染失败时不崩溃
            pass
    def thinking_animation_loop(self) -> None:
        """思考动画线程"""
        while not self.thinking_stop_event.is_set():
            self.render()
            time.sleep(0.1)
    def start_thinking(self) -> None:
        """开始显示思考动画"""
        if self.thinking:
            return
        self.thinking = True
        self.thinking_stop_event.clear()
        self.thinking_animation_thread = threading.Thread(target=self.thinking_animation_loop, daemon=True)
        self.thinking_animation_thread.start()
    def stop_thinking(self) -> None:
        """停止显示思考动画"""
        self.thinking = False
        if self.thinking_animation_thread and self.thinking_animation_thread.is_alive():
            self.thinking_stop_event.set()
            self.thinking_animation_thread.join()
    def handle_message(self, message: Dict[str, Any]) -> None:
        """处理后端返回的消息，兼容伪终端模式"""
        msg_type = message.get("type")
        content = message.get("content", "")
        if msg_type == "assistant_msg":
            self.stop_thinking()
            elapsed = message.get("elapsed", 0)
            token_usage = message.get("token_usage", {})
            msg = AssistantMessage(content, elapsed=elapsed, token_usage=token_usage)
            if self.is_tty:
                self.messages.append(msg)
                self.render()
            else:
                # 兼容模式下直接打印
                self._print("\r" + " " * 50 + "\r")  # 清除思考状态
                for line in msg.render(self.terminal_width):
                    self._print(line)
        elif msg_type == "system_notify":
            msg = SystemMessage(content)
            if self.is_tty:
                self.messages.append(msg)
                self.render()
            else:
                for line in msg.render(self.terminal_width):
                    self._print(line)
        elif msg_type == "tool_call":
            status = message.get("status", "")
            tool_name = message.get("toolName", "")
            parameters = message.get("parameters")
            result = message.get("result")
            error = message.get("error")
            msg_content = message.get("content", "")
            msg = ToolMessage(status, tool_name, parameters, result, error, msg_content)
            if self.is_tty:
                self.messages.append(msg)
                self.render()
            else:
                for line in msg.render(self.terminal_width):
                    self._print(line)
        elif msg_type == "error":
            self.stop_thinking()
            msg = SystemMessage(f"{Icon.ERROR()}{content}")
            if self.is_tty:
                self.messages.append(msg)
                self.render()
            else:
                self._print("\r" + " " * 50 + "\r")  # 清除思考状态
                for line in msg.render(self.terminal_width):
                    self._print(line)
        elif msg_type == "model_update":
            self.current_model = message.get("model", "")
            # 模型更新不显示系统消息，只更新内部状态
            self.render()
    def receive_loop(self) -> None:
        """接收消息循环（正确的字节层面解析）"""
        while self.running and self.connected:
            try:
                data = self.socket.recv(4096)  # 增大缓冲区
                if not data:
                    break
                self.buffer += data
                # 在字节层面搜索消息边界，避免字节/字符索引不匹配问题
                while True:
                    # 查找消息开始标记
                    start_pos = self.buffer.find(MSG_START)
                    if start_pos == -1:
                        break  # 没有完整消息，继续接收
                    # 查找消息结束标记（从开始标记后面找）
                    end_pos = self.buffer.find(MSG_END, start_pos + len(MSG_START))
                    if end_pos == -1:
                        break  # 消息不完整，继续接收
                    # 提取消息内容（去掉开始和结束标记）
                    msg_bytes = self.buffer[start_pos + len(MSG_START) : end_pos]
                    # 移除已处理的部分（包括结束标记）
                    self.buffer = self.buffer[end_pos + len(MSG_END) :]
                    # 解码并解析JSON
                    try:
                        msg_str = msg_bytes.decode('utf-8')
                        message = json.loads(msg_str)
                        self.handle_message(message)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        # 解析失败，跳过这条坏消息
                        continue
            except Exception as e:
                self.messages.append(SystemMessage(f"{Icon.ERROR()}连接断开: {str(e)}"))
                self.render()
                self.connected = False
                break
    def send_message(self, msg_type: str, payload: Dict[str, Any]) -> None:
        """发送消息到后端"""
        if not self.connected or not self.socket:
            self.messages.append(SystemMessage(f"{Icon.ERROR()}后端连接断开，请重启应用"))
            self.render()
            return
        message = {
            "type": msg_type,
            "id": os.urandom(16).hex(),
            "timestamp": int(time.time() * 1000),
            **payload
        }
        msg_str = f"{MSG_START_STR}\n{json.dumps(message, ensure_ascii=False)}\n{MSG_END_STR}\n"
        try:
            self.socket.sendall(msg_str.encode('utf-8'))
        except Exception as e:
            self.messages.append(SystemMessage(f"{Icon.ERROR()}发送消息失败: {str(e)}"))
            self.render()
    def input_loop(self) -> None:
        """用户输入循环，跨平台兼容"""
        if sys.platform == "win32":
            # Windows系统下使用msvcrt读取键盘输入
            import msvcrt
            while self.running and self.connected:
                try:
                    if msvcrt.kbhit():
                        char = msvcrt.getwch()
                        if ord(char) == 3:  # Ctrl+C
                            self.running = False
                            break
                        elif ord(char) == 13:  # 回车
                            if self.current_input.strip():
                                # 发送用户消息
                                msg = UserMessage(self.current_input)
                                self.messages.append(msg)
                                self.send_message("user_input", {"content": self.current_input})
                                # 开始思考动画
                                self.start_thinking()
                                self.current_input = ""
                                self.input_cursor_pos = 0
                                self.render()
                        elif ord(char) == 8:  # 退格
                            if self.input_cursor_pos > 0:
                                self.current_input = self.current_input[:self.input_cursor_pos-1] + self.current_input[self.input_cursor_pos:]
                                self.input_cursor_pos -= 1
                                self.render()
                        elif ord(char) == 224:  # 特殊功能键前缀
                            next_char = msvcrt.getwch()
                            if next_char == 'M':  # 右箭头
                                if self.input_cursor_pos < len(self.current_input):
                                    self.input_cursor_pos += 1
                                    self.render()
                            elif next_char == 'K':  # 左箭头
                                if self.input_cursor_pos > 0:
                                    self.input_cursor_pos -= 1
                                    self.render()
                            elif next_char == 'H':  # 上箭头
                                self.scroll_offset += 1
                                self.render()
                            elif next_char == 'P':  # 下箭头
                                self.scroll_offset -= 1
                                if self.scroll_offset < 0:
                                    self.scroll_offset = 0
                                self.render()
                        else:
                            # 普通字符，插入到当前光标位置
                            if ord(char) >= 32:  # 可打印字符
                                self.current_input = self.current_input[:self.input_cursor_pos] + char + self.current_input[self.input_cursor_pos:]
                                self.input_cursor_pos += 1
                                self.render()
                    time.sleep(0.01)
                except KeyboardInterrupt:
                    self.running = False
                    break
        else:
            # Unix/Linux/Mac系统下使用termios
            import termios
            import tty
            original_terminal_settings = termios.tcgetattr(sys.stdin.fileno())
            try:
                tty.setcbreak(sys.stdin.fileno())
                while self.running and self.connected:
                    try:
                        # 读取单个字符
                        char = sys.stdin.read(1)
                        if not char:
                            continue
                        # 处理特殊字符
                        if ord(char) == 3:  # Ctrl+C
                            self.running = False
                            break
                        elif ord(char) == 13:  # 回车
                            if self.current_input.strip():
                                # 发送用户消息
                                msg = UserMessage(self.current_input)
                                self.messages.append(msg)
                                self.send_message("user_input", {"content": self.current_input})
                                # 开始思考动画
                                self.start_thinking()
                                self.current_input = ""
                                self.input_cursor_pos = 0
                                self.render()
                        elif ord(char) == 127 or ord(char) == 8:  # 退格或删除
                            if self.input_cursor_pos > 0:
                                self.current_input = self.current_input[:self.input_cursor_pos-1] + self.current_input[self.input_cursor_pos:]
                                self.input_cursor_pos -= 1
                                self.render()
                        elif ord(char) == 27:  # 箭头键等特殊序列
                            next_char = sys.stdin.read(1)
                            if next_char == '[':
                                direction = sys.stdin.read(1)
                                if direction == 'C':  # 右箭头
                                    if self.input_cursor_pos < len(self.current_input):
                                        self.input_cursor_pos += 1
                                        self.render()
                                elif direction == 'D':  # 左箭头
                                    if self.input_cursor_pos > 0:
                                        self.input_cursor_pos -= 1
                                        self.render()
                                elif direction == 'A':  # 上箭头
                                    self.scroll_offset += 1
                                    self.render()
                                elif direction == 'B':  # 下箭头
                                    self.scroll_offset -= 1
                                    if self.scroll_offset < 0:
                                        self.scroll_offset = 0
                                    self.render()
                        else:
                            # 普通字符，插入到当前光标位置
                            self.current_input = self.current_input[:self.input_cursor_pos] + char + self.current_input[self.input_cursor_pos:]
                            self.input_cursor_pos += 1
                            self.render()
                    except KeyboardInterrupt:
                        self.running = False
                        break
            finally:
                # 恢复终端设置
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, original_terminal_settings)
    def connect(self) -> bool:
        """连接后端服务"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect(("127.0.0.1", self.port))
            self.connected = True
            return True
        except Exception as e:
            self._print(f"{Icon.ERROR()}连接后端失败: {str(e)}")
            return False
    def run(self) -> None:
        """运行TUI，自动适配终端环境"""
        try:
            self.render()
            if not self.connect():
                return
            # 极简启动，没有多余欢迎消息
            self.render()
            # 启动接收线程
            receive_thread = threading.Thread(target=self.receive_loop, daemon=True)
            receive_thread.start()
            # 根据终端类型选择输入模式
            if self.is_tty:
                # 完整功能模式
                self.input_loop()
            else:
                # 伪终端兼容模式（类似Claude Code的IDE终端体验）
                self.compat_input_loop()
        finally:
            self.cleanup_terminal()
            # 清理
            if self.socket:
                self.socket.close()
            self._print(f"\n{Icon.INFO()}{Icon.BYE()} 再见！")
            sys.exit(0)
    def compat_input_loop(self) -> None:
        """伪终端兼容输入模式，Claude Code极简风格"""
        # 启动头部信息
        import os
        icon = Icon.get("🤖", ">>")
        self._print(f"{Style.BOLD}{Style.YELLOW}{icon}{Style.RESET}  {Style.BOLD}ToolsAgent v1.0{Style.RESET}")
        self._print(f"   {Style.DIM}{self.current_model} · Local File Operations{Style.RESET}")
        self._print(f"   {Style.DIM}{os.getcwd()}{Style.RESET}")
        self._print()

        while self.running and self.connected:
            try:
                # 显示提示符
                sys.stdout.write(f"{Style.BOLD}>{Style.RESET} ")
                sys.stdout.flush()
                # 读取整行输入
                line = input()
                content = line.strip()
                if content:
                    # 显示用户消息
                    msg = UserMessage(content)
                    for line in msg.render(self.terminal_width):
                        self._print(line)
                    # 发送消息
                    self.send_message("user_input", {"content": content})
                    # 显示思考状态
                    self._print(f"\n{Style.DIM}Thinking...{Style.RESET}", end="\r")
                    sys.stdout.flush()
            except KeyboardInterrupt:
                self._print()
                self._print(f"{Style.DIM}👋 再见！{Style.RESET}")
                self.running = False
                break
            except EOFError:
                break
def main():
    import argparse
    parser = argparse.ArgumentParser(description="ToolsAgent TUI")
    parser.add_argument("port", type=int, help="后端服务端口")
    args = parser.parse_args()
    app = TUIApp(args.port)
    app.run()
if __name__ == "__main__":
    main()
