/**
 * 终端符号常量：Unicode 优先，ASCII 回退。
 *
 * 现代 IDE 终端、Windows Terminal 等都支持 Unicode 绘图字符，
 * 即使通过 pipe 连接（stdout.isTTY=false）显示能力也不受影响。
 * 仅在显式禁用或极简终端时回退 ASCII。
 */

const hasUnicode = !process.env.NO_UNICODE
  && process.env.TERM !== 'dumb'

export const S = {
  // 分隔线 & 边框
  hLine:    hasUnicode ? '─' : '-',
  vLine:    hasUnicode ? '│' : '|',

  // 提示符
  prompt:   hasUnicode ? '▸' : '>',
  cursor:   hasUnicode ? '▎' : '|',
  thinking: hasUnicode ? '⋯' : '...',

  // 状态
  dot:      hasUnicode ? '●' : '*',
  dotEmpty: hasUnicode ? '○' : 'o',
  check:    hasUnicode ? '✓' : 'v',
  cross:    hasUnicode ? '✗' : 'x',
  info:     hasUnicode ? 'ℹ' : 'i',
  warn:     hasUnicode ? '⚠' : '!',
  diamond:  hasUnicode ? '◆' : '>>',
  refresh:  hasUnicode ? '⟳' : '~',

  // 展开/折叠
  collapse: hasUnicode ? '▶' : '>',
  expand:   hasUnicode ? '▼' : 'v',

  // Spinner 动画帧
  spinner: hasUnicode
    ? ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    : ['|', '/', '-', '\\'],

  /** 生成指定宽度的水平线 */
  hLineN(n: number): string {
    return this.hLine.repeat(n)
  },
}
