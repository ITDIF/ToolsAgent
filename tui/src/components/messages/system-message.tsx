import React from 'react'
import { Box, Text } from 'ink'
import type { Message } from '../../store/message-store.js'
import { useTheme } from '../../theme/context.js'
import { S } from '../../utils/symbols.js'

export function SystemMessage({ message }: { message: Message }) {
  const { theme } = useTheme()

  const colorMap: Record<string, string> = {
    info: theme.suggestion,
    warn: theme.warning,
    error: theme.error,
  }
  const color = colorMap[message.level || 'info'] || theme.subtle

  return (
    <Box>
      <Text color={color}>{S.info} </Text>
      <Text color={theme.subtle}>{message.content}</Text>
    </Box>
  )
}
