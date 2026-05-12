import React from 'react'
import { Box, Text } from 'ink'
import { useUiState } from '../store/ui-store.js'
import { useTheme } from '../theme/context.js'

export function StatusBar() {
  const { model, sessionId, isThinking, connected, totalTokens } = useUiState()
  const { theme } = useTheme()

  const statusIcon = connected ? '●' : '○'
  const statusColor = connected ? theme.success : theme.error

  return (
    <Box borderStyle="single" borderColor={theme.subtle} paddingX={1}>
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
  )
}
