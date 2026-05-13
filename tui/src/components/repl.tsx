import React from 'react'
import { Box, useStdout } from 'ink'
import { TuiClient } from '../bridge/tui-client.js'
import { StatusBar } from './status-bar.js'
import { MessageList } from './messages/message-list.js'
import { PromptInput } from './prompt/prompt-input.js'
import { ConfirmationOverlay } from './confirmation-overlay.js'

export function REPL({ client }: { client: TuiClient }) {
  const { stdout } = useStdout()
  // StatusBar: 3行(border) | MessageList: 剩余空间 | PromptInput: 3行(border)
  // ConfirmationOverlay 仅在有确认请求时出现，叠加在消息区上方
  const totalRows = stdout?.rows ?? 24

  return (
    <Box flexDirection="column">
      <StatusBar />
      <MessageList />
      <ConfirmationOverlay client={client} />
      <PromptInput client={client} />
    </Box>
  )
}
