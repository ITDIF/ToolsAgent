import React, { createContext, useContext, useReducer, type Dispatch } from 'react'
import type { ConfirmationRequestPayload } from '../bridge/protocol.js'

// ===== UI 状态 =====

export interface UiState {
  connected: boolean
  model: string
  sessionId: string
  isThinking: boolean
  pendingConfirmation: ConfirmationRequestPayload | null
  themeName: string
  terminalMode: 'full' | 'fallback'
  totalTokens: { input: number; output: number; total: number }
}

const initialUiState: UiState = {
  connected: false,
  model: '',
  sessionId: '',
  isThinking: false,
  pendingConfirmation: null,
  themeName: 'dark',
  terminalMode: 'full',
  totalTokens: { input: 0, output: 0, total: 0 },
}

export type UiAction =
  | { type: 'SET_CONNECTED'; connected: boolean }
  | { type: 'SET_MODEL'; model: string }
  | { type: 'SET_SESSION'; sessionId: string }
  | { type: 'SET_THINKING'; isThinking: boolean }
  | { type: 'SET_CONFIRMATION'; payload: ConfirmationRequestPayload | null }
  | { type: 'SET_THEME'; themeName: string }
  | { type: 'SET_TERMINAL_MODE'; mode: 'full' | 'fallback' }
  | { type: 'ADD_TOKENS'; tokens: { input: number; output: number; total: number } }

function uiReducer(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case 'SET_CONNECTED':
      return { ...state, connected: action.connected }
    case 'SET_MODEL':
      return { ...state, model: action.model }
    case 'SET_SESSION':
      return { ...state, sessionId: action.sessionId }
    case 'SET_THINKING':
      return { ...state, isThinking: action.isThinking }
    case 'SET_CONFIRMATION':
      return { ...state, pendingConfirmation: action.payload }
    case 'SET_THEME':
      return { ...state, themeName: action.themeName }
    case 'SET_TERMINAL_MODE':
      return { ...state, terminalMode: action.mode }
    case 'ADD_TOKENS':
      return {
        ...state,
        totalTokens: {
          input: state.totalTokens.input + action.tokens.input,
          output: state.totalTokens.output + action.tokens.output,
          total: state.totalTokens.total + action.tokens.total,
        },
      }
    default:
      return state
  }
}

// ===== Context =====

const UiStateContext = createContext<UiState>(initialUiState)
const UiDispatchContext = createContext<Dispatch<UiAction>>(() => {})

export function UiStoreProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(uiReducer, initialUiState)
  return (
    <UiStateContext.Provider value={state}>
      <UiDispatchContext.Provider value={dispatch}>
        {children}
      </UiDispatchContext.Provider>
    </UiStateContext.Provider>
  )
}

export function useUiState(): UiState {
  return useContext(UiStateContext)
}

export function useUiDispatch(): Dispatch<UiAction> {
  return useContext(UiDispatchContext)
}
