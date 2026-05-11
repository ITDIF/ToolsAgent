# Claude Code TUI Clone - Implementation Plan

## Context

The goal is to build a **complete terminal TUI clone** of Claude Code that visually matches its interface, supports **multiple LLM providers** (Claude API, OpenAI, Ollama/local), and lives inside the existing repo at `E:\project\AIprojects\claude_code_src\tui\`.

The source code contains a sophisticated custom Ink framework (React reconciler + Yoga layout + terminal rendering), 130+ UI components, 40+ tools, and a complex streaming/permission system. This plan pragmatically rebuilds these using the standard npm `ink` package as foundation, porting the theme colors and component patterns directly from source.

---

## Key Architecture Decisions

1. **Use npm `ink` v5** instead of forking the custom `src/ink/` framework - the custom one is deeply coupled to `bun:bundle`, native Yoga bindings, and internal React reconciler APIs
2. **Canonical message format follows Anthropic's structure** - most expressive for tool use; OpenAI/Ollama adapters translate at the boundary
3. **Zustand for state** - simpler than the source's custom `useSyncExternalStore` store
4. **Tool system is a clean subset** of the source's `Tool.ts` interface (~8 methods vs 30+)
5. **Theme definitions directly portable** from `src/utils/theme.ts` - pure data with RGB/ANSI values
6. **No runtime dependency on `src/`** - source is reference only, no imports

---

## Source Architecture Analysis

### Custom Ink TUI Framework (src/ink/)

Claude Code 没有使用 npm 上的 ink 包，而是构建了一套自定义的 React 终端渲染框架：

| 文件 | 作用 |
|------|------|
| `src/ink/reconciler.ts` | 自定义 React reconciler，使用 `react-reconciler` 创建终端 DOM 抽象 |
| `src/ink/ink.tsx` | 主渲染器入口，管理 React FiberRoot、帧渲染循环、终端 I/O |
| `src/ink/render-node-to-output.ts` | 将 DOM 节点转换为终端输出（ANSI 转义码） |
| `src/ink/render-to-screen.ts` | 虚拟屏幕缓冲区，计算最小 diff |
| `src/ink/log-update.ts` | 屏幕更新 diff 算法，最小化终端写入 |
| `src/ink/screen.ts` | 屏幕 Cell 缓冲区（StylePool/CharPool/HyperlinkPool） |
| `src/ink/dom.ts` | 终端 DOM 抽象：ink-box, ink-text, ink-virtual-text, ink-link |
| `src/ink/styles.ts` | CSS 样式到 Yoga 属性的映射 |
| `src/ink/selection.ts` | 终端文本选择（鼠标/键盘） |
| `src/ink/terminal.ts` | 终端能力检测、ANSI 转义码处理 |

**渲染管线**: React Components → Reconciler → DOM Tree → Yoga Layout → render-node-to-output → log-update (diff) → terminal write

### Component Hierarchy

```
App.tsx (ThemeProvider + StatsProvider + FpsMetricsProvider)
  └── REPL.tsx (主屏幕)
        ├── Messages.tsx (消息列表容器)
        │     └── VirtualMessageList.tsx (虚拟化滚动)
        │           └── Message.tsx (类型分发器)
        │                 ├── AssistantTextMessage.tsx
        │                 ├── AssistantThinkingMessage.tsx
        │                 ├── AssistantToolUseMessage.tsx
        │                 ├── UserTextMessage.tsx
        │                 ├── UserToolResultMessage/
        │                 │     ├── UserToolSuccessMessage.tsx
        │                 │     ├── UserToolErrorMessage.tsx
        │                 │     └── UserToolCanceledMessage.tsx
        │                 ├── CompactBoundaryMessage.tsx
        │                 └── SystemTextMessage.tsx
        ├── PromptInput/PromptInput.tsx (输入框)
        │     ├── BaseTextInput.tsx
        │     ├── VimTextInput.tsx
        │     └── PromptInputFooter.tsx
        ├── StatusLine.tsx (底部状态栏)
        └── PermissionRequest.tsx (权限对话框)
```

### Theme System (src/utils/theme.ts)

- **6 套主题**: dark, light, dark-ansi, light-ansi, dark-daltonized, light-daltonized
- **89 个颜色 token**: claude(橙), permission(蓝), success, error, warning, diff, agent 等
- **RGB 颜色值** + ANSI 16 色降级方案
- 通过 `useTheme()` hook 访问

### Tool System (src/Tool.ts, src/tools/)

40+ 工具，每个工具包含：
- `name`: 工具名称
- `inputSchema`: Zod 验证
- `call()`: 执行逻辑
- `checkPermissions()`: 权限检查
- `renderToolUseMessage()`: 工具调用 UI
- `renderToolResultMessage()`: 工具结果 UI

核心工具: BashTool, FileReadTool, FileEditTool, FileWriteTool, GlobTool, GrepTool, WebSearchTool, WebFetchTool, AgentTool 等

### Streaming & Query (src/query.ts)

AsyncGenerator 流式管线：
1. 发送消息到 Claude API
2. 流式接收 ContentBlockDelta
3. 处理 tool_use → 执行工具 → 追加 tool_result → 重新查询
4. 上下文压缩、token 预算管理

### Permission System (src/types/permissions.ts, src/utils/permissions/)

- **7 种权限模式**: default, acceptEdits, bypassPermissions, plan, dontAsk, auto, bubble
- 规则引擎: allow/deny/ask 规则匹配
- auto 模式: AI 分类器自动决策

---

## Project Structure

```
tui/
  package.json
  tsconfig.json
  src/
    main.ts                          # Entry point: CLI args, boot
    app.tsx                          # Root component with providers

    # -- Provider abstraction layer --
    providers/
      types.ts                       # Provider, CanonicalMessage, StreamEvent types
      claude-provider.ts             # Anthropic Claude API adapter
      openai-provider.ts             # OpenAI API adapter
      ollama-provider.ts             # Ollama local model adapter
      provider-factory.ts            # Creates provider from config

    # -- Tool system --
    tools/
      types.ts                       # Tool interface (simplified)
      registry.ts                    # Tool registration/lookup
      bash-tool.ts
      file-read-tool.ts
      file-edit-tool.ts
      file-write-tool.ts
      glob-tool.ts
      grep-tool.ts
      web-fetch-tool.ts
      web-search-tool.ts

    # -- Permission system --
    permissions/
      types.ts                       # PermissionMode, PermissionResult
      manager.ts                     # Permission checking
      rules.ts                       # Rule-based allow/deny/ask

    # -- Theme system --
    theme/
      theme.ts                       # 6 theme definitions (ported from src/utils/theme.ts)
      theme-provider.tsx             # React context
      themed-text.tsx                # <Text> with theme color resolution
      themed-box.tsx                 # <Box> with theme border/bg resolution

    # -- Core UI components --
    components/
      repl.tsx                       # Main REPL layout
      messages/
        message-list.tsx             # Virtualized scrollable message list
        message.tsx                  # Type dispatcher
        assistant-text.tsx           # Assistant text messages
        assistant-tool-use.tsx       # Tool use blocks (collapsible)
        assistant-thinking.tsx       # Thinking/reasoning blocks
        user-text.tsx                # User text messages
        system-message.tsx           # System info/error messages
        tool-result.tsx              # Tool result display
      prompt/
        prompt-input.tsx             # Input with vim/emacs modes
        vim-engine.ts                # Vim state machine (ported)
        history.ts                   # Command history navigation
        typeahead.ts                 # Slash command completion
        suggestions.tsx              # Suggestion chips
      permission-dialog.tsx          # Permission request overlay
      status-line.tsx                # Bottom status bar
      spinner.tsx                    # Animated spinner
      markdown.tsx                   # Terminal markdown renderer
      diff-view.tsx                  # File diff display
      scroll-box.tsx                 # Custom scrollable container

    # -- Query/streaming engine --
    engine/
      query.ts                       # Query orchestration
      stream-handler.ts              # Stream event processing
      message-store.ts               # Zustand message store
      context-manager.ts             # Token tracking / compaction

    # -- Configuration --
    config/
      config.ts                      # Provider keys, preferences
      keybindings.ts                 # Keybinding definitions

    # -- Utilities --
    utils/
      terminal.ts                    # Terminal capability detection
      ansi.ts                        # ANSI escape helpers
      text-width.ts                  # String width (CJK support)
```

---

## Implementation Phases

### Phase 1: Foundation - Boot + Theme + Layout

**Goal**: 启动终端应用，包含主题支持、输入框和消息显示区域。

**Deliverables**:

1. 项目脚手架: `package.json`, `tsconfig.json`, 构建脚本
2. `main.ts` - 解析 CLI 参数，检测终端能力，渲染 `<App>`
3. 主题系统: 从 `src/utils/theme.ts` 移植全部 6 套主题定义（精确 RGB/ANSI 值），实现 `ThemeProvider` context，`ThemedText`/`ThemedBox` 组件
4. `repl.tsx` - 基础布局: `<Box flexDirection="column">` 消息区(上, flexGrow=1) + 输入框(下)
5. `prompt-input.tsx` - 基础多行输入，Enter 提交，Shift+Enter 换行
6. `message-list.tsx` - 简单滚动列表（初始不做虚拟化）
7. `status-line.tsx` - 底部栏显示 provider 名称、模型、权限模式、cwd

**Dependencies**: ink v5, react v18, zod, chalk

**Reference files**:
- `src/utils/theme.ts` (L1-640) - Theme type + all color definitions
- `src/components/design-system/ThemeProvider.tsx` - Provider pattern
- `src/components/design-system/ThemedText.tsx` - Color resolution
- `src/screens/REPL.tsx` - Layout structure

---

### Phase 2: Provider Abstraction + Claude API Streaming

**Goal**: 连接 Claude API 实现流式响应，在 UI 中展示 assistant 消息。

**Deliverables**:

1. `providers/types.ts` - 定义规范类型:
   ```
   ProviderMessage: { role, content: ContentBlock[] }
   ContentBlock: TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock
   StreamEvent: MessageStart | ContentBlockStart | ContentBlockDelta | ContentBlockStop | MessageStop
   Provider: { name, sendMessage(messages, tools, options) -> AsyncIterable<StreamEvent> }
   ```
2. `providers/claude-provider.ts` - 封装 `@anthropic-ai/sdk`，通过 SDK `stream()` 方法实现流式
3. `engine/query.ts` - 查询循环: 接收用户消息 → 发送给 provider → 处理流事件 → 追加到消息存储 → 处理工具调用
4. `engine/stream-handler.ts` - 将 StreamEvent 处理为增量 UI 更新
5. `engine/message-store.ts` - Zustand store: messages[], addMessage, updateMessage, appendDelta
6. `components/messages/assistant-text.tsx` - 流式文本渲染
7. `components/messages/assistant-thinking.tsx` - 思考块（可折叠、灰色）
8. `components/spinner.tsx` - API 调用期间动画 spinner

**Dependencies**: @anthropic-ai/sdk, zustand

**Key insight**: 源码 `query.ts` 有 70K+ 行（含压缩、token 预算、工具编排等）。克隆版初始 query 引擎约 500-800 行即可。

**Provider type design**: 规范格式采用 Anthropic 结构，因为：
- Tool use 是一级内容块类型（非独立字段）
- Thinking/reasoning blocks 是原生支持的
- 源码 `Tool.ts` 已输出 `ToolUseBlockParam`/`ToolResultBlockParam`

---

### Phase 3: Tool System

**Goal**: 实现核心工具，包含执行、UI 渲染和权限检查。

**Deliverables**:

1. `tools/types.ts` - 简化 Tool 接口:
   ```
   Tool<I, O>: {
     name: string
     description: string
     inputSchema: ZodSchema
     call(input, context) -> Promise<ToolResult<O>>
     renderToolUse(input) -> ReactNode
     renderToolResult(output) -> ReactNode
     checkPermissions(input, context) -> Promise<PermissionResult>
     isReadOnly(input): boolean
   }
   ```
   这是源码 `Tool.ts` (L362-695) 的干净子集。`buildTool()` helper (L783-792) 直接移植。

2. 核心工具实现:
   - `bash-tool.ts` - Shell 命令执行，移植安全模式从 `src/tools/BashTool/bashPermissions.ts`（简化版）
   - `file-read-tool.ts` - 文件读取（含行范围）
   - `file-edit-tool.ts` - 搜索/替换编辑
   - `file-write-tool.ts` - 完整文件写入
   - `glob-tool.ts` - 文件模式匹配 (fast-glob)
   - `grep-tool.ts` - 内容搜索
   - `web-fetch-tool.ts` - URL 内容获取
   - `web-search-tool.ts` - Web 搜索

3. `tools/registry.ts` - 工具注册: 名称→实例映射

4. 工具 UI 组件:
   - `assistant-tool-use.tsx` - 工具名称 + 输入摘要，可折叠
   - `tool-result.tsx` - 工具输出/错误
   - `diff-view.tsx` - 文件编辑内联 diff
   - `markdown.tsx` - Markdown 渲染

**Dependencies**: fast-glob, chalk

---

### Phase 4: Permission System

**Goal**: 交互式权限提示，匹配 Claude Code 的视觉设计。

**Deliverables**:

1. `permissions/types.ts`:
   - `PermissionMode`: `'default' | 'acceptEdits' | 'bypassPermissions' | 'plan'`
   - `PermissionResult`: `{ behavior: 'allow' | 'deny' | 'ask', ... }`
   - `PermissionRule`: `{ toolName, ruleContent?, behavior }`

2. `permissions/manager.ts` - 规则评估引擎:
   - 从配置文件加载规则
   - `default` 模式: bash/file write/file edit 需询问; file read/glob/grep 允许
   - `acceptEdits` 模式: 文件操作允许, bash 需询问
   - `bypassPermissions` 模式: 全部允许
   - `plan` 模式: 全部拒绝（仅规划）

3. `permissions/rules.ts` - 工具特定规则的模式匹配

4. `components/permission-dialog.tsx`:
   - 显示工具名称、输入摘要、风险级别
   - 选项: 允许一次、总是允许(添加规则)、拒绝
   - 蓝色 (`permission` color) 边框装饰

---

### Phase 5: Multi-Provider Support (OpenAI + Ollama)

**Goal**: 支持 OpenAI 和 Ollama 作为替代后端。

**Deliverables**:

1. `providers/openai-provider.ts`:
   - 封装 `openai` npm 包
   - 消息格式转换:
     - Canonical `ToolUseBlock` → OpenAI `tool_calls[]` array
     - Canonical `ToolResultBlock` → OpenAI `role="tool"` message with `tool_call_id`
   - 流处理: OpenAI delta → canonical `ContentBlockDelta` events
   - System prompt: OpenAI 使用独立 `system` 字段

2. `providers/ollama-provider.ts`:
   - Ollama 使用 OpenAI 兼容 API (`http://localhost:11434/v1`)
   - 可扩展 OpenAI provider
   - 工具调用支持因模型而异 (llama3.1+ 支持)

3. `providers/provider-factory.ts`:
   - 读取配置: `{ provider: "claude" | "openai" | "ollama", apiKey?, model, baseUrl? }`
   - 支持 `--provider` CLI 标志和 `CLAUDE_TUI_PROVIDER` 环境变量
   - 运行时切换 (`/provider ollama` 命令)

**Provider 差异对照**:

| Feature | Claude | OpenAI | Ollama |
|---------|--------|--------|--------|
| Tool calling format | `tool_use` content blocks | `function_calling` in message | OpenAI-compatible |
| Streaming | Native SSE with content block deltas | SSE with delta types | OpenAI-compatible |
| System prompt | System message in array | Separate `system` field | Varies |
| Thinking/reasoning | `thinking` content blocks | No native support | No native support |
| Parallel tools | Yes | Yes (configurable) | Limited |
| Image input | Yes (base64) | Yes (base64/URL) | Limited |

**Adapter pattern**: 每个 adapter 负责:
1. 消息格式翻译（canonical ↔ native）
2. 流事件翻译（native SSE → canonical events）
3. 工具定义翻译（Zod schema → provider-native JSON schema）
4. 功能能力报告

查询引擎永远不看到 provider 特定格式，只发出 canonical `StreamEvent`。

---

### Phase 6: Vim Mode + Advanced Input

**Goal**: 完整 vim 模式，历史搜索，slash 命令。

**Deliverables**:

1. `prompt/vim-engine.ts` - 从源码移植 vim 状态机:
   - `src/vim/types.ts` 的类型定义（~200 行，零依赖，可直接移植）
   - CommandState 状态机: idle → operator → motion → execute
   - PersistentState for dot-repeat, registers, last-find

2. `prompt/prompt-input.tsx` 增强:
   - Vim 模式切换 (默认关闭, `--vim` 或配置启用)
   - INSERT 模式: 标准文本输入
   - NORMAL 模式: vim motions (h,l,j,k,w,b,e,0,^,$), operators (d,c,y), text objects (iw,aw)
   - 当前模式视觉指示器

3. `prompt/history.ts`:
   - 上下箭头历史导航
   - Ctrl+R 历史搜索
   - 持久化历史文件 `~/.claude-tui/history`

4. `prompt/typeahead.ts`:
   - Slash 命令补全 (`/help`, `/model`, `/theme`, `/provider`, `/clear` 等)
   - Tab 接受, Escape 取消

**Reference files**:
- `src/vim/types.ts` - Vim state machine types
- `src/vim/transitions.ts` - State transitions
- `src/vim/operators.ts`, `src/vim/motions.ts` - Operators and motions

---

### Phase 7: Polish + Advanced Features

**Goal**: 匹配 Claude Code 的视觉保真度，添加剩余功能。

**Deliverables**:

1. **虚拟滚动** - `message-list.tsx`:
   - 只渲染可见消息 + 上下缓冲区
   - 新消息自动滚到底部，手动滚动暂停自动
   - 移植 `src/components/VirtualMessageList.tsx` 概念

2. **搜索/高亮** - Ctrl+F 搜索消息，高亮匹配

3. **上下文压缩** - `context-manager.ts`:
   - 跟踪每条消息的 token 使用
   - 接近限制时压缩旧消息为摘要

4. **会话持久化** - 保存/恢复会话到 `~/.claude-tui/sessions/`

5. **Markdown 渲染增强** - 标题、加粗、斜体、代码块(语法高亮)、链接、列表

6. **主题选择器** - 6 套主题实时预览

7. **Diff 渲染** - 文件编辑操作的 inline diff

8. **完整 Slash 命令**: /help, /model, /provider, /theme, /clear, /compact, /vim, /permissions, /cost

---

## Dependencies

```json
{
  "dependencies": {
    "ink": "^5.0.0",
    "react": "^18.3.0",
    "@anthropic-ai/sdk": "^0.40.0",
    "openai": "^4.70.0",
    "zod": "^3.23.0",
    "zustand": "^5.0.0",
    "chalk": "^5.3.0",
    "fast-glob": "^3.3.0",
    "cli-highlight": "^2.2.0",
    "marked": "^14.0.0",
    "string-width": "^7.0.0",
    "wrap-ansi": "^9.0.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "@types/react": "^18.3.0",
    "tsx": "^4.19.0",
    "esbuild": "^0.24.0"
  }
}
```

---

## Verification

| Phase | 验证方法 |
|-------|---------|
| Phase 1 | `npx tsx src/main.ts` → 看到主题化 REPL shell、输入框、状态栏 |
| Phase 2 | 输入消息 → 收到流式 Claude 响应 |
| Phase 3 | 让 Claude 编辑文件 → 看到 tool use 块、权限提示、执行结果 |
| Phase 4 | 切换权限模式，验证 allow/deny/ask 行为 |
| Phase 5 | `/provider` 切换 provider，验证每个的流式工作 |
| Phase 6 | `/vim` 切换 vim 模式，测试 motions/operators/insert |
| Phase 7 | 100+ 消息虚拟滚动、搜索、会话恢复 |

---

## Critical Source Files (Reference Only)

| Source File | What to Port |
|-------------|-------------|
| `src/utils/theme.ts` (L1-640) | 全部 6 套主题定义（精确 RGB/ANSI 值） |
| `src/Tool.ts` (L362-792) | Tool interface + `buildTool()` helper pattern |
| `src/vim/types.ts` | Vim state machine (可直接移植，~200行，零依赖) |
| `src/components/design-system/ThemedText.tsx` | Theme color resolution pattern |
| `src/components/design-system/ThemeProvider.tsx` | Provider context structure |
| `src/types/permissions.ts` | Permission types (subset) |
| `src/types/message.ts` | Message type structure (canonical format reference) |
| `src/query.ts` | Query loop pattern (simplified) |
| `src/components/messages/AssistantToolUseMessage.tsx` | Tool use rendering pattern |
| `src/components/StructuredDiff.tsx` | Diff rendering pattern |
| `src/components/VirtualMessageList.tsx` | Virtual scrolling concept |
| `src/components/PromptInput/PromptInput.tsx` | Input component structure |
| `src/components/StatusLine.tsx` | Status bar layout |
