import React from 'react'
import { Box } from 'ink'
import { TuiClient } from '../bridge/tui-client.js'
import { StatusBar } from './status-bar.js'
import { MessageList } from './messages/message-list.js'
import { PromptInput } from './prompt/prompt-input.js'
import { ConfirmationOverlay } from './confirmation-overlay.js'

export function REPL({ client }: { client: TuiClient }) {
  return (
    <Box flexDirection="column" height="100%">
      <StatusBar />
      <Box flexDirection="column" flexGrow={1}>
        <MessageList />
      </Box>
      <ConfirmationOverlay client={client} />
      <PromptInput client={client} />
    </Box>
  )
}
