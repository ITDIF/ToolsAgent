import React, { useState } from 'react'
import { Box, Text, useInput, useStdout } from 'ink'
import { TuiClient } from '../bridge/tui-client.js'
import { useUiState, useUiDispatch } from '../store/ui-store.js'
import { useTheme } from '../theme/context.js'
import { S } from '../utils/symbols.js'
import type { ConfirmationRequestPayload } from '../bridge/protocol.js'

/** raw mode 下的键盘导航选择 */
function RawModeSelector({ client, pendingConfirmation }: {
  client: TuiClient
  pendingConfirmation: ConfirmationRequestPayload
}) {
  const dispatchUi = useUiDispatch()
  const { theme } = useTheme()
  const [selectedIndex, setSelectedIndex] = useState(pendingConfirmation.default || 0)

  React.useEffect(() => {
    setSelectedIndex(pendingConfirmation.default || 0)
  }, [pendingConfirmation.requestId])

  useInput((ch, key) => {
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
    if (key.escape || ch === 'q') {
      client.sendConfirmationResponse(pendingConfirmation.requestId, null)
      dispatchUi({ type: 'SET_CONFIRMATION', payload: null })
      return
    }
    const num = parseInt(ch)
    if (!isNaN(num) && num >= 1 && num <= pendingConfirmation.options.length) {
      client.sendConfirmationResponse(pendingConfirmation.requestId, num - 1)
      dispatchUi({ type: 'SET_CONFIRMATION', payload: null })
    }
  })

  return (
    <>
      {pendingConfirmation.options.map((opt, i) => (
        <Box key={i}>
          <Text color={i === selectedIndex ? theme.permission : theme.subtle}>
            {i === selectedIndex ? S.prompt : ' '} {i + 1}. {opt}
          </Text>
        </Box>
      ))}
      <Text color={theme.subtle}>↑↓ 选择 · Enter 确认 · Esc 取消</Text>
    </>
  )
}

export function ConfirmationOverlay({ client, hasRawMode }: { client: TuiClient; hasRawMode: boolean }) {
  const { pendingConfirmation } = useUiState()
  const { theme } = useTheme()
  const { stdout } = useStdout()
  const cols = Math.max((stdout?.columns ?? 80) - 1, 1)

  if (!pendingConfirmation) return null

  return (
    <Box flexDirection="column" width="100%">
      <Text color={theme.permission}>{S.hLine.repeat(cols)}</Text>
      <Box width="100%">
        <Text color={theme.permission}>{S.vLine} </Text>
        <Box flexGrow={1} flexDirection="column">
          <Text color={theme.warning}>{S.warn} {pendingConfirmation.title}</Text>
          {hasRawMode ? (
            <RawModeSelector client={client} pendingConfirmation={pendingConfirmation} />
          ) : (
            <>
              {pendingConfirmation.options.map((opt, i) => (
                <Box key={i}>
                  <Text color={theme.subtle}>  {i + 1}. {opt}</Text>
                </Box>
              ))}
              <Text color={theme.subtle}>输入数字选择 · 回车确认 · q 取消</Text>
            </>
          )}
        </Box>
        <Text color={theme.permission}> {S.vLine}</Text>
      </Box>
      <Text color={theme.permission}>{S.hLine.repeat(cols)}</Text>
    </Box>
  )
}
