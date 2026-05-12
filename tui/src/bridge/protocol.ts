// ===== 消息协议定义 =====

/** 消息类型枚举 */
export type ServerMessageType =
  | 'ready'
  | 'assistant_msg'
  | 'tool_status'
  | 'thinking_start'
  | 'thinking_end'
  | 'confirmation_request'
  | 'system_notify'
  | 'model_update'
  | 'error'
  | 'undo_result'
  | 'session_info'

export type ClientMessageType =
  | 'user_input'
  | 'confirmation_response'
  | 'command'
  | 'cancel'

export type MessageType = ServerMessageType | ClientMessageType

// ===== Payload 类型 =====

export interface ReadyPayload {
  model: string
  sessionId: string
}

export interface AssistantMsgPayload {
  content: string
  elapsed: number
  tokenUsage: { input: number; output: number; total: number }
}

export interface ToolStatusPayload {
  id: string
  toolName: string
  status: 'running' | 'success' | 'error' | 'info'
  description: string
  parameters?: Record<string, unknown>
  result?: Record<string, unknown>
  error?: string
}

export interface ThinkingEndPayload {
  elapsed: number
  tokenUsage: { input: number; output: number; total: number }
}

export interface ConfirmationRequestPayload {
  requestId: string
  title: string
  options: string[]
  default: number
}

export interface SystemNotifyPayload {
  content: string
  level: 'info' | 'warn' | 'error'
}

export interface ModelUpdatePayload {
  model: string
}

export interface ErrorPayload {
  content: string
  code?: string
}

export interface UndoResultPayload {
  success: boolean
  results: Array<{
    success: boolean
    message: string | Record<string, unknown>
    error?: string
  }>
  error?: string
}

export interface SessionInfoPayload {
  sessionId: string
  messageCount: number
}

export interface UserInputPayload {
  content: string
}

export interface ConfirmationResponsePayload {
  requestId: string
  choiceIndex: number | null
}

export interface CommandPayload {
  name: string
  args?: Record<string, unknown>
}

export interface CancelPayload {
  requestId?: string
}

// ===== 消息信封 =====

export interface Envelope {
  id: string
  type: MessageType
  timestamp: number
  payload: Record<string, unknown>
}

// ===== 帧标记 =====

export const MSG_START = '<<<MSG_START>>>'
export const MSG_END = '<<<MSG_END>>>'

// ===== 序列化/反序列化 =====

export function serializeEnvelope(env: Envelope): string {
  return `${MSG_START}\n${JSON.stringify(env)}\n${MSG_END}\n`
}

export function parseEnvelope(raw: string): Envelope | null {
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed.type === 'string') {
      return parsed as Envelope
    }
    return null
  } catch {
    return null
  }
}
