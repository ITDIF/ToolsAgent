
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

### 增强功能
- 会话历史持久化
- 操作日志记录
- 多模型支持
- 工具执行超时保护（默认30秒）
- 可配置参数（通过 `~/.toolsagent/config.json`）

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

```bash
python main.py
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
```

## 特殊命令

- `quit/exit/退出` - 退出程序
- `save` - 手动保存会话

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

## 项目结构

```
ToolsAgent/
├── main.py                    # CLI 入口
├── agent.py                   # Agent 协调层（多轮工具循环）
├── config.py                  # 配置管理
├── file_ops.py                # 文件操作工具（写操作走路径沙箱）
├── path_safety.py             # 路径安全校验（黑/白名单）
├── utils.py                   # 工具函数（日志写入与清理）
├── session.py                 # 会话管理
├── requirements.txt           # 依赖
├── .env                       # 环境变量
├── .env.example               # 环境变量示例
├── README.md                  # 文档
├── tests/                     # 单元测试
│   ├── test_file_ops.py       # 文件操作测试
│   ├── test_session.py        # 会话管理测试
│   ├── test_token.py          # Token 计数测试
│   └── test_utils.py          # 工具函数测试
└── providers/
    ├── __init__.py            # 导出
    ├── base.py                # 抽象基类 + OpenAI 兼容基类（含消息格式化）
    ├── claude.py              # Claude 实现（Anthropic 原生 block 格式）
    ├── kimi.py                # Kimi 实现
    ├── doubao.py              # 豆包 实现
    ├── glm.py                 # GLM 实现
    └── xiaomi.py              # 小米 实现
```

