# Memory 系统功能审计与离线评测（2026-11-07）

## 审计结论与调用链

| 能力 | 实际实现与边界 |
| --- | --- |
| 短期与工作记忆 | `LayeredMemory` 按会话身份和 thread 哈希 Redis 键，保存当前订单标识、已验证 customer_id、任务进度和短摘要；`MEMORY_TTL_SECONDS` 控制 TTL。LangGraph Checkpoint 仍持有完整消息和审批中断，Redis 不代替它。 |
| 长期情景记忆 | `completed_episode` 只从已完成任务 trace 提取事件类别、已执行动作及安全商品名；复用 RAG 单例的 BGE Embedding，在独立 Chroma Collection 写入。新会话完成业务订单身份校验后按 customer_id 过滤检索，综合余弦相似度与时间近因性。 |
| 用户画像 | 新增独立 SQLite `customer_profiles`，保存 `text` / `phone` 沟通渠道枚举及更新时间；支持增改、幂等去重、查询和删除。只在验证身份、请求完成且用户明确表达长期偏好时自动更新。旧 `customer_memories` 仍存售后备注；结构化画像覆盖冲突的旧自由文本偏好。 |
| 上下文与预算 | 服务读取 Redis → 新会话检索 Chroma → 读取 SQLite 备注及画像 → 通过请求 metadata 送入 `assemble_model_context`。`ContextManager` 选择工作状态、相关记忆、最近 Checkpoint 消息和工具/RAG 证据，按独立预算组装模型视图。中文相关性过滤改用重叠双字词，避免词边界漏掉“台灯工单”。 |
| 自动压缩 | `AutomaticCompactor` 用 Redis 原子游标保存结构化历史摘要；`CONTEXT_COMPACTION_ENABLED=true` 时，候选组装器用摘要替代游标覆盖的旧消息，保留最近两轮及工具调用对。游标不符、摘要预算不足或近期消息无法保留时回退。Checkpoint 原始消息不变；默认开关为 `false`。 |

业务订单状态始终以订单工具与数据库为准。跨会话读取须先通过订单号及手机号后四位的现有业务校验；只有已验证 `customer_id` 可用于 SQLite/Chroma 客户过滤。手机号、支付信息、API Key 与原始 CoT 不写入情景摘要或结构化画像。该业务校验并不等价于正式账号认证。

## 数据与实验口径

- [固定数据集](../../data/evaluation/memory/dataset-v1.json)：42 条中文合成情景、16 条手工设计的售后事件，覆盖历史检索、跨会话、相似事件、画像及冲突更新、近期排序、同会话工作状态、长上下文、故障与隔离。Ground Truth 是作者依据合成事件**手工标注，未经独立人工复核**，没有真实客户数据。
- A：不读取 Memory，只保留当前请求与同一生产 System Prompt。B：真实 `BAAI/bge-small-zh-v1.5`（FastEmbed，512 维）+ 隔离 Chroma Collection + SQLite 画像 + Context Manager；两条长对话复用既有摘要替代实验，强制触发压缩以观察候选策略。A 按实验定义不使用 Checkpoint 历史，因此不代表现有线上 Agent 的无 Memory 运行效果。
- 固定 Top-K=4、相似度阈值 0.55、近因性权重 0.15、`as_of=2026-11-07T00:00:00+00:00`。真实 BGE 在本地缓存加载；**没有真实 DeepSeek API 调用**。Redis 路径用隔离的进程内适配器执行真实 `LayeredMemory` 读写及 TTL 参数；这不是 Redis 性能测试，已有真实 Redis 专项集成测试另行通过环境变量触发。
- [逐题最终结果](../../data/evaluation/memory/results-v1/results.json)保存查询、Ground Truth、排名、相似度、来源会话、实际注入、画像、Token、故障与恢复。保留[中文事件标签优化前](../../data/evaluation/memory/results-v1/before-event-labels.json)和[上下文词组修复前](../../data/evaluation/memory/results-v1/before-context-gate.json)的完整原始结果。三个结果都使用同一数据集和 BGE；不改标签。

运行命令：

```powershell
$env:PYTHONPATH='src'
uv run python scripts/evaluate_memory.py
```

## 指标定义及结果

检索指标只在 29 条有相关事件且未注入故障的题上计算。Recall@4 是 Top-4 中相关事件数除以标注相关事件数；Precision@4 分母固定为 4；MRR 是首个相关事件的倒数排名。跨会话 Recall 在 4 条该类正例上计算。注入 Recall 检查相关事件**真正出现在模型视图**。画像准确率在 6 条含画像标签的正常题上计算。隔离率在 4 条隔离/未验证题上检查是否泄露被禁止事件。事实保留率在 2 条同会话工作状态和 2 条旧长对话共 12 个严格字面事实上计算；它是上下文包含率，不是回答正确率。

| 指标 | A 当前请求 | B 完整 Memory + 离线压缩候选 |
| --- | ---: | ---: |
| Memory Recall@4 | 0 | **1.0000** |
| Memory Precision@4 | 0 | **0.2759** |
| MRR | 0 | **0.9138** |
| Cross-session Recall | 0 | **1.0000** |
| 相关事件实际注入率 | 0 | **1.0000** |
| Profile Accuracy | 0 | **1.0000** |
| Fact Retention（严格字面，12 项） | 0 | **1.0000** |
| User Isolation | 1.0000（未检索，平凡成立） | **1.0000** |
| 两条近期排序题的顺序正确率 | 0 | **1.0000** |
| Task Completion Rate | **未评估** | **未评估** |

两条**强制触发**的旧长对话中，完整原始上下文为 1038 估算 Token，摘要替代后为 703，减少 **32.27%**。它相对“只保留当前请求”的 A 会增加上下文；不能把该节省率理解为相对 A 的节省，也不能外推到默认 4096 Token、80% 触发阈值的生产环境。B 平均单题检索与组装耗时为约 **14.4 ms**，是本机模型热启动后的合成实验值，不含模型冷启动、真实 Redis 网络或 LLM 生成耗时。

## 失败案例与修复

首次完整 B 运行时，英文 `ticket_create` / `create_support_ticket` 摘要使中文“工单”问题难以召回：Recall@4 **0.8276**、MRR **0.6494**、跨会话 Recall **0.75**。改成语义相同的中文事件标签后，在同一 42 题上分别为 **1.0000 / 0.9138 / 1.0000**。`c23` 曾经已召回台灯工单，但原中文词组匹配取不重叠双字，恰好漏掉“台灯”和“工单”，导致未注入；重叠双字修复后，相关事件实际注入率为 1.0000。上述是本数据集上的修复效果，没有独立留出集。

最终仍有 **5/29** 个有答案查询的 Top-1 排错：`r09`、`r15`、`r17`、`r19`、`p27`。例如 `r15` 的“耳机维修，不是退款”把退款事件排在维修前，`r19` 的“吸尘器维修，别找工单”把工单排在维修前。Top-4 均含标注事件，因此 Recall@4 满分掩盖了否定条件和相似事件的排序问题。Precision@4 仅 0.2759，也说明结果中有较多同客户但与本题无关的事件。未为这组开发样本继续调阈值或权重。

`f37`、`f38` 故意注入 Chroma / Redis 故障，均明确报错并在恢复后可重新读取；这两题**不计入检索质量分母**。真实 Redis 不可用时的网络恢复、真实 BGE 的更大规模记忆库、真实长任务及并发性能尚未通过本实验验证。尤其没有真实模型端到端任务执行，**Task Completion Rate 保持 null**，不得把事实保留率写作任务完成率。

此前已批准并保存的[DeepSeek 六次调用与人工复核](../../data/evaluation/context-compaction-v2/human-review.json)对这两组旧合成长对话给出 **2/2 续接回答保持任务顺序**；那是摘要质量实验，不是本次 A/B 的端到端 Agent 任务完成率。本轮复用其对话和离线摘要评测，没有重复调用付费 API。DeepSeek 官方当前[模型与价格说明](https://api-docs.deepseek.com/quick_start/pricing/)可用于以后单独预算真实执行实验；本轮 API 消耗为零。

## 结论与简历口径

三层 Memory 的存储、身份隔离、读写、Context Manager 注入和可选压缩均有实际代码与专项测试支撑，形成了**功能调用闭环**。可准确描述为“实现 Redis 工作记忆、Chroma+BGE 情景检索、SQLite 结构化画像与可选上下文压缩，并在 42 条合成题上完成真实 BGE 离线评测”。不能声称线上默认启用压缩或情景记忆、真实客户数据准确率、完整 Agent 任务完成率、普遍 Token 节省或真实 Redis/DeepSeek 的本轮性能结果。下一步应独立人工复核数据集，并用真实长会话和显式授权的模型调用验证任务完成率及否定查询排序。

工程验证：全量 pytest **366 passed、5 skipped**；`ruff check .`、`mypy src scripts/evaluate_memory.py`（81 个文件）与 `git diff --check` 通过。5 个跳过项包含需要单独 Redis 测试服务的集成场景；本机没有 Docker 命令。本轮原有工作区的其他未提交更改保留，未修改 Router、Planner、MCP 或政策 RAG 检索算法。
