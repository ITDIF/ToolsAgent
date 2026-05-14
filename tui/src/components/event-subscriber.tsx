import React, { useEffect } from 'react'
import { TypedEventBus } from '../bridge/event-bus.js'
import { useUiDispatch } from '../store/ui-store.js'
import { useMessageDispatch } from '../store/message-store.js'

/**
 * 将 EventBus 事件桥接到 React store dispatch。
 * 这是唯一一个直接访问 EventBus 的组件，其他组件只读 store。
 */
export function EventSubscriber({
  bus,
  children,
}: {
  bus: TypedEventBus
  children: React.ReactNode
}) {
  const dispatchUi = useUiDispatch()
  const dispatchMsg = useMessageDispatch()

  useEffect(() => {
    const unsubs: Array<() => void> = []

    unsubs.push(bus.on('connected', () => {
      dispatchUi({ type: 'SET_CONNECTED', connected: true })
    }))

    unsubs.push(bus.on('disconnected', () => {
      dispatchUi({ type: 'SET_CONNECTED', connected: false })
    }))

    unsubs.push(bus.on('ready', (payload) => {
      dispatchUi({ type: 'SET_MODEL', model: payload.model })
      dispatchUi({ type: 'SET_SESSION', sessionId: payload.sessionId })
    }))

    unsubs.push(bus.on('assistant_msg', (payload) => {
      dispatchMsg({
        type: 'ADD_ASSISTANT_MESSAGE',
        id: `asst_${Date.now()}`,
        content: payload.content,
        elapsed: payload.elapsed,
        tokenUsage: payload.tokenUsage,
      })
    }))

    unsubs.push(bus.on('tool_status', (payload) => {
      if (payload.status === 'running') {
        dispatchMsg({ type: 'ADD_TOOL_MESSAGE', payload })
      } else {
        dispatchMsg({
          type: 'UPDATE_TOOL_STATUS',
          id: payload.id,
          status: payload.status,
          result: payload.result,
          error: payload.error,
        })
      }
    }))

    unsubs.push(bus.on('thinking_start', () => {
      dispatchUi({ type: 'SET_THINKING', isThinking: true })
    }))

    unsubs.push(bus.on('thinking_update', (payload) => {
      dispatchUi({
        type: 'UPDATE_THINKING',
        elapsed: payload.elapsed,
        tokenDelta: payload.tokenDelta,
      })
    }))

    unsubs.push(bus.on('thinking_end', (payload) => {
      dispatchUi({ type: 'SET_THINKING', isThinking: false })
      dispatchUi({ type: 'ADD_TOKENS', tokens: payload.tokenUsage })
    }))

    unsubs.push(bus.on('confirmation_request', (payload) => {
      dispatchUi({ type: 'SET_CONFIRMATION', payload })
    }))

    unsubs.push(bus.on('system_notify', (payload) => {
      dispatchMsg({
        type: 'ADD_SYSTEM_MESSAGE',
        id: `sys_${Date.now()}`,
        content: payload.content,
        level: payload.level,
      })
    }))

    unsubs.push(bus.on('model_update', (payload) => {
      dispatchUi({ type: 'SET_MODEL', model: payload.model })
    }))

    unsubs.push(bus.on('error', (payload) => {
      dispatchMsg({
        type: 'ADD_ERROR_MESSAGE',
        id: `err_${Date.now()}`,
        content: payload.content,
      })
    }))

    unsubs.push(bus.on('exit', () => {
      process.exit(0)
    }))

    return () => unsubs.forEach(unsub => unsub())
  }, [bus, dispatchUi, dispatchMsg])

  return <>{children}</>
}
