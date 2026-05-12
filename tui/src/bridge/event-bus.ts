import { EventEmitter } from 'events'
import type {
  ReadyPayload,
  AssistantMsgPayload,
  ToolStatusPayload,
  ThinkingEndPayload,
  ConfirmationRequestPayload,
  SystemNotifyPayload,
  ModelUpdatePayload,
  ErrorPayload,
  UndoResultPayload,
  SessionInfoPayload,
} from './protocol.js'

// ===== 类型安全事件映射 =====

export interface EventMap {
  connected: []
  disconnected: [reason: string]
  ready: [payload: ReadyPayload]
  assistant_msg: [payload: AssistantMsgPayload]
  tool_status: [payload: ToolStatusPayload]
  thinking_start: []
  thinking_end: [payload: ThinkingEndPayload]
  confirmation_request: [payload: ConfirmationRequestPayload]
  system_notify: [payload: SystemNotifyPayload]
  model_update: [payload: ModelUpdatePayload]
  error: [payload: ErrorPayload]
  undo_result: [payload: UndoResultPayload]
  session_info: [payload: SessionInfoPayload]
}

export type EventKey = keyof EventMap

type EventHandler<K extends EventKey> = (...args: EventMap[K]) => void

// ===== 类型安全事件总线 =====

export class TypedEventBus {
  private emitter = new EventEmitter()

  on<K extends EventKey>(event: K, handler: EventHandler<K>): () => void {
    this.emitter.on(event, handler)
    return () => this.emitter.off(event, handler)
  }

  off<K extends EventKey>(event: K, handler: EventHandler<K>): void {
    this.emitter.off(event, handler)
  }

  emit<K extends EventKey>(event: K, ...args: EventMap[K]): void {
    this.emitter.emit(event, ...args)
  }

  removeAllListeners(event?: EventKey): void {
    this.emitter.removeAllListeners(event)
  }
}
