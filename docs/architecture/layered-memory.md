# 分层 Memory（最小实现）

相关故障、修复依据和评测局限集中记录在[工程难点与解决记录](../learning/engineering-challenges.md)；逐题结果见[Memory 离线评测](../evaluation/memory-evaluation.md)。

正常运行默认启用三层 Memory（`MEMORY_ENABLED=true`、`EPISODIC_MEMORY_ENABLED=true`）；本地 `REDIS_URL` 默认 `redis://127.0.0.1:6379/0`，启动时必须可用。服务创建独立 SQLite 长期记忆表、初始化独立 Chroma Collection 并预热 BGE，失败即阻止启动。Docker Compose 使用 `redis://redis:6379/0`、Redis AOF 命名卷、持久化 Chroma 与 SQLite 卷。`MEMORY_TTL_SECONDS` 默认 86400 秒，`MEMORY_SQLITE_PATH` 默认 `data/customer_memories.db`，容器中位于持久化 `/app/runtime/`。显式设 `MEMORY_ENABLED=false` 才关闭三层记忆；摘要替代旧历史的开关仍默认关闭。

| 层 | 存储 | 内容与边界 |
| --- | --- | --- |
| 会话短期 | Redis | 按服务端会话身份与 thread ID 哈希成键，保存精简意图/商品摘要，有 TTL |
| 工作记忆 | Redis + LangGraph State | Redis 保存当前已验证订单、意图和任务状态摘要；完整 route/plan/messages 仍由 State 与 Checkpoint 管理 |
| 客户长期 | SQLite `customer_memories` 与 `customer_profiles` | 前者保存短的售后类别备注；后者按已验证 customer_id 保存结构化沟通渠道偏好，均支持读取、更新、去重和删除 |
| 中断恢复 | 原 LangGraph SQLite Checkpoint | 工单审批与完整消息状态继续由现有 Checkpoint 管理 |

只有请求同时带订单号和手机号后四位、且现有订单查询通过业务库校验，才绑定真实 `customer_id`。后四位仅用于当次查询，不写入 Memory。新会话完成身份验证后，按查询词相关性和更新时间选最多四条长期记忆，截断到 500 字符后注入模型上下文。若同一 thread 的 Checkpoint 已有消息，不重复注入；Checkpoint 中断恢复直接使用原有 `Command(resume=...)`。

`LayeredMemory.put/delete/select` 提供长期备注的增改、删除与读取；相同内容按 `(customer_id, kind, value)` 去重。该表自动写入仅记录意图类别及安全的商品名称；沟通偏好使用下述结构化画像表。Redis 故障会抛出异常，服务启动时校验连接，不会把审批状态转移到 Redis。

结构化画像由独立 `customer_profiles(customer_id, communication_channel, updated_at)` 表保存，只接受 `text` / `phone` 枚举。服务仅在业务身份已验证、请求完成且用户明确说出“以后/今后/下次/长期”的沟通方式时作确定性更新；不保存原话或电话号码。`LayeredMemory.upsert_profile/get_profile/delete_profile/profile_note` 提供画像 CRUD。读取时结构化画像覆盖旧版自由文本偏好备注，避免新旧偏好同时注入。复杂或含否定的表述保守跳过，需要用户再次明确选择。

当前身份解析识别明确写出的 `ORD` / `OL` 加数字的订单号及“手机号后四位”等格式；其他表述仍由 Agent 正常处理，但本轮不会自动绑定长期记忆。此能力不是账户登录，也不应用于跨真实用户的生产身份认证。

## Context Manager 与 Token Budget

服务端在处理请求时按会话凭证读取 Redis 工作状态和摘要，在新会话且验证订单身份后检索 Chroma 情景记忆，并从 SQLite 读取该客户的历史备注与结构化画像。数据通过本次 LangGraph `RunnableConfig.metadata` 传递给模型调用；`ContextManager` 在 `wrap_model_call` 中合并生产 System Prompt、任务状态、相关记忆、Checkpoint 最近对话，以及本轮 RAG/业务工具结果。只覆盖送往模型的消息列表，Checkpoint 内的完整消息、Router/Planner State 和审批中断均不裁剪。

默认预算为总计 4096 Token：系统规则 1024、最近对话 1200、记忆 640、RAG 证据 768、业务工具结果 720。可分别用 `CONTEXT_*_BUDGET` 环境变量调整。先尝试模型提供的消息 Token 计数；若模型未实现或缺少 tokenizer，则按字符数乘 1.25 加消息开销保守估算。日志只记录估算 Token 与各类别占用，不记录消息正文。

组装时永远保留系统规则和当前用户消息；按最近优先选历史对话，长期售后摘要要求与当前问题匹配，偏好与任务状态优先。旧轮次工具结果被淘汰，当前轮次的 Tool Call 与对应 ToolMessage 整组保留，避免不成对或丢失当前业务证据。若系统规则、当前请求或本轮必要工具结果本身超过预算，允许超额并在日志体现；不会截断政策原文或审批工具结果。历史订单状态只作线索，当前事实仍须重新调用业务工具。

专项测试覆盖不同任务组装、长对话裁剪、记忆相关性、工具调用配对、当前请求保留、Redis 故障和会话隔离。完整 pytest 的旧 RAG SHA256 失败见已有评测文档；该完整性校验保持开启。

## Automatic Context Compaction

`assemble_model_context` 在模型调用前计算原始消息和 System Prompt 的 Token 数。达到 `CONTEXT_COMPACTION_THRESHOLD`（默认总预算的 80%）时，`AutomaticCompactor` 只处理最近两条用户消息之前的完整历史。结构化摘要从用户原话和工具 JSON 中摘录目标、约束、偏好、决策、已完成步骤、未解决问题、订单标识及政策来源；不会读取 AI 中间思考文本，也不会修改 Checkpoint 或截断本轮工具调用。

摘要与普通会话快照分别保存在同一会话身份派生的两个 Redis 键中，均有 TTL。压缩键用原子游标比较写入：重复调用不会再次压缩同一段历史，并发写入只有一个成功；失败时保留原摘要并明确报错。后续轮次将新历史与已保存的结构化摘要增量合并。敏感数字和凭据先脱敏；超过摘要预算或用户原话过长时跳过该段压缩，避免存入不完整事实。Context Manager 将压缩摘要作为历史线索注入，动态订单状态仍需业务工具重新核验。

Token 预算由 `CONTEXT_TOKEN_BUDGET`、`CONTEXT_MEMORY_BUDGET` 和 `CONTEXT_COMPACTION_SUMMARY_BUDGET` 等环境变量控制。此阶段采用可审计的离线摘录规则；复杂语义归纳和真实模型调用尚未启用。Token 节省率和关键字段保留率仅在[合成离线报告](../../data/evaluation/context-compaction-v1/results.json)所列样本上成立，不代表真实客服对话准确率。

第四阶段[真实环境集成报告](../evaluation/context-compaction-phase4.md)验证了独立 Redis 兼容服务的原子游标、并发、重启和异常恢复，并区分 Context Manager 裁剪与 Compaction 的实际收益。在强制触发压缩的固定短对话压力预算下，一组摘录摘要因 Memory 预算不足被上下文组装器跳过，另一组进入模型视图但增加了 Token；模型实际可见事实保留率为 6/8。生产默认预算下这些短对话不会触发压缩。当前不应将压缩字段的存储保留率当作模型可用信息保留率，也不应把动态裁剪节省的 Token 算成 Compaction 收益。

[摘要替代旧历史的离线候选实验](../evaluation/context-compaction-replacement.md)新增独立组装器，使用已保存的压缩游标确定旧消息前缀，并在模型视图中以独立预算的摘要替代该前缀。现在可设置 `CONTEXT_COMPACTION_ENABLED=true` 使 `assemble_model_context` 使用该候选；默认仍为 `false`，保留原有动态裁剪。候选保留最近 2 个用户轮次和完整工具调用对；摘要超预算、游标错误或最近轮次不能完整保留时回退到原有 Context Manager。可用 `CONTEXT_HISTORY_SUMMARY_BUDGET`、`CONTEXT_LONG_TERM_BUDGET`、`CONTEXT_RECENT_TURNS` 调整预算及保留轮次。日志记录压缩前后 Token、是否注入摘要和回退原因，不记录内容。该开关只影响发送到模型的视图，Checkpoint、审批状态及 Redis TTL 均不变。

## 长期情景记忆

设置 `EPISODIC_MEMORY_ENABLED=true` 且配置 `REDIS_URL` 后，服务复用**同一进程**政策 RAG 单例的 BGE Embedding 与 Chroma 持久化目录，在独立的 `customer_support_episodes` Collection 中保存已完成的售后事件。政策 Collection 不变。当前 STDIO MCP Server 是另一进程，其政策检索会各自加载 BGE；本实现没有跨进程共享模型实例。事件只从已完成的任务 trace 中提取业务动作、类别和安全商品名，以中文业务标签保存，不使用模型自由文本、原始 CoT、手机号、支付信息或未经确认的工单结果。元数据含 `memory_id`、`customer_id`、`event_type`、`created_at` 和 `source_session`；模块支持按 ID 更新、去重及删除。

服务在**新会话**通过原有订单号和手机号后四位业务库校验取得 `customer_id` 后，才使用当前问题做 BGE 向量查询，并在 Chroma 端按客户过滤。结果先经过相似度阈值，再按语义相似度与时间近因性排序，最多选 `EPISODIC_TOP_K` 条，交给 Context Manager 的长期记忆预算筛选。可配置 `EPISODIC_SIMILARITY_THRESHOLD`、`EPISODIC_RECENCY_WEIGHT`。无验证身份时不读取跨会话记忆；Chroma 故障明确报错。SQLite 仍负责结构化长期偏好及售后摘要的增改、去重和删除，LangGraph SQLite Checkpoint 继续负责会话中断与恢复。

调用链：业务身份校验 → Redis 会话/工作状态读取 → 已验证客户的 SQLite 画像与 Chroma 情景记忆检索 → Context Manager（可选摘要替代）→ LangGraph Agent → 任务完成且无待审批中断 → Redis、SQLite 与 Chroma 记忆写入。Redis/画像/情景记忆默认启用，`CONTEXT_COMPACTION_ENABLED` 仍默认关闭。`/ready` 检查 Redis 和 Chroma，可用性变化返回 503。当前身份校验是订单持有信息校验，不能替代正式账户认证。

专项单元测试使用隔离 Chroma 与确定性测试 Embedding 验证写入、检索、更新、删除、用户过滤、近因性排序、预算内注入和故障；LangGraph 假模型测试直接检查模型可见消息中的摘要替代、默认路径与回退。另有[42 题真实 BGE 离线评测](../evaluation/memory-evaluation.md)。本轮默认运行接入不增加 DeepSeek 调用；离线检索指标不代表真实模型端到端任务完成率。
