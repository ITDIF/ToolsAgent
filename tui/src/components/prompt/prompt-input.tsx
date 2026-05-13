import React, { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import { TuiClient } from '../../bridge/tui-client.js'
import { useMessageDispatch } from '../../store/message-store.js'
import { useUiState } from '../../store/ui-store.js'
import { useTheme } from '../../theme/context.js'

export function PromptInput({ client }: { client: TuiClient }) {
  const [input, setInput] = useState('')
  const [cursorPos, setCursorPos] = useState(0) // 光标在 input 中的位置
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
      setCursorPos(0)
      return
    }

    if (key.backspace || key.delete) {
      if (cursorPos > 0) {
        setInput(prev => prev.slice(0, cursorPos - 1) + prev.slice(cursorPos))
        setCursorPos(prev => prev - 1)
      }
      return
    }

    if (key.leftArrow) {
      setCursorPos(prev => Math.max(0, prev - 1))
      return
    }

    if (key.rightArrow) {
      setCursorPos(prev => Math.min(input.length, prev + 1))
      return
    }

    if (key.upArrow) {
      if (history.length > 0) {
        const newIdx = historyIdx < history.length - 1 ? historyIdx + 1 : historyIdx
        setHistoryIdx(newIdx)
        const newInput = history[history.length - 1 - newIdx] || ''
        setInput(newInput)
        setCursorPos(newInput.length)
      }
      return
    }

    if (key.downArrow) {
      if (historyIdx > 0) {
        const newIdx = historyIdx - 1
        setHistoryIdx(newIdx)
        const newInput = history[history.length - 1 - newIdx] || ''
        setInput(newInput)
        setCursorPos(newInput.length)
      } else {
        setHistoryIdx(-1)
        setInput('')
        setCursorPos(0)
      }
      return
    }

    // Home: 光标移到行首
    if (key.ctrl && ch === 'a') {
      setCursorPos(0)
      return
    }

    // End: 光标移到行尾 (Ctrl+E)
    if (key.ctrl && ch === 'e') {
      setCursorPos(input.length)
      return
    }

    if (key.ctrl && ch === 'c') {
      client.sendCancel()
      return
    }

    // 普通字符输入：在光标位置插入
    if (ch && !key.ctrl && !key.meta) {
      setInput(prev => prev.slice(0, cursorPos) + ch + prev.slice(cursorPos))
      setCursorPos(prev => prev + 1)
    }
  })

  const promptChar = isThinking ? '⋯' : '▸'
  const promptColor = isThinking ? theme.warning : theme.success

  // 将输入分为光标前和光标后两部分
  const beforeCursor = input.slice(0, cursorPos)
  const afterCursor = input.slice(cursorPos)

  return (
    <Box borderStyle="single" borderColor={theme.subtle} paddingX={1}>
      <Text color={promptColor}>{promptChar} </Text>
      <Text color={theme.text}>{beforeCursor}</Text>
      <Text color={theme.subtle} inverse>▎</Text>
      <Text color={theme.text}>{afterCursor}</Text>
    </Box>
  )
}
