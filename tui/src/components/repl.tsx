import React from 'react'
import { Box, Text, useStdout } from 'ink'
import { TuiClient } from '../bridge/tui-client.js'
import { StatusBar } from './status-bar.js'
import { MessageList } from './messages/message-list.js'
import { PromptInput } from './prompt/prompt-input.js'
import { ConfirmationOverlay } from './confirmation-overlay.js'
import { useTheme } from '../theme/context.js'
import { S } from '../utils/symbols.js'

function Divider() {
  const { stdout } = useStdout()
  const { theme } = useTheme()
  const cols = Math.max((stdout?.columns ?? 80) - 1, 1)
  return <Text color={theme.subtle}>{S.hLine.repeat(cols)}</Text>
}

export function REPL({ client, hasRawMode }: { client: TuiClient; hasRawMode: boolean }) {
  return (
    <Box flexDirection="column">
      <StatusBar />
      <MessageList />
      <ConfirmationOverlay client={client} hasRawMode={hasRawMode} />
      <Divider />
      <PromptInput client={client} hasRawMode={hasRawMode} />
      <Divider />
    </Box>
  )
}
