import React, { useState, useEffect } from 'react'
import { Box, Text } from 'ink'
import { useTheme } from '../theme/context.js'

const FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

export function Spinner({ label }: { label?: string }) {
  const { theme } = useTheme()
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setFrame(f => (f + 1) % FRAMES.length)
    }, 80)
    return () => clearInterval(timer)
  }, [])

  return (
    <Box>
      <Text color={theme.claude}>{FRAMES[frame]}</Text>
      {label && <Text color={theme.subtle}> {label}</Text>}
    </Box>
  )
}
