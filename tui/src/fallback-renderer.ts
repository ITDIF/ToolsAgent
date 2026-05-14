import * as readline from 'node:readline'
import { stdin, stdout } from 'node:process'
import chalk from 'chalk'
import { TypedEventBus } from './bridge/event-bus.js'
import { TuiClient } from './bridge/tui-client.js'
import type { ConfirmationRequestPayload } from './bridge/protocol.js'
import { S } from './utils/symbols.js'

/**
 * 伪终端兼容渲染器。
 * 当 Ink 无法原地覆盖时（Windows pipe 下 eraseLines 无效），
 * 使用 readline + chalk 提供滚动式输出。
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

  private get cols(): number {
    return Math.max((stdout?.columns ?? 80) - 1, 20)
  }

  private printDivider(color?: typeof chalk.gray): void {
    const fn = color || chalk.gray
    console.log(fn(S.hLine.repeat(this.cols)))
  }

  private printRow(content: string, color?: typeof chalk.gray): void {
    const fn = color || chalk.gray
    console.log(fn(S.vLine) + ' ' + content)
  }

  private pausePrompt(): void {
    if (!this.rl) return
    this.rl.pause()
    stdout.write('\r\x1b[2K')
  }

  private resumePrompt(): void {
    if (!this.rl) return
    this.printDivider()
    this.rl.resume()
    this.rl.prompt(true)
  }

  start(): void {
    this.rl = readline.createInterface({
      input: stdin,
      output: stdout,
      prompt: chalk.gray(S.vLine) + ' ' + chalk.green(S.prompt + ' '),
    })

    this.bus.on('connected', () => {
      console.log(chalk.green(S.check + ' 已连接到后端服务'))
      console.log()
      this.printDivider(chalk.cyan)
      this.printRow(chalk.cyan('ToolsAgent 本地文件操作助手'), chalk.cyan)
      this.printRow(chalk.gray('输入指令按回车发送，/help 查看命令'))
      this.printDivider(chalk.cyan)
      console.log()
      this.rl?.prompt()
    })

    this.bus.on('disconnected', (reason) => {
      console.log(chalk.red(`\n连接断开: ${reason}`))
      this.rl?.close()
      process.exit(0)
    })

    this.bus.on('ready', (payload) => {
      this.pausePrompt()
      this.printRow(chalk.gray(`模型: ${payload.model} | 会话: ${payload.sessionId.slice(0, 8)}`))
      this.resumePrompt()
    })

    this.bus.on('assistant_msg', (payload) => {
      const meta = []
      if (payload.elapsed) meta.push(`${payload.elapsed.toFixed(1)}s`)
      if (payload.tokenUsage?.total) meta.push(`+${payload.tokenUsage.total}t`)
      const metaStr = meta.length ? chalk.gray(` [${meta.join(' | ')}]`) : ''

      this.clearThinkingLine()
      this.pausePrompt()
      this.printDivider()
      console.log()
      console.log(chalk.rgb(215, 119, 87)(S.diamond + ' ') + payload.content + metaStr)
      console.log()
      this.resumePrompt()
    })

    this.bus.on('tool_status', (payload) => {
      const icons: Record<string, string> = {
        running: chalk.yellow(S.refresh),
        success: chalk.green(S.check),
        error: chalk.red(S.cross),
        info: chalk.blue(S.info),
      }
      const icon = icons[payload.status] || chalk.gray(S.hLine)
      this.clearThinkingLine()
      this.pausePrompt()
      console.log(`  ${icon} ${payload.toolName}: ${payload.description}`)
      if (!this.isThinking) {
        this.resumePrompt()
      }
    })

    this.bus.on('thinking_start', () => {
      if (this.updateInterval) {
        clearInterval(this.updateInterval)
        this.updateInterval = null
      }
      this.isThinking = true
      this.thinkingStart = Date.now()
      this.thinkingTokenDelta = 0
      this.pausePrompt()
      this.updateThinkingLine(0, 0)
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
      if (payload) {
        const elapsed = payload.elapsed || (Date.now() - this.thinkingStart) / 1000
        const tokenUsage = payload.tokenUsage
        const parts = [`${elapsed.toFixed(1)}s`]
        if (tokenUsage?.total > 0) {
          parts.push(`+${tokenUsage.total}t`)
        }
        const summary = parts.join(' | ')
        stdout.write(`\r${' '.repeat(this.thinkingLineLen)}\r`)
        console.log(chalk.gray(`  ${S.check} 思考完成 ${summary}`))
        this.thinkingLineLen = 0
      } else {
        this.clearThinkingLine()
      }
      this.isThinking = false
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
      this.pausePrompt()
      console.log(colorFn(S.info + ' ') + payload.content)
      if (!this.waitingConfirmation) {
        this.resumePrompt()
      }
    })

    this.bus.on('model_update', (payload) => {
      this.pausePrompt()
      console.log(chalk.cyan(`模型切换: ${payload.model}`))
      this.resumePrompt()
    })

    this.bus.on('error', (payload) => {
      this.clearThinkingLine()
      this.pausePrompt()
      console.log(chalk.red(S.cross + ' ') + payload.content)
      if (!this.waitingConfirmation) {
        this.resumePrompt()
      }
    })

    this.bus.on('undo_result', (payload) => {
      this.pausePrompt()
      if (payload.success) {
        for (const r of payload.results || []) {
          if (r.success) {
            const msg = typeof r.message === 'string' ? r.message : (r.message as any)?.label || '完成'
            console.log(chalk.green(`  ${S.check} `) + msg)
          } else {
            console.log(chalk.red(`  ${S.cross} `) + (r.error || '失败'))
          }
        }
      } else {
        console.log(chalk.red(S.cross + ' 撤销失败: ') + (payload.error || '未知错误'))
      }
      this.resumePrompt()
    })

    this.bus.on('session_info', (payload) => {
      this.pausePrompt()
      console.log(chalk.blue(`会话: ${payload.sessionId} (${payload.messageCount} 条消息)`))
      this.resumePrompt()
    })

    this.bus.on('exit', () => {
      this.rl?.close()
      process.exit(0)
    })

    this.rl.on('line', (line) => {
      if (this.waitingConfirmation) return
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
      stdout.write(`\r${' '.repeat(this.thinkingLineLen)}\r`)
      this.thinkingLineLen = 0
    }
  }

  private updateThinkingLine(elapsed: number, tokenDelta: number): void {
    const frame = S.spinner[Math.floor(elapsed * 10) % S.spinner.length]
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
    stdout.write(`\r${line}`)
  }

  private handleConfirmation(payload: ConfirmationRequestPayload): void {
    this.waitingConfirmation = true
    this.clearThinkingLine()
    this.pausePrompt()
    console.log()
    this.printDivider(chalk.yellow)
    this.printRow(chalk.yellow(S.warn + ' ' + payload.title), chalk.yellow)
    payload.options.forEach((opt, i) => {
      console.log(chalk.yellow(S.vLine) + `   ${i + 1}. ${opt}`)
    })
    this.printRow(chalk.gray('请选择 (数字/回车默认/Esc取消)'), chalk.yellow)
    this.printDivider(chalk.yellow)

    const confirmRl = readline.createInterface({
      input: stdin,
      output: stdout,
    })

    confirmRl.question(chalk.gray(S.vLine + ' '), (answer) => {
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
      this.resumePrompt()
    })
  }
}
