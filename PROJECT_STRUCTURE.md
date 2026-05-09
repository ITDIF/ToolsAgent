# 项目架构重构说明

## 新的项目结构

```
ToolsAgent/
├── src/
│   ├── cli/                  # 命令行界面层
│   │   └── main.py          # 主程序入口
│   ├── core/                 # 核心逻辑层
│   │   ├── agent.py         # FileAgent 主类
│   │   └── llm/             # LLM 适配层
│   │       ├── base.py      # 基类定义
│   │       ├── claude.py    # Claude 适配
│   │       ├── kimi.py      # Kimi 适配
│   │       ├── doubao.py    # 豆包适配
│   │       ├── glm.py       # GLM 适配
│   │       └── xiaomi.py    # 小米 MIMO 适配
│   ├── file/                # 文件操作层
│   │   ├── basic.py         # 基础文件操作
│   │   └── archive.py       # 归档/压缩操作
│   ├── security/            # 安全层
│   │   ├── sandbox.py       # 路径安全沙箱
│   │   └── undo.py          # 撤销功能管理
│   ├── infra/               # 基础设施层
│   │   ├── config.py        # 配置管理
│   │   ├── session.py       # 会话管理
│   │   └── utils.py         # 工具函数
│   └── ui/                 # 用户界面层
│       ├── tui.py          # 终端 UI 组件
│       ├── console.py      # 控制台输出工具
│       └── prompts.py      # 用户提示
├── tests/                  # 测试文件
├── main.py                # 入口点
└── pyproject.toml         # 项目配置
```

## 分层说明

### CLI 层 (`src/cli/`)
- 处理命令行参数
- 提供用户友好的交互界面
- 协调各组件之间的工作

### 核心层 (`src/core/`)
- `agent.py`: 主要的 FileAgent 类，协调整个流程
- `llm/`: 包含各种 LLM 提供商的适配器

### 文件操作层 (`src/file/`)
- `basic.py`: 移动、复制、删除、创建、读写等基础操作
- `archive.py`: 压缩和解压缩功能

### 安全层 (`src/security/`)
- `sandbox.py`: 路径安全检查，防止危险操作
- `undo.py`: 撤销功能管理，记录和恢复操作

### 基础设施层 (`src/infra/`)
- `config.py`: 配置加载和管理
- `session.py`: 会话历史管理
- `utils.py`: 日志和其他工具函数

### 用户界面层 (`src/ui/`)
- `tui.py`: 跨平台的终端 UI 组件
- `console.py`: 控制台颜色和格式化输出
- `prompts.py`: 用户确认和授权提示

## 重构改进

1. **更清晰的代码组织**: 相关功能放在同一模块中
2. **更好的可维护性**: 分层架构使得修改某部分功能不会影响其他部分
3. **可扩展性**: 新增 LLM 提供商或文件操作功能更加容易
4. **保持向后兼容**: 所有功能保持原样，只是重新组织了文件结构

## 测试状态

✅ TUI 测试: 11/11 通过  
✅ 文件操作测试: 40/40 通过  
✅ 路径安全测试: 18/18 通过  
✅ 撤销功能测试: 37/37 通过  
✅ 会话管理测试: 6/6 通过  

总计: **112/113** 测试通过 (1个跳过)
