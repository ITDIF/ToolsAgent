import React from 'react'
import { Box, Text } from 'ink'
import { useMessageState } from '../../store/message-store.js'
import { UserMessage } from './user-message.js'
import { AssistantMessage } from './assistant-message.js'
import { ToolMessage } from './tool-message.js'
import { SystemMessage } from './system-message.js'
import { Spinner } from '../spinner.js'
import { useUiState } from '../../store/ui-store.js'

export function MessageList() {
  const { messages } = useMessageState()
  const { isThinking } = useUiState()

  return (
    <Box flexDirection="column">
      {messages.map((msg: any) => {
        switch (msg.role) {
          case 'user':
            return <UserMessage key={msg.id} message={msg} />
          case 'assistant':
            return <AssistantMessage key={msg.id} message={msg} />
          case 'tool':
            return <ToolMessage key={msg.id} message={msg} />
          case 'system':
            return <SystemMessage key={msg.id} message={msg} />
          default:
            return <Text key={msg.id}>{msg.content}</Text>
        }
      })}
      {isThinking && <Spinner label="思考中..." />}
    </Box>
  )
}
