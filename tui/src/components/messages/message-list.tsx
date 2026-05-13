import React, { useMemo } from 'react'
import { Box, Text, useStdout } from 'ink'
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
  const { stdout } = useStdout()

  // 计算消息区可用行数：终端总行数 - 状态栏(3行) - 输入框(3行) - 确认弹窗预留(0行)
  const availableHeight = Math.max((stdout?.rows ?? 24) - 6, 4)

  // 估算消息总高度，只保留最近能放下的消息
  const visibleMessages = useMemo(() => {
    // 粗略估算：每条消息占 1 行（短消息）到多行（长内容）
    // 从最新消息往回累加，直到超出可用高度
    let usedLines = isThinking ? 1 : 0  // spinner 占 1 行
    const result: any[] = []

    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i]
      // 估算消息高度：内容按 80 字符换行 + 1 行头部
      const contentLines = Math.max(1, Math.ceil((msg.content?.length || 0) / 80)) + 1
      if (usedLines + contentLines > availableHeight && result.length > 0) break
      usedLines += contentLines
      result.unshift(msg)
    }

    return result
  }, [messages, availableHeight, isThinking])

  return (
    <Box flexDirection="column" height={availableHeight} overflow="hidden">
      {visibleMessages.map((msg: any) => {
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
