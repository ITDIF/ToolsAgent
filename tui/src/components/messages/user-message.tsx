import React from 'react'
import { Box, Text } from 'ink'
import type { Message } from '../../store/message-store.js'
import { useTheme } from '../../theme/context.js'

export function UserMessage({ message }: { message: Message }) {
  const { theme } = useTheme()
  return (
    <Box>
      <Text color={theme.briefLabelYou}>▸ </Text>
      <Text color={theme.text}>{message.content}</Text>
    </Box>
  )
}
