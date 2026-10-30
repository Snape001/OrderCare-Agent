# State、Checkpoint 与会话记忆

## 两种客服 State

真实模式：`src/agents/customer_support_agent.py:build_customer_support_graph` 调用 `create_agent`，沿用其消息状态，核心是 `messages` 列表；每轮新增 `HumanMessage`、可能的 `AIMessage.tool_calls` / `ToolMessage`、最终 `AIMessage`。它没有项目自定义的 `current_order_id`、`active_task` 字段。模型可以读到同一会话的历史文本，但是否从旧对话提取订单号取决于模型与提示词，不能保证自动复用。

Mock 模式：`src/agents/customer_support_mock.py:CustomerSupportState` 扩展 `MessagesState`，定义 `pending_query: {intent, order_id?, phone_last4?} | None` 和 `pending_ticket | None`。`customer_support_node` 返回增量状态；`messages` 由 LangGraph reducer 追加，槽位由节点返回值覆盖。补参时保留有效参数，查询成功或取消后将 `pending_query` 设为 `None`。该槽位只表示**正在进行的任务**，并非跨任务用户资料；前轮查询成功后下一轮开始退款仍可能重新询问订单号。工单参数缺失时未建立完整待办状态，也不应夸称通用任务持久化。

## 保存、恢复与隔离

`src/service/service.py:lifespan` 用 `src/memory/__init__.py:initialize_database` 创建 saver 并绑定图。默认 `DATABASE_TYPE=sqlite`，`src/memory/sqlite.py:get_sqlite_saver` 使用 `settings.SQLITE_DB_PATH`（默认 `checkpoints.db`）；Postgres/Mongo 也有可配置适配，但当前默认部署并未使用。每次调用 `_handle_input` 先 `agent.aget_state` 检查同一内部 `thread_id` 的中断，正常轮次输入本轮 `HumanMessage`；执行时图从 Checkpoint 取回状态，图步骤由 saver 持久化。`/history` 读取状态快照的 `messages`。

Streamlit 在 `st.session_state` 中保存 UI 消息、公开 `thread_id` 和 `AgentClient`。`AgentClient` 生成随机 `X-Session-Token`；`src/service/access.py:session_identity` 校验并哈希该令牌，`checkpoint_thread(identity, agent_id, public_thread_id)` 派生内部 key。服务端还把请求中的 `user_id` 覆盖为令牌身份。因此只知道 URL 中的 `thread_id` 无法读取其他会话。`New Chat` 生成新 `thread_id`。如果刷新后客户端会话令牌变了，原公开 ID 也未必能恢复旧会话；这不是登录系统。

## 长期 Store 与业务数据库的区别

默认 `src/memory/sqlite.py:get_sqlite_store` 返回进程内 `InMemoryStore`，重启后不持久；它与 SQLite **Checkpoint** 不同。业务订单和工单走 `src/customer_support/store.py` 的本地 SQLite，若 `BUSINESS_DATABASE_TYPE=mysql` 则走 `mysql_store.py`；这两个业务存储也不是对话记忆。Docker Compose 设置业务 MySQL、Checkpoint SQLite。政策 Markdown/Chroma 是知识库，同样不是会话记忆。

## 人工确认与局限

真实图在 `create_support_ticket` 前经 `HumanInTheLoopMiddleware` 暂停，Checkpoint 保存中断；下一轮 `_handle_input` 读取 `state.tasks[].interrupts` 并构造 `Command(resume=...)`。Mock 则把 `pending_ticket` 写入 State，明确确认后才调用写入函数。当前缺少“已验证的当前订单”跨任务槽位及生命周期规则；这正解释“前文给过订单号，下一轮想退款又被追问”的可能行为，不能把已有 Checkpoint 等同于完整业务记忆。
