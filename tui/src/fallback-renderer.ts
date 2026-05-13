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
  private isThinking = false
  private thinkingStart = 0
  private thinkingTokenDelta = 0
  private updateInterval: NodeJS.Timeout | null = null
  private thinkingLineLen = 0

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

      this.clearThinkingLine()
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
      this.clearThinkingLine()
      console.log(`  ${icon} ${payload.toolName}: ${payload.description}`)
      if (!this.isThinking) {
        this.rl?.prompt()
      }
    })

    this.bus.on('thinking_start', () => {
      // 如果上一轮思考还没结束（不应该发生），先清理
      if (this.updateInterval) {
        clearInterval(this.updateInterval)
        this.updateInterval = null
      }
      this.isThinking = true
      this.thinkingStart = Date.now()
      this.thinkingTokenDelta = 0
      // 换行后再显示思考动画，不覆盖 prompt 行
      process.stdout.write('\n')
      this.updateThinkingLine(0, 0)
      // 启动定时更新
      this.updateInterval = setInterval(() => {
        const elapsed = (Date.now() - this.thinkingStart) / 1000
        this.updateThinkingLine(elapsed, this.thinkingTokenDelta)
      }, 100)
    })

    this.bus.on('thinking_update', (payload: any) => {
      this.thinkingTokenDelta = payload.tokenDelta
      const elapsed = payload.elapsed || (Date.now() - this.thinkingStart) / 1000
      this.updateThinkingLine(elapsed, this.thinkingTokenDelta)
    })

    this.bus.on('thinking_end', (payload: any) => {
      if (this.updateInterval) {
        clearInterval(this.updateInterval)
        this.updateInterval = null
      }
      // 显示本轮思考的最终统计，然后清除
      if (payload) {
        const elapsed = payload.elapsed || (Date.now() - this.thinkingStart) / 1000
        const tokenUsage = payload.tokenUsage
        const parts = [`${elapsed.toFixed(1)}s`]
        if (tokenUsage?.total > 0) {
          parts.push(`+${tokenUsage.total}t`)
        }
        const summary = parts.join(' | ')
        process.stdout.write(`\r${' '.repeat(this.thinkingLineLen)}\r`)
        console.log(chalk.gray(`  ✓ 思考完成 ${summary}`))
        this.thinkingLineLen = 0
      } else {
        this.clearThinkingLine()
      }
      this.isThinking = false
      // 不立即恢复 prompt，等 tool_status 或 assistant_msg 再显示
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
      this.clearThinkingLine()
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

    this.bus.on('undo_result', (payload) => {
      if (payload.success) {
        for (const r of payload.results || []) {
          if (r.success) {
            const msg = typeof r.message === 'string' ? r.message : (r.message as any)?.label || '完成'
            console.log(chalk.green('  ✓ ') + msg)
          } else {
            console.log(chalk.red('  ✗ ') + (r.error || '失败'))
          }
        }
      } else {
        console.log(chalk.red('✗ 撤销失败: ') + (payload.error || '未知错误'))
      }
    })

    this.bus.on('session_info', (payload) => {
      console.log(chalk.blue(`📋 会话: ${payload.sessionId} (${payload.messageCount} 条消息)`))
    })

    this.bus.on('exit', () => {
      this.rl?.close()
      process.exit(0)
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

  private clearThinkingLine(): void {
    if (this.thinkingLineLen > 0) {
      process.stdout.write(`\r${' '.repeat(this.thinkingLineLen)}\r`)
      this.thinkingLineLen = 0
    }
  }

  private updateThinkingLine(elapsed: number, tokenDelta: number): void {
    const frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    const frame = frames[Math.floor(elapsed * 10) % frames.length]
    const parts = []
    if (elapsed >= 0) {
      parts.push(`${elapsed.toFixed(1)}s`)
    }
    if (tokenDelta > 0) {
      parts.push(`+${tokenDelta}t`)
    }
    const statusText = parts.length > 0 ? `  ${parts.join(' | ')}` : ''
    const line = chalk.gray(` ${frame} 思考中...${statusText}`)
    this.thinkingLineLen = line.length
    process.stdout.write(`\r${line}`)
  }

  private handleConfirmation(payload: ConfirmationRequestPayload): void {
    this.waitingConfirmation = true
    this.clearThinkingLine()
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
