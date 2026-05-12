import React, { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import { TuiClient } from '../bridge/tui-client.js'
import { useUiState } from '../store/ui-store.js'
import { useUiDispatch } from '../store/ui-store.js'
import { useTheme } from '../theme/context.js'

export function ConfirmationOverlay({ client }: { client: TuiClient }) {
  const { pendingConfirmation } = useUiState()
  const dispatchUi = useUiDispatch()
  const { theme } = useTheme()
  const [selectedIndex, setSelectedIndex] = useState(pendingConfirmation?.default || 0)

  // 当新的确认请求到来时重置选中索引
  React.useEffect(() => {
    if (pendingConfirmation) {
      setSelectedIndex(pendingConfirmation.default || 0)
    }
  }, [pendingConfirmation?.requestId])

  useInput((ch, key) => {
    if (!pendingConfirmation) return

    if (key.upArrow) {
      setSelectedIndex(i => Math.max(0, i - 1))
      return
    }

    if (key.downArrow) {
      setSelectedIndex(i => Math.min(pendingConfirmation.options.length - 1, i + 1))
      return
    }

    if (key.return) {
      client.sendConfirmationResponse(pendingConfirmation.requestId, selectedIndex)
      dispatchUi({ type: 'SET_CONFIRMATION', payload: null })
      return
    }

    if (key.escape || (ch === 'q')) {
      client.sendConfirmationResponse(pendingConfirmation.requestId, null)
      dispatchUi({ type: 'SET_CONFIRMATION', payload: null })
      return
    }

    // 数字快捷键
    const num = parseInt(ch)
    if (!isNaN(num) && num >= 1 && num <= pendingConfirmation.options.length) {
      client.sendConfirmationResponse(pendingConfirmation.requestId, num - 1)
      dispatchUi({ type: 'SET_CONFIRMATION', payload: null })
      return
    }
  })

  if (!pendingConfirmation) return null

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={theme.permission}
      paddingX={1}
    >
      <Text color={theme.warning}>⚠ {pendingConfirmation.title}</Text>
      {pendingConfirmation.options.map((opt, i) => (
        <Box key={i}>
          <Text color={i === selectedIndex ? theme.permission : theme.subtle}>
            {i === selectedIndex ? '▸' : ' '} {i + 1}. {opt}
          </Text>
        </Box>
      ))}
      <Text color={theme.subtle}>↑↓ 选择 · Enter 确认 · Esc 取消</Text>
    </Box>
  )
}
