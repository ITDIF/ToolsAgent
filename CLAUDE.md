# CLAUDE.md

本地文件操作 Agent。LLM 通过工具调用操作用户本地文件。**写操作必经路径沙箱**,不能绕过。

## 命令

```bash
python -m pytest tests/ -v       # 跑测试
python main.py                   # 启动 CLI
```

## 关键约束

- **写操作必经 `path_safety.assert_safe_write_path`**:`file_ops` 中所有写函数(move/copy/delete/create/write/rename)开头都调用 `_safety_check`,新增写工具时务必比照添加。
- **search/list 是只读操作**,不走沙箱,但 `search_files` 必须遵守 `max_search_results` 与 `max_search_depth`,避免在大目录卡死。
- **`read_file` 受 `max_read_bytes` 限制**,超出截断并返回 `truncated:true`,不要去掉这个保护。
- **多轮工具循环上限是 `max_tool_iterations`**(默认 8),超过会落到 `chat()` 兜底总结。
- **消息格式由 Provider 决定**:agent 调用 `provider.build_assistant_message` / `build_tool_result_messages`,不要在 agent 里手拼 OpenAI/Anthropic 风格的消息。
- **撤销栈是全局 + 锁**:`_UNDO_STACK` 由 `_UNDO_LOCK` 保护;新增写工具必须在执行成功后调 `_push_undo({...})` 写入 action,撤销逻辑分支在 `_apply_undo_action` 里加。新增 action 类型时同步更新 `_describe_action`。
- **批量操作通过 `_BATCH_CONTEXT.sub_actions` 收集子撤销**:在 `batch_operations` 内调用的写函数会把 undo 写到 batch 里而非主栈,最终整个 batch 作为一条 `type=batch` 入栈、可一次回滚。`_BATCH_ALLOWED_TOOLS` 是子工具白名单,新增可批量调用的工具时记得加入。
- **测试涉及撤销栈时**,务必用 `clear_undo_stack()`(已在 `tests/test_undo.py` 用 autouse fixture 自动清理)避免污染。

## 数据目录

所有运行时数据落在 `~/.toolsagent/`:
- `config.json` — 用户配置(覆盖 `config.py:DEFAULT_CONFIG`)
- `sessions/*.json` — 会话历史
- `logs/YYYY-MM-DD.jsonl` — 操作日志(启动按 `log_retention_days` 清理)

不要把数据写到工程目录里。

## 添加新 LLM Provider

- **OpenAI 兼容**:继承 `OpenAICompatibleProvider`,只填 `api_key/base_url/model`,默认会复用 OpenAI 风格的 `build_assistant_message` / `build_tool_result_messages`。
- **非 OpenAI 兼容**:继承 `BaseLLMProvider`,实现 `chat`/`chat_with_tools`,**并务必重写 `build_assistant_message` 和 `build_tool_result_messages`**,使返回的 messages 符合该厂商原生格式(参见 `claude.py` 的 Anthropic block 写法)。
- 在 `main.py:MODEL_PROVIDERS` 注册,提供 `env_key/default_model/aliases/needs_endpoint/base_url_env/base_url_default`。

## 关于 .env

`.env` 是用户私密凭据,**不要读取、不要写入、不要提交**。`.env.example` 是模板,可以编辑。

## Claude 默认模型

默认 `claude-sonnet-4-6`(`providers/claude.py` 与 `main.py:MODEL_PROVIDERS`)。升级模型时这两处同步改。
