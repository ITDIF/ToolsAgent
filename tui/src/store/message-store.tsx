import React, { createContext, useContext, useReducer, type Dispatch } from 'react'
import type { ToolStatusPayload } from '../bridge/protocol.js'

// ===== 消息类型 =====

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  timestamp: number
  // tool 专有
  toolName?: string
  toolStatus?: 'running' | 'success' | 'error' | 'info'
  toolDescription?: string
  toolParameters?: Record<string, unknown>
  toolResult?: Record<string, unknown>
  toolError?: string
  // assistant 专有
  elapsed?: number
  tokenUsage?: { input: number; output: number; total: number }
  // system 专有
  level?: 'info' | 'warn' | 'error'
}

export interface MessageState {
  messages: Message[]
}

const initialState: MessageState = {
  messages: [],
}

export type MessageAction =
  | { type: 'ADD_USER_MESSAGE'; id: string; content: string }
  | { type: 'ADD_ASSISTANT_MESSAGE'; id: string; content: string; elapsed: number; tokenUsage: { input: number; output: number; total: number } }
  | { type: 'ADD_TOOL_MESSAGE'; payload: ToolStatusPayload }
  | { type: 'UPDATE_TOOL_STATUS'; id: string; status: string; result?: Record<string, unknown>; error?: string }
  | { type: 'ADD_SYSTEM_MESSAGE'; id: string; content: string; level: string }
  | { type: 'ADD_ERROR_MESSAGE'; id: string; content: string }

function messageReducer(state: MessageState, action: MessageAction): MessageState {
  switch (action.type) {
    case 'ADD_USER_MESSAGE':
      return {
        messages: [...state.messages, {
          id: action.id,
          role: 'user',
          content: action.content,
          timestamp: Date.now(),
        }],
      }

    case 'ADD_ASSISTANT_MESSAGE':
      return {
        messages: [...state.messages, {
          id: action.id,
          role: 'assistant',
          content: action.content,
          timestamp: Date.now(),
          elapsed: action.elapsed,
          tokenUsage: action.tokenUsage,
        }],
      }

    case 'ADD_TOOL_MESSAGE':
      return {
        messages: [...state.messages, {
          id: action.payload.id,
          role: 'tool',
          content: action.payload.description,
          timestamp: Date.now(),
          toolName: action.payload.toolName,
          toolStatus: action.payload.status as Message['toolStatus'],
          toolDescription: action.payload.description,
          toolParameters: action.payload.parameters,
        }],
      }

    case 'UPDATE_TOOL_STATUS': {
      const messages = state.messages.map(m => {
        if (m.id === action.id) {
          return {
            ...m,
            toolStatus: action.status as Message['toolStatus'],
            toolResult: action.result,
            toolError: action.error,
          }
        }
        return m
      })
      // 如果没找到对应消息，创建一条
      if (!messages.find(m => m.id === action.id)) {
        return {
          messages: [...messages, {
            id: action.id,
            role: 'tool' as const,
            content: action.error || '完成',
            timestamp: Date.now(),
            toolStatus: action.status as Message['toolStatus'],
            toolResult: action.result,
            toolError: action.error,
          }],
        }
      }
      return { messages }
    }

    case 'ADD_SYSTEM_MESSAGE':
      return {
        messages: [...state.messages, {
          id: action.id,
          role: 'system',
          content: action.content,
          timestamp: Date.now(),
          level: action.level as Message['level'],
        }],
      }

    case 'ADD_ERROR_MESSAGE':
      return {
        messages: [...state.messages, {
          id: action.id,
          role: 'system',
          content: action.content,
          timestamp: Date.now(),
          level: 'error',
        }],
      }

    default:
      return state
  }
}

// ===== Context =====

const MessageStateContext = createContext<MessageState>(initialState)
const MessageDispatchContext = createContext<Dispatch<MessageAction>>(() => {})

export function MessageStoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(messageReducer, initialState)
  return (
    <MessageStateContext.Provider value={state}>
      <MessageDispatchContext.Provider value={dispatch}>
        {children}
      </MessageDispatchContext.Provider>
    </MessageStateContext.Provider>
  )
}

export function useMessageState(): MessageState {
  return useContext(MessageStateContext)
}

export function useMessageDispatch(): Dispatch<MessageAction> {
  return useContext(MessageDispatchContext)
}
