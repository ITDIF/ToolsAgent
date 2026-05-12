
# ToolsAgent - 本地文件操作助手

通过自然语言对话操作本地文件的 AI 助手。

## 功能

### 文件操作
- 移动文件/文件夹
- 复制文件/文件夹
- 删除文件/文件夹（带确认）
- 创建文件夹
- 创建文件（支持指定内容）
- 读取文件内容
- 写入文件内容（覆盖/追加）
- 重命名文件/文件夹
- 搜索文件/文件夹
- 列出文件
- **压缩文件/文件夹**（支持 zip、tar、tar.gz、tgz、tar.bz2、rar）
- **解压压缩文件**（支持 zip、tar、tar.gz、tgz、tar.bz2、rar）

### 增强功能
- 会话历史持久化
- 操作日志记录
- 多模型支持
- 工具执行超时保护（默认30秒）
- 可配置参数（通过 `~/.toolsagent/config.json`）
- 命令缩写支持
- 撤销最近的操作（支持指定步数）
- 批量执行多个操作（失败可一次撤销全部）
- **压缩/解压文件**（支持 zip、tar、tar.gz、tgz、tar.bz2、rar）
- 🎨 **现代化 TUI 界面**：基于 Ink 的交互式终端用户界面（可选）

## 支持的模型

| 模型 | 厂商 | 环境变量 |
|------|------|----------|
| **Claude** | Anthropic | `ANTHROPIC_API_KEY` |
| **Kimi** | 月之暗面 | `KIMI_API_KEY` |
| **豆包** | 字节跳动 | `DOUBAO_API_KEY` |
| **GLM** | 智谱 AI | `GLM_API_KEY` |
| **小米** | MIMO | `XIAOMI_API_KEY` |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入对应模型的 API Key：

```
# Claude (Anthropic)
ANTHROPIC_API_KEY=sk-ant-...

# Kimi (月之暗面)
KIMI_API_KEY=sk-...

# 豆包 (字节跳动)
DOUBAO_API_KEY=...
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# GLM (智谱 AI)
GLM_API_KEY=...

# 小米 (MIMO)
XIAOMI_API_KEY=...
XIAOMI_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
```

### 3. 运行

#### 传统 CLI 模式（默认）

```bash
python -m src.cli.main
```

或者安装为命令行工具：

```bash
pip install -e .
toolsagent
```

#### 现代化 TUI 模式（可选）

需要先安装 Node.js 依赖：

```bash
cd tui
npm install
cd ..
```

然后启动 TUI 界面：

```bash
python -m src.cli.main --tui
```

或者：

```bash
toolsagent --tui
```

## 使用示例

```
你: 创建一个名为 test 的文件夹
即将执行: 创建文件夹 test
确认执行? (y/n): y
助手: 已成功创建 test 文件夹。

你: 列出当前目录的文件
助手: 当前目录包含以下内容...

你: 读取 README.md 的内容
助手: 文件内容...

你: 把 data 文件夹压缩成 backup.zip
助手: 已创建压缩文件: backup.zip

你: 解压 archive.tar.gz
助手: 已解压: archive.tar.gz -> archive/
```

## 特殊命令

支持命令缩写，方便快捷操作：

| 命令 | 缩写 |
|------|------|
| `/help` | `/h` |
| `/history` | `/his` |
| `/logs` | `/l`, `/log` |
| `/save` | `/s` |
| `/model` | `/m` |
| `/undo` | `/u` |
| `/undo-list` | `/ul` |
| `/quit` | `/q`, `/exit` |

## 配置

配置文件位于 `~/.toolsagent/config.json`：

```json
{
  "tool_timeout": 30,
  "default_model": "mimo-v2.5",
  "log_retention_days": 30,
  "max_search_results": 100,
  "max_search_depth": 10,
  "max_tool_iterations": 8,
  "max_read_bytes": 1048576,
  "confirm_delete": true,
  "confirm_overwrite": true,
  "allowed_roots": []
}
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `tool_timeout` | 30 | 工具执行超时时间（秒） |
| `default_model` | mimo-v2.5 | 默认模型 |
| `log_retention_days` | 30 | 日志保留天数（启动时清理） |
| `max_search_results` | 100 | 搜索结果最大数量，触顶返回 `truncated:true` |
| `max_search_depth` | 10 | 搜索递归最大目录深度 |
| `max_tool_iterations` | 8 | 单次请求允许的最大工具调用轮次 |
| `max_read_bytes` | 1048576 | 读文件最大字节数（默认 1MB），超出截断并标记 |
| `confirm_delete` | true | 删除前是否确认 |
| `confirm_overwrite` | true | 覆盖写入前是否确认 |
| `allowed_roots` | [] | 写操作白名单根目录列表；为空时启用系统目录黑名单 |
| `rar_executable` | "" | RAR/WinRAR 可执行文件路径（用于创建 .rar 压缩文件） |

## 支持的压缩格式

| 操作 | 支持格式 |
|------|----------|
| **压缩** | `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.rar`（需安装 RAR/WinRAR） |
| **解压** | `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.rar`（需安装 rarfile + unrar） |

## 数据存储位置

所有数据存储在 `~/.toolsagent/` 目录下：
- `~/.toolsagent/sessions/` - 会话历史
- `~/.toolsagent/logs/` - 操作日志
- `~/.toolsagent/config.json` - 配置文件

## 测试

```bash
python -m pytest tests/ -v
```

## 扩展新的 LLM Provider

### OpenAI 兼容 API

继承 `OpenAICompatibleProvider`，只需配置参数：

```python
from providers.base import OpenAICompatibleProvider

class MyProvider(OpenAICompatibleProvider):
    def __init__(self, api_key=None, model="my-model"):
        super().__init__(
            api_key=api_key or os.getenv("MY_API_KEY"),
            base_url="https://api.example.com/v1",
            model=model
        )
```

### 其他 API

继承 `BaseLLMProvider`，实现 `chat()` 和 `chat_with_tools()` 方法。

## 项目结构（2025年重构）

项目已重构为分层架构，提供更好的可维护性和可扩展性。详细说明请查看 [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md)。

```
ToolsAgent/
├── main.py                    # 入口点
├── src/
│   ├── cli/                   # 命令行界面层
│   │   └── main.py            # CLI 入口
│   ├── core/                  # 核心逻辑层
│   │   ├── agent.py           # FileAgent 主类
│   │   └── llm/               # LLM 适配层
│   │       ├── base.py        # 抽象基类
│   │       ├── claude.py      # Claude 实现
│   │       ├── kimi.py        # Kimi 实现
│   │       ├── doubao.py      # 豆包 实现
│   │       ├── glm.py         # GLM 实现
│   │       └── xiaomi.py      # 小米 实现
│   ├── file/                  # 文件操作层
│   │   ├── basic.py           # 基础文件操作
│   │   └── archive.py         # 压缩/解压操作
│   ├── security/              # 安全层
│   │   ├── sandbox.py         # 路径安全校验
│   │   └── undo.py            # 撤销功能管理
│   ├── infra/                 # 基础设施层
│   │   ├── config.py          # 配置管理
│   │   ├── session.py         # 会话管理
│   │   └── utils.py           # 工具函数
│   └── ui/                    # 用户界面层
│       ├── tui.py             # 终端 UI 组件
│       ├── console.py         # 控制台输出工具
│       └── prompts.py         # 用户提示
├── tui/                       # 现代化 TUI 界面（基于 Node.js/Ink）
│   ├── src/
│   │   ├── main.tsx           # TUI 入口
│   │   └── theme/
│   │       └── theme.ts       # 主题定义
│   ├── package.json           # Node.js 依赖
│   ├── tsconfig.json          # TypeScript 配置
│   └── README.md              # TUI 文档
├── tests/                     # 单元测试
├── requirements.txt           # 依赖
├── .env                       # 环境变量
├── .env.example               # 环境变量示例
├── README.md                  # 文档
└── PROJECT_STRUCTURE.md       # 架构说明
```

### 旧结构（归档）

```
ToolsAgent/
├── main.py                    # CLI 入口
├── agent.py                   # Agent 协调层
├── config.py                  # 配置管理
├── file_ops.py                # 文件操作工具
├── path_safety.py             # 路径安全校验
├── utils.py                   # 工具函数
├── session.py                 # 会话管理
├── undo_manager.py            # 撤销管理
├── tui.py                     # 终端 UI 组件
└── providers/                 # LLM 提供商
    ├── __init__.py
    ├── base.py
    ├── claude.py
    ├── kimi.py
    ├── doubao.py
    ├── glm.py
    └── xiaomi.py
```

