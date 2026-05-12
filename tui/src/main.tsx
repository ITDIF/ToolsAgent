#!/usr/bin/env node
import * as net from 'node:net'
import * as readline from 'node:readline'
import { stdin, stdout } from 'node:process'

// 检测终端环境
const isTTY = !!stdin.isTTY
let supportsRawMode = false

if (isTTY) {
  try {
    stdin.setRawMode(true)
    stdin.setRawMode(false)
    supportsRawMode = true
  } catch (err) {
    supportsRawMode = false
  }
}

// 如果是CI环境，直接退出
const isCI = process.env.CI === 'true' || process.env.TF_BUILD || process.env.GITHUB_ACTIONS
if (isCI && !isTTY) {
  console.error(`
⚠️  当前环境是 CI 非交互式环境，无法运行 TUI 界面
请在交互式终端中运行，或使用传统 CLI 模式：
python -m src.cli.main
`)
  process.exit(1)
}

// 环境提示
if (!isTTY || !supportsRawMode) {
  console.log('⚠️  检测到非标准终端环境，使用纯文本兼容模式运行')
  console.log('💡 如需更好的交互体验，请使用系统终端（Windows Terminal/PowerShell）运行')
  console.log()
}

// 消息边界
const MSG_START = '<<<MSG_START>>>'
const MSG_END = '<<<MSG_END>>>'

// 获取后端端口（支持环境变量或命令行参数）
const port = process.env.TUI_BACKEND_PORT
  ? parseInt(process.env.TUI_BACKEND_PORT)
  : parseInt(process.argv[2] || '0')

if (!port) {
  console.error(`
⚠️  TUI 前端界面
----------------------
此程序是 ToolsAgent 的前端界面，需要后端服务支持。

使用方式：
1. 通过 Python 启动（推荐）：
   python -m src.cli.main --tui

2. 手动启动（仅用于开发）：
   # 终端1：启动后端
   TUI_BACKEND_PORT=9999 python -m src.cli.main --tui

   # 终端2：启动前端
   npm run dev 9999

3. 构建后运行：
   npm run build
   TUI_BACKEND_PORT=9999 npm start 9999

注意：直接运行此程序不会启动任何服务，它只是一个客户端。
`)
  process.exit(1)
}

// 连接状态
let isConnected = false
let socket: net.Socket | null = null

// 消息发送函数
function sendMessage(type: string, payload: Record<string, any>) {
  if (!isConnected || !socket) {
    console.log('❌ 后端连接断开，请重启应用')
    return
  }
  const message = {
    type,
    id: crypto.randomUUID(),
    timestamp: Date.now(),
    ...payload
  }
  const msgStr = `${MSG_START}\n${JSON.stringify(message)}\n${MSG_END}\n`
  socket.write(msgStr)
}

// 处理后端消息
function handleMessage(message: any) {
  const { type, content, model } = message
  switch (type) {
    case 'assistant_msg':
      console.log()
      console.log('🤖 助手回复:')
      console.log(content)
      console.log()
      break
    case 'system_notify':
      console.log()
      console.log(`ℹ️  系统通知: ${content}`)
      console.log()
      break
    case 'tool_call':
      console.log()
      const statusText = message.status === 'running' ? '⚙️  正在执行' : message.status === 'success' ? '✅ 执行完成' : '❌ 执行失败'
      console.log(`${statusText} 工具: ${message.toolName}`)
      if (message.parameters) {
        console.log('参数:', JSON.stringify(message.parameters, null, 2))
      }
      if (message.result) {
        console.log('结果:', JSON.stringify(message.result, null, 2))
      }
      if (message.error) {
        console.log('错误:', message.error)
      }
      console.log()
      break
    case 'error':
      console.log()
      console.log(`❌ 错误: ${content}`)
      console.log()
      break
    case 'model_update':
      console.log()
      console.log(`🔄 当前模型: ${model}`)
      console.log()
      break
  }

  // 显示输入提示符
  process.stdout.write('> ')
}

// 连接后端
console.log(`🔌 正在连接后端服务 (端口 ${port})...`)
socket = net.connect({ host: '127.0.0.1', port }, () => {
  isConnected = true
  console.log('✅ 已连接到后端服务')
  console.log()
  console.log('🎯 ToolsAgent 本地文件操作助手')
  console.log('--------------------------------')
  console.log('💡 输入文件操作指令，按回车发送')
  console.log('💡 按 Ctrl+C 退出')
  console.log()
  process.stdout.write('> ')

  let buffer = Buffer.alloc(0)
  let inMessage = false

  // @ts-ignore
  socket.on('data', (data) => {
    buffer = Buffer.concat([buffer, data])
    const bufferStr = buffer.toString('utf-8')

    while (bufferStr.includes(MSG_START)) {
      const startIdx = bufferStr.indexOf(MSG_START)
      buffer = buffer.subarray(startIdx + MSG_START.length)
      inMessage = true
    }

    while (inMessage && bufferStr.includes(MSG_END)) {
      const endIdx = bufferStr.indexOf(MSG_END)
      const msgContent = bufferStr.slice(0, endIdx).trim()
      buffer = buffer.subarray(endIdx + MSG_END.length)
      inMessage = false

      try {
        const message = JSON.parse(msgContent)
        handleMessage(message)
      } catch (e) {
        // 解析失败忽略
      }
    }
  })
})

socket.on('error', (err) => {
  console.error(`❌ 连接后端失败: ${err.message}`)
  console.error(`请确保后端服务正在运行，端口 ${port} 可访问`)
  process.exit(1)
})

socket.on('close', () => {
  isConnected = false
  console.log('\n🔌 与后端连接断开')
  process.exit(0)
})

// 处理用户输入
const rl = readline.createInterface({
  input: stdin,
  output: stdout,
  prompt: '> '
})

rl.on('line', (line) => {
  const content = line.trim()
  if (content) {
    sendMessage('user_input', { content })
  } else {
    process.stdout.write('> ')
  }
})

rl.on('close', () => {
  console.log('\n👋 再见！')
  process.exit(0)
})

// 处理Ctrl+C
process.on('SIGINT', () => {
  console.log('\n👋 再见！')
  process.exit(0)
})