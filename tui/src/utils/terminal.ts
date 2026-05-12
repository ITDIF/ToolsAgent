/** 终端能力检测 */

export interface TerminalInfo {
  isTTY: boolean
  supportsRawMode: boolean
  mode: 'full' | 'fallback'
  isIDE: boolean
}

export function detectTerminal(): TerminalInfo {
  const isTTY = !!process.stdin.isTTY
  let supportsRawMode = false

  if (isTTY) {
    try {
      process.stdin.setRawMode(true)
      process.stdin.setRawMode(false)
      supportsRawMode = true
    } catch {
      supportsRawMode = false
    }
  }

  const ideIndicators = [
    'IDEA_INITIAL_DIRECTORY',   // JetBrains
    'TERMINAL_EMULATOR',        // 各种 IDE
    'VSCODE_CWD',              // VS Code
    'ELECTRON_RUN_AS_NODE',    // Electron-based
  ]
  const isIDE = ideIndicators.some(k => !!process.env[k])

  const mode: TerminalInfo['mode'] =
    (isTTY && supportsRawMode) ? 'full' : 'fallback'

  return { isTTY, supportsRawMode, mode, isIDE }
}

export function detectPreferredTheme(): 'dark' | 'light' {
  // 简单启发式：IDE 终端通常有暗色主题
  if (process.env.TERM_PROGRAM === 'vscode') return 'dark'
  if (process.env.COLORFGBG) {
    const parts = process.env.COLORFGBG.split(';')
    if (parts.length >= 2 && parseInt(parts[0]) < 8) return 'light'
  }
  return 'dark'
}
