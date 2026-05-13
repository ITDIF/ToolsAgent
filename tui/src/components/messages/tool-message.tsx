import React, { useState, useEffect } from 'react'
import { Box, Text } from 'ink'
import type { Message } from '../../store/message-store.js'
import { useTheme } from '../../theme/context.js'

export function ToolMessage({ message }: { message: Message }) {
  const { theme } = useTheme()
  const [expanded, setExpanded] = useState(false)

  // 工具完成时自动展开，运行中保持折叠
  useEffect(() => {
    if (message.toolStatus === 'success' || message.toolStatus === 'error') {
      setExpanded(true)
    }
  }, [message.toolStatus])

  const statusConfig: Record<string, { icon: string; color: string }> = {
    running: { icon: '⟳', color: theme.warning },
    success: { icon: '✓', color: theme.success },
    error:   { icon: '✗', color: theme.error },
    info:    { icon: 'ℹ', color: theme.suggestion },
  }

  const config = statusConfig[message.toolStatus || 'running'] || statusConfig.running
  const hasDetails = message.toolParameters || message.toolResult || message.toolError

  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box>
        <Text color={config.color}>{config.icon} </Text>
        <Text color={theme.text}>{message.toolName}</Text>
        {message.toolDescription && (
          <Text color={theme.subtle}> {message.toolDescription}</Text>
        )}
        {hasDetails && (
          <Text color={theme.subtle}> {expanded ? '▼' : '▶'}</Text>
        )}
      </Box>

      {expanded && message.toolParameters && Object.keys(message.toolParameters).length > 0 && (
        <Box marginLeft={2} flexDirection="column">
          <Text color={theme.subtle}>参数: {JSON.stringify(message.toolParameters)}</Text>
        </Box>
      )}

      {expanded && message.toolResult && (
        <Box marginLeft={2} flexDirection="column">
          <Text color={theme.subtle}>结果: {JSON.stringify(message.toolResult)}</Text>
        </Box>
      )}

      {message.toolError && (
        <Box marginLeft={2}>
          <Text color={theme.error}>{message.toolError}</Text>
        </Box>
      )}
    </Box>
  )
}
