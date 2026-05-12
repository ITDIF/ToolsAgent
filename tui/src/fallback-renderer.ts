import * as readline from 'node:readline'
import { stdin, stdout } from 'node:process'
import chalk from 'chalk'
import { TypedEventBus } from './bridge/event-bus.js'
import { TuiClient } from './bridge/tui-client.js'
import type { ConfirmationRequestPayload } from './bridge/protocol.js'

/**
 * 伪终端兼容渲染器。
 * 当 Ink 无法使用（非 TTY 或不支持 raw mode）时，
 * 使用 readline + chalk 提供基本的交互体验。
 */
export class FallbackRenderer {
  private bus: TypedEventBus
  private client: TuiClient
  private rl: readline.Interface | null = null
  private waitingConfirmation = false

  constructor(bus: TypedEventBus, client: TuiClient) {
    this.bus = bus
    this.client = client
  }

  start(): void {
    this.rl = readline.createInterface({
      input: stdin,
      output: stdout,
      prompt: chalk.green('▸ '),
    })

    // 注册事件监听
    this.bus.on('connected', () => {
      console.log(chalk.green('✓ 已连接到后端服务'))
      console.log()
      console.log(chalk.cyan('ToolsAgent 本地文件操作助手'))
      console.log(chalk.gray('────────────────────────'))
      console.log(chalk.gray('输入指令按回车发送，/help 查看命令'))
      console.log()
      this.rl?.prompt()
    })

    this.bus.on('disconnected', (reason) => {
      console.log(chalk.red(`\n连接断开: ${reason}`))
      this.rl?.close()
      process.exit(0)
    })

    this.bus.on('ready', (payload) => {
      console.log(chalk.gray(`模型: ${payload.model} | 会话: ${payload.sessionId.slice(0, 8)}`))
      console.log()
      this.rl?.prompt()
    })

    this.bus.on('assistant_msg', (payload) => {
      const meta = []
      if (payload.elapsed) meta.push(`${payload.elapsed.toFixed(1)}s`)
      if (payload.tokenUsage?.total) meta.push(`+${payload.tokenUsage.total}t`)
      const metaStr = meta.length ? chalk.gray(` [${meta.join(' | ')}]`) : ''

      console.log()
      console.log(chalk.rgb(215, 119, 87)('◆ ') + payload.content + metaStr)
      console.log()
      this.rl?.prompt()
    })

    this.bus.on('tool_status', (payload) => {
      const icons: Record<string, string> = {
        running: chalk.yellow('⟳'),
        success: chalk.green('✓'),
        error: chalk.red('✗'),
        info: chalk.blue('ℹ'),
      }
      const icon = icons[payload.status] || chalk.gray('·')
      console.log(`  ${icon} ${payload.toolName}: ${payload.description}`)
    })

    this.bus.on('thinking_start', () => {
      process.stdout.write(chalk.gray(' ⋯ '))
    })

    this.bus.on('thinking_end', () => {
      process.stdout.write('\r' + ' '.repeat(10) + '\r')
    })

    this.bus.on('confirmation_request', (payload) => {
      this.handleConfirmation(payload)
    })

    this.bus.on('system_notify', (payload) => {
      const colors: Record<string, typeof chalk.blue> = {
        info: chalk.blue,
        warn: chalk.yellow,
        error: chalk.red,
      }
      const colorFn = colors[payload.level] || chalk.gray
      console.log(colorFn('ℹ ') + payload.content)
      if (!this.waitingConfirmation) {
        this.rl?.prompt()
      }
    })

    this.bus.on('model_update', (payload) => {
      console.log(chalk.cyan(`🔄 模型切换: ${payload.model}`))
    })

    this.bus.on('error', (payload) => {
      console.log(chalk.red('✗ ') + payload.content)
      if (!this.waitingConfirmation) {
        this.rl?.prompt()
      }
    })

    // 用户输入
    this.rl.on('line', (line) => {
      if (this.waitingConfirmation) return // 确认模式下忽略
      const content = line.trim()
      if (content) {
        this.client.sendUserInput(content)
      } else {
        this.rl?.prompt()
      }
    })

    this.rl.on('close', () => {
      console.log(chalk.gray('\n再见！'))
      process.exit(0)
    })

    process.on('SIGINT', () => {
      console.log(chalk.gray('\n再见！'))
      process.exit(0)
    })
  }

  private handleConfirmation(payload: ConfirmationRequestPayload): void {
    this.waitingConfirmation = true
    console.log()
    console.log(chalk.yellow('⚠ ') + payload.title)
    payload.options.forEach((opt, i) => {
      console.log(`  ${i + 1}. ${opt}`)
    })

    const confirmRl = readline.createInterface({
      input: stdin,
      output: stdout,
    })

    confirmRl.question(chalk.gray('请选择 (数字/回车默认/Esc取消): '), (answer) => {
      confirmRl.close()
      this.waitingConfirmation = false

      const trimmed = answer.trim()
      if (!trimmed || trimmed.toLowerCase() === 'esc' || trimmed.toLowerCase() === 'q') {
        this.client.sendConfirmationResponse(payload.requestId, null)
      } else {
        const num = parseInt(trimmed)
        if (!isNaN(num) && num >= 1 && num <= payload.options.length) {
          this.client.sendConfirmationResponse(payload.requestId, num - 1)
        } else {
          this.client.sendConfirmationResponse(payload.requestId, payload.default ?? 0)
        }
      }
      this.rl?.prompt()
    })
  }
}
