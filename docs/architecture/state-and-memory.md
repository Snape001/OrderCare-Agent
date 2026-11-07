# State、Checkpoint 与分层 Memory

## 客服图的 State

`src/agents/customer_support_agent.py:build_customer_support_graph` 基于 LangChain `create_agent` 构图，沿用 LangGraph 的 `messages` 累加状态；Router 中间件还写入结构化 `route`、`plan` 和 `task_trace`。模型的工具调用是 `AIMessage.tool_calls`，执行结果是配对的 `ToolMessage`。Router 使用当前 Provider 的结构化输出；单意图生成简单计划，多意图或条件请求才调用 Planner。审批恢复时不重新路由。它是框架生成的 Agent 图和中间件，不是仓库手写的通用 DAG 引擎。详见[执行链](agent-execution-flow.md)与[Router / Planner](router-planner.md)。

## Checkpoint、会话隔离与审批

`src/service/service.py:lifespan` 为图绑定 SQLite saver（默认 `DATABASE_TYPE=sqlite`，`src/memory/sqlite.py:get_sqlite_saver`）；它保存完整消息、图状态和工单审批中断。`_handle_input` 先检查同一内部 `thread_id` 的待恢复中断：有中断则使用 `Command(resume=...)`，否则提交本轮 `HumanMessage`。`/history` 从 Checkpoint 读取消息。

Streamlit 保存公开 `thread_id` 与 `AgentClient`；客户端生成 `X-Session-Token`。服务端 `src/service/access.py:checkpoint_thread` 将会话身份、Agent ID 和公开 thread ID 组合为内部 key，并覆盖客户端提供的 `user_id`。仅知道公开 thread ID 不足以读取他人的会话。这个令牌隔离不是正式账号登录；客户端令牌丢失后，旧公开 thread ID 未必可恢复。

## 分层 Memory 与业务事实

| 层 | 实现 | 用途和边界 |
| --- | --- | --- |
| 短期/工作记忆 | `src/memory/layers.py`，Redis | 带 TTL 的会话摘要、当前订单标识、已验证客户和任务状态摘要；不替换 Checkpoint |
| 情景记忆 | `src/memory/episodic.py`，BGE + 独立 Chroma Collection | 已完成售后事件的向量化、按已验证 `customer_id` 过滤的跨会话 Top-K 检索 |
| 用户画像/备注 | `src/memory/layers.py`，SQLite `customer_profiles` / `customer_memories` | 结构化沟通渠道偏好和简短售后类别备注；支持读取、增改、去重和删除 |
| 模型输入视图 | `src/memory/context_manager.py`、`context_compaction_candidate.py` | 按任务相关性、近因性及分项 Token 预算组装；可选摘要替代旧历史，不改 Checkpoint |

服务端在请求开始读取 Redis；新会话只有通过订单号与手机号后四位的业务库校验取得 `customer_id`，才读取该客户 SQLite/Chroma 长期信息。信息经 `RunnableConfig.metadata` 进入 `assemble_model_context`，在模型调用前选择历史、记忆和当前工具/RAG 证据。当前请求、审批和当前轮工具调用配对优先保留；历史订单状态仅作线索，实时订单事实须重查业务库。请求稳定完成后才写入安全的摘要/事件/明确偏好，不把待审批结果记成已完成。

正常运行默认启用 Redis 与情景记忆，启动会预热 BGE 并检查 Chroma；`CONTEXT_COMPACTION_ENABLED` 默认仍为 `false`。压缩器以 Redis 原子游标防重复；候选组装器验证游标、预算和最近两轮，失败回退动态裁剪。摘要覆盖的旧消息只从**模型视图**移除，Checkpoint 仍完整保存。默认 Store `src/memory/sqlite.py:get_sqlite_store` 是进程内 `InMemoryStore`，与上述持久化层和业务订单 SQLite/MySQL 均不同。配置、故障处理、评测边界见[分层 Memory 架构](layered-memory.md)和[42 题离线报告](../evaluation/memory-evaluation.md)。
