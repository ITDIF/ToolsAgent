"""
TUI 通信桥接层 —— 替代 main.py 中的全局变量与嵌套闭包。

职责：
  1. 启动 TCP 服务、等待 TUI 前端连接
  2. 线程安全地发送消息给前端
  3. 处理前端消息，分发到注册的回调
  4. 阻塞式确认协议：request_confirmation() 发送请求后等待前端响应
"""

import json
import logging
import socket
import threading
import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MSG_START = b"<<<MSG_START>>>"
MSG_END = b"<<<MSG_END>>>"


@dataclass
class _PendingConfirmation:
    """等待前端确认的请求"""
    event: threading.Event = field(default_factory=threading.Event)
    result: list = field(default_factory=list)  # result[0] = Optional[int]


class TuiBridge:
    """后端与 TUI 前端的通信桥接"""

    CONFIRMATION_TIMEOUT = 120.0  # 确认超时秒数

    def __init__(self):
        self._server_socket: Optional[socket.socket] = None
        self._client_socket: Optional[socket.socket] = None
        self._port: int = 0
        self._is_running: bool = False
        self._send_lock = threading.Lock()
        self._on_message_callback: Optional[Callable[[dict], None]] = None
        self._pending_confirmations: Dict[str, _PendingConfirmation] = {}
        self._recv_thread: Optional[threading.Thread] = None

    # ===== 生命周期 =====

    def start_server(self) -> int:
        """启动 TCP 服务，返回端口号"""
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.bind(('127.0.0.1', 0))
        self._server_socket.listen(1)
        self._port = self._server_socket.getsockname()[1]
        self._is_running = True
        return self._port

    def wait_for_connection(self, timeout: float = 30.0) -> None:
        """阻塞等待前端连接，超时抛出 TimeoutError"""
        if not self._server_socket:
            raise RuntimeError("服务未启动")
        self._server_socket.settimeout(timeout)
        try:
            self._client_socket, _ = self._server_socket.accept()
        except socket.timeout:
            raise TimeoutError(f"等待 TUI 前端连接超时（{timeout}s）")
        self._client_socket.settimeout(None)
        self._server_socket.settimeout(None)
        # 启动接收线程
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def close(self) -> None:
        """关闭所有连接"""
        self._is_running = False
        if self._client_socket:
            try:
                self._client_socket.close()
            except Exception:
                pass
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass

    @property
    def is_connected(self) -> bool:
        return self._client_socket is not None and self._is_running

    # ===== 消息发送 =====

    def send(self, msg_type: str, payload: dict) -> None:
        """线程安全地发送消息给前端"""
        if not self._client_socket:
            logger.warning("无法发送消息：客户端未连接")
            return
        message = {
            "id": str(uuid.uuid4()),
            "type": msg_type,
            "timestamp": int(time.time() * 1000),
            "payload": payload,
        }
        msg_str = f"{MSG_START.decode('utf-8')}\n{json.dumps(message, ensure_ascii=False)}\n{MSG_END.decode('utf-8')}\n"
        with self._send_lock:
            try:
                self._client_socket.sendall(msg_str.encode('utf-8'))
            except Exception as e:
                logger.error(f"发送消息给TUI失败: {e}")

    def send_thinking_update(self, elapsed: float, token_delta: int) -> None:
        """发送思考状态更新（时间、token变化）"""
        self.send("thinking_update", {
            "elapsed": elapsed,
            "tokenDelta": token_delta,
        })

    def send_thinking_start(self) -> None:
        """发送思考开始信号"""
        self.send("thinking_start", {})

    def send_thinking_end(self, elapsed: float, token_usage: dict) -> None:
        """发送思考结束信号"""
        self.send("thinking_end", {
            "elapsed": elapsed,
            "tokenUsage": token_usage,
        })

    # ===== 确认协议 =====

    def request_confirmation(self, title: str, options: List[str], default: int = 0) -> Optional[int]:
        """
        阻塞式确认请求。
        发送 confirmation_request 给前端，等待用户选择后返回选项索引。
        超时或取消返回 None。
        """
        request_id = str(uuid.uuid4())
        pending = _PendingConfirmation()
        self._pending_confirmations[request_id] = pending

        self.send("confirmation_request", {
            "requestId": request_id,
            "title": title,
            "options": options,
            "default": default,
        })

        if not pending.event.wait(timeout=self.CONFIRMATION_TIMEOUT):
            # 超时视为取消
            self._pending_confirmations.pop(request_id, None)
            logger.warning(f"确认请求超时: {request_id}")
            return None

        self._pending_confirmations.pop(request_id, None)
        return pending.result[0] if pending.result else None

    def _resolve_confirmation(self, request_id: str, choice_index: Optional[int]) -> None:
        """解析确认请求（由接收线程调用）"""
        pending = self._pending_confirmations.get(request_id)
        if pending:
            pending.result.append(choice_index)
            pending.event.set()

    # ===== 消息接收 =====

    def on_message(self, callback: Callable[[dict], None]) -> None:
        """注册前端消息处理器"""
        self._on_message_callback = callback

    def _recv_loop(self) -> None:
        """接收线程主循环"""
        buffer = b""
        while self._is_running:
            if not self._client_socket:
                break
            try:
                data = self._client_socket.recv(4096)
                if not data:
                    break
                buffer += data

                while True:
                    start_pos = buffer.find(MSG_START)
                    if start_pos == -1:
                        break
                    end_pos = buffer.find(MSG_END, start_pos + len(MSG_START))
                    if end_pos == -1:
                        break

                    msg_bytes = buffer[start_pos + len(MSG_START): end_pos]
                    buffer = buffer[end_pos + len(MSG_END):]

                    try:
                        msg_str = msg_bytes.decode('utf-8')
                        message = json.loads(msg_str)
                        self._handle_message(message)
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                        logger.error(f"解析TUI消息失败: {e}")
                        continue
            except Exception as e:
                if self._is_running:
                    logger.error(f"Socket接收异常: {e}")
                break

        logger.info("TUI接收线程退出")

    def _handle_message(self, message: dict) -> None:
        """分发前端消息"""
        msg_type = message.get("type")
        payload = message.get("payload", message)  # 兼容旧格式

        # 确认响应走专用通道
        if msg_type == "confirmation_response":
            request_id = payload.get("requestId", "")
            choice_index = payload.get("choiceIndex")
            if choice_index is not None:
                choice_index = int(choice_index)
            self._resolve_confirmation(request_id, choice_index)
            return

        # 其他消息转发给注册的回调
        if self._on_message_callback:
            self._on_message_callback(message)
