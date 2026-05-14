import React, { useState, useEffect } from 'react'
import { Box, Text } from 'ink'
import { useTheme } from '../theme/context.js'
import { useUiState } from '../store/ui-store.js'
import { S } from '../utils/symbols.js'

export function Spinner({ label }: { label?: string }) {
  const { theme } = useTheme()
  const { thinkingElapsed, thinkingTokenDelta } = useUiState()
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setFrame(f => (f + 1) % S.spinner.length)
    }, 80)
    return () => clearInterval(timer)
  }, [])

  // 构建状态信息
  const statusParts = []
  // 始终显示时间（只要 isThinking）
  if (thinkingElapsed >= 0) {
    statusParts.push(`${thinkingElapsed.toFixed(1)}s`)
  }
  // 只在有 token 时显示
  if (thinkingTokenDelta > 0) {
    statusParts.push(`+${thinkingTokenDelta}t`)
  }
  const statusText = statusParts.join(' | ')

  return (
    <Box>
      <Text color={theme.claude}>{S.spinner[frame]}</Text>
      {label && <Text color={theme.subtle}> {label}</Text>}
      {statusText && <Text color={theme.subtle}>  {statusText}</Text>}
    </Box>
  )
}
