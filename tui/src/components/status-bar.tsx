import React from 'react'
import { Box, Text, useStdout } from 'ink'
import { useUiState } from '../store/ui-store.js'
import { useTheme } from '../theme/context.js'
import { S } from '../utils/symbols.js'

function HLine() {
  const { stdout } = useStdout()
  const { theme } = useTheme()
  const cols = Math.max((stdout?.columns ?? 80) - 1, 1)
  return <Text color={theme.subtle}>{S.hLine.repeat(cols)}</Text>
}

export function StatusBar() {
  const { model, sessionId, isThinking, connected, totalTokens } = useUiState()
  const { theme } = useTheme()

  const statusIcon = connected ? S.dot : S.dotEmpty
  const statusColor = connected ? theme.success : theme.error

  return (
    <Box flexDirection="column" width="100%">
      <HLine />
      <Box width="100%">
        <Text color={theme.subtle}>{S.vLine} </Text>
        <Box flexGrow={1}>
          <Text color={statusColor}>{statusIcon}</Text>
          <Text color={theme.text}> </Text>
          <Text color={theme.claude}>{model}</Text>
          <Text color={theme.subtle}> | </Text>
          <Text color={theme.subtle}>{sessionId.slice(0, 8)}</Text>
          <Text color={theme.subtle}> | </Text>
          <Text color={theme.subtle}>{totalTokens.total}t</Text>
          {isThinking && (
            <>
              <Text color={theme.subtle}> | </Text>
              <Text color={theme.warning}>thinking...</Text>
            </>
          )}
        </Box>
        <Text color={theme.subtle}> {S.vLine}</Text>
      </Box>
      <HLine />
    </Box>
  )
}
