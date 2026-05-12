#!/usr/bin/env node

import { render } from 'ink'
import { TypedEventBus } from './bridge/event-bus.js'
import { TuiClient } from './bridge/tui-client.js'
import { App } from './components/app.js'
import { FallbackRenderer } from './fallback-renderer.js'
import { detectTerminal, detectPreferredTheme } from './utils/terminal.js'

// 获取后端端口
const port = process.env.TUI_BACKEND_PORT
  ? parseInt(process.env.TUI_BACKEND_PORT)
  : parseInt(process.argv[2] || '0')

if (!port) {
  console.error(`
ToolsAgent TUI 前端
──────────────────
此程序需要后端服务支持。

使用方式:
  python -m src.cli.main --tui
`)
  process.exit(1)
}

// 检测终端能力
const terminal = detectTerminal()
const preferredTheme = detectPreferredTheme()

if (!terminal.isTTY) {
  console.log('⚠ 检测到非终端环境，使用兼容模式')
  console.log('💡 如需更好的交互体验，请使用系统终端运行')
  console.log()
}

// 创建 EventBus 和 Client
const bus = new TypedEventBus()
const client = new TuiClient(bus)

// 连接后端
client.connect('127.0.0.1', port).catch((err) => {
  console.error(`连接后端失败: ${err.message}`)
  process.exit(1)
})

// 根据终端能力选择渲染模式
if (terminal.mode === 'full') {
  // 使用 Ink/React 渲染
  const { waitUntilExit } = render(
    <App
      bus={bus}
      client={client}
      initialTheme={preferredTheme}
      terminalMode="full"
    />,
    {
      exitOnCtrlC: false,
    }
  )

  waitUntilExit().then(() => {
    client.disconnect()
    process.exit(0)
  })
} else {
  // 伪终端兼容模式
  const renderer = new FallbackRenderer(bus, client)
  renderer.start()
}

// 优雅退出
process.on('SIGINT', () => {
  client.disconnect()
  process.exit(0)
})

process.on('exit', () => {
  client.disconnect()
})
