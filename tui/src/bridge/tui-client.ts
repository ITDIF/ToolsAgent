import * as net from 'node:net'
import { TypedEventBus } from './event-bus.js'
import {
  type Envelope,
  type MessageType,
  MSG_START,
  MSG_END,
  serializeEnvelope,
  parseEnvelope,
} from './protocol.js'

// ===== TCP 客户端 =====

export class TuiClient {
  private socket: net.Socket | null = null
  private bus: TypedEventBus
  private buffer = ''
  private _connected = false

  constructor(bus: TypedEventBus) {
    this.bus = bus
  }

  get connected(): boolean {
    return this._connected
  }

  /** 连接后端 */
  connect(host: string, port: number): Promise<void> {
    return new Promise((resolve, reject) => {
      this.socket = net.connect({ host, port }, () => {
        this._connected = true
        this.bus.emit('connected')
        resolve()
      })

      this.socket.on('data', (data) => this.processData(data))

      this.socket.on('error', (err) => {
        this._connected = false
        reject(err)
      })

      this.socket.on('close', () => {
        this._connected = false
        this.bus.emit('disconnected', '连接关闭')
      })
    })
  }

  /** 断开连接 */
  disconnect(): void {
    if (this.socket) {
      this.socket.destroy()
      this.socket = null
      this._connected = false
    }
  }

  // ===== 发送方法 =====

  /** 发送原始消息 */
  private send(type: MessageType, payload: Record<string, unknown>): void {
    if (!this.socket || !this._connected) return
    const env: Envelope = {
      id: crypto.randomUUID(),
      type,
      timestamp: Date.now(),
      payload,
    }
    this.socket.write(serializeEnvelope(env))
  }

  /** 发送用户输入 */
  sendUserInput(content: string): void {
    this.send('user_input', { content })
  }

  /** 发送确认响应 */
  sendConfirmationResponse(requestId: string, choiceIndex: number | null): void {
    this.send('confirmation_response', { requestId, choiceIndex })
  }

  /** 发送斜杠命令 */
  sendCommand(name: string, args?: Record<string, unknown>): void {
    this.send('command', { name, ...args })
  }

  /** 发送取消 */
  sendCancel(requestId?: string): void {
    this.send('cancel', { requestId })
  }

  // ===== 帧解析 =====

  private processData(data: Buffer): void {
    this.buffer += data.toString('utf-8')

    while (true) {
      const startIdx = this.buffer.indexOf(MSG_START)
      if (startIdx === -1) break

      const endIdx = this.buffer.indexOf(MSG_END, startIdx + MSG_START.length)
      if (endIdx === -1) break

      const raw = this.buffer.slice(startIdx + MSG_START.length, endIdx).trim()
      this.buffer = this.buffer.slice(endIdx + MSG_END.length)

      const envelope = parseEnvelope(raw)
      if (envelope) {
        this.dispatchMessage(envelope)
      }
    }
  }

  /** 将 envelope 路由到 EventBus */
  private dispatchMessage(env: Envelope): void {
    const { type, payload } = env
    switch (type) {
      case 'ready':
        this.bus.emit('ready', payload as any)
        break
      case 'assistant_msg':
        this.bus.emit('assistant_msg', payload as any)
        break
      case 'tool_status':
        this.bus.emit('tool_status', payload as any)
        break
      case 'thinking_start':
        this.bus.emit('thinking_start')
        break
      case 'thinking_update':
        this.bus.emit('thinking_update', payload as any)
        break
      case 'thinking_end':
        this.bus.emit('thinking_end', payload as any)
        break
      case 'confirmation_request':
        this.bus.emit('confirmation_request', payload as any)
        break
      case 'system_notify':
        this.bus.emit('system_notify', payload as any)
        break
      case 'model_update':
        this.bus.emit('model_update', payload as any)
        break
      case 'error':
        this.bus.emit('error', payload as any)
        break
      case 'undo_result':
        this.bus.emit('undo_result', payload as any)
        break
      case 'session_info':
        this.bus.emit('session_info', payload as any)
        break
      case 'exit':
        this.bus.emit('exit')
        process.exit(0)
        break
      default:
        break
    }
  }
}
