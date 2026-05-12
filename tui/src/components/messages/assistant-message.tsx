import React from 'react'
import { Box, Text } from 'ink'
import type { Message } from '../../store/message-store.js'
import { useTheme } from '../../theme/context.js'

export function AssistantMessage({ message }: { message: Message }) {
  const { theme } = useTheme()
  const meta = []
  if (message.elapsed != null) {
    meta.push(`${message.elapsed.toFixed(1)}s`)
  }
  if (message.tokenUsage) {
    meta.push(`+${message.tokenUsage.total}t`)
  }

  return (
    <Box flexDirection="column">
      <Box>
        <Text color={theme.briefLabelClaude}>◆ </Text>
        <Text color={theme.text}>{message.content}</Text>
      </Box>
      {meta.length > 0 && (
        <Box marginLeft={2}>
          <Text color={theme.subtle}>{meta.join(' | ')}</Text>
        </Box>
      )}
    </Box>
  )
}
