# Claude Code TUI

一个基于Ink构建的Claude Code终端用户界面。

## 功能特性

- ✨ 完整的聊天界面
- 🎨 多主题支持（暗色、亮色、色盲友好、ANSI等）
- ⌨️ 键盘交互
- 💬 消息历史记录
- 📊 状态栏显示

## 主题

支持以下主题：
- `dark` - 暗色主题（默认）
- `light` - 亮色主题
- `dark-daltonized` - 色盲友好暗色主题
- `light-daltonized` - 色盲友好亮色主题
- `dark-ansi` - ANSI暗色主题
- `light-ansi` - ANSI亮色主题
- `auto` - 自动检测系统主题

## 安装

```bash
npm install
```

## 运行

开发模式：
```bash
npm run dev
```

生产构建：
```bash
npm run build
npm start
```

## 使用方法

1. 启动应用后，直接输入消息即可与Claude对话
2. 按回车键发送消息
3. 按 Ctrl+C 退出应用

## 技术栈

- [Ink](https://github.com/vadimdemedes/ink) - React for interactive command-line apps
- [React](https://reactjs.org/) - UI library
- [TypeScript](https://www.typescriptlang.org/) - Type-safe JavaScript

## 项目结构

```
src/
├── main.tsx          # 应用入口
└── theme/
    └── theme.ts      # 主题定义
```

## 后续计划

- [ ] 接入真实的Claude API
- [ ] 支持代码高亮显示
- [ ] 支持工具调用展示
- [ ] 实现系统主题自动检测
- [ ] 添加更多交互功能（如历史记录导航）
- [ ] 支持文件上传和下载
- [ ] 实现会话管理
