import React, { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import { TuiClient } from '../../bridge/tui-client.js'
import { useMessageDispatch } from '../../store/message-store.js'
import { useUiState } from '../../store/ui-store.js'
import { useTheme } from '../../theme/context.js'

export function PromptInput({ client }: { client: TuiClient }) {
  const [input, setInput] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [historyIdx, setHistoryIdx] = useState(-1)
  const { isThinking, pendingConfirmation } = useUiState()
  const dispatchMsg = useMessageDispatch()
  const { theme } = useTheme()

  useInput((ch, key) => {
    // 有确认弹窗时，输入由 ConfirmationOverlay 处理
    if (pendingConfirmation) return

    if (key.return) {
      const content = input.trim()
      if (!content) return

      // 记录历史
      setHistory(prev => [...prev, content])
      setHistoryIdx(-1)

      // 添加用户消息到 store
      dispatchMsg({ type: 'ADD_USER_MESSAGE', id: `user_${Date.now()}`, content })

      // 发送给后端
      if (content.startsWith('/')) {
        const spaceIdx = content.indexOf(' ')
        const name = (spaceIdx === -1 ? content.slice(1) : content.slice(1, spaceIdx)).toLowerCase()
        const rest = spaceIdx === -1 ? '' : content.slice(spaceIdx + 1)
        if ((name === 'undo' || name === 'u') && rest) {
          client.sendCommand(name, { count: parseInt(rest) || 1 })
        } else {
          client.sendCommand(name)
        }
      } else {
        client.sendUserInput(content)
      }

      setInput('')
      return
    }

    if (key.backspace || key.delete) {
      setInput(prev => prev.slice(0, -1))
      return
    }

    if (key.upArrow) {
      if (history.length > 0) {
        const newIdx = historyIdx < history.length - 1 ? historyIdx + 1 : historyIdx
        setHistoryIdx(newIdx)
        setInput(history[history.length - 1 - newIdx] || '')
      }
      return
    }

    if (key.downArrow) {
      if (historyIdx > 0) {
        const newIdx = historyIdx - 1
        setHistoryIdx(newIdx)
        setInput(history[history.length - 1 - newIdx] || '')
      } else {
        setHistoryIdx(-1)
        setInput('')
      }
      return
    }

    if (key.ctrl && ch === 'c') {
      client.sendCancel()
      return
    }

    // 普通字符输入
    if (ch && !key.ctrl && !key.meta) {
      setInput(prev => prev + ch)
    }
  })

  const promptChar = isThinking ? '⋯' : '▸'
  const promptColor = isThinking ? theme.warning : theme.success

  return (
    <Box borderStyle="single" borderColor={theme.subtle} paddingX={1}>
      <Text color={promptColor}>{promptChar} </Text>
      <Text color={theme.text}>{input}</Text>
      <Text color={theme.subtle}>▎</Text>
    </Box>
  )
}

// 简易 maxsplit
const maxsplit = / (.+)/
