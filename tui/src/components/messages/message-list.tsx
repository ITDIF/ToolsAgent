import React, { useMemo } from 'react'
import { Box, Text, useStdout } from 'ink'
import { useMessageState } from '../../store/message-store.js'
import { UserMessage } from './user-message.js'
import { AssistantMessage } from './assistant-message.js'
import { ToolMessage } from './tool-message.js'
import { SystemMessage } from './system-message.js'
import { Spinner } from '../spinner.js'
import { useUiState } from '../../store/ui-store.js'

/** 计算字符串的终端显示宽度（CJK 字符算 2，其余算 1） */
function stringWidth(str: string): number {
  let w = 0
  for (const ch of str) {
    const code = ch.codePointAt(0)!
    // CJK Unified Ideographs + CJK Extension A/B + Common CJK ranges
    if (
      (code >= 0x4E00 && code <= 0x9FFF) ||
      (code >= 0x3400 && code <= 0x4DBF) ||
      (code >= 0x20000 && code <= 0x2A6DF) ||
      (code >= 0x2A700 && code <= 0x2B73F) ||
      (code >= 0xF900 && code <= 0xFAFF) ||
      // Fullwidth forms
      (code >= 0xFF01 && code <= 0xFF60) ||
      // CJK punctuation / Hiragana / Katakana
      (code >= 0x3000 && code <= 0x33FF) ||
      // Hangul
      (code >= 0xAC00 && code <= 0xD7AF)
    ) {
      w += 2
    } else {
      w += 1
    }
  }
  return w
}

/** 估算一条消息在终端中占用的行数 */
function estimateMessageLines(msg: any, termWidth: number): number {
  const contentWidth = Math.max(termWidth - 4, 20) // 减去左边距和图标
  const contentW = stringWidth(msg.content || '')
  const contentLines = Math.max(1, Math.ceil(contentW / contentWidth))
  // +1 行给头部（图标+名称），工具消息还有额外的详情行
  let extra = 1
  if (msg.role === 'tool' && msg.toolError) extra += 1
  if (msg.role === 'assistant' && msg.tokenUsage) extra += 1
  return contentLines + extra
}

export function MessageList() {
  const { messages } = useMessageState()
  const { isThinking } = useUiState()
  const { stdout } = useStdout()

  const termWidth = stdout?.columns ?? 80
  // 计算消息区可用行数：终端总行数 - 状态栏(3行) - 输入框(3行)
  const availableHeight = Math.max((stdout?.rows ?? 24) - 6, 4)

  // 从最新消息往回累加，只保留能放下的消息
  const visibleMessages = useMemo(() => {
    let usedLines = isThinking ? 1 : 0 // spinner 占 1 行
    const result: any[] = []

    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i]
      const lines = estimateMessageLines(msg, termWidth)
      if (usedLines + lines > availableHeight && result.length > 0) break
      usedLines += lines
      result.unshift(msg)
    }

    return result
  }, [messages, availableHeight, termWidth, isThinking])

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
