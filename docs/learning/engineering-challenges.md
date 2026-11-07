# OrderCare-Agent 工程难点与解决记录

本文补充当前架构的 Memory、RAG、MCP 与 Agent 工程问题。早期按时间记录的案例保留在[开发日志](agent-development-journal.md)；这里的结论只使用仓库代码、测试或已保存实验，不把离线样本结果写成线上 SLA。当前功能入口见[项目总览](../architecture/project-overview.md)和[模块索引](../architecture/module-reference.md)。

## 1. Checkpoint 有历史消息，却不等于可用的业务记忆

- **卡点**：多轮任务要记住当前订单与待办，跨会话还要找回该客户的售后事件；把全部旧消息塞给模型会增加 Token，且旧订单状态可能过时。
- **定位**：LangGraph SQLite Checkpoint 负责消息和审批恢复，默认 Store 是进程内 `InMemoryStore`。它不提供按客户语义检索或结构化沟通偏好；订单真实状态保存在业务库。见[`state-and-memory.md`](../architecture/state-and-memory.md)及[`service.py`](../../src/service/service.py)。
- **解决**：`src/memory/layers.py` 用带 TTL、按会话身份哈希的 Redis 键存短期和工作状态；SQLite `customer_profiles` 存结构化渠道偏好；`episodic.py` 在独立 Chroma Collection 用 BGE 存已完成事件。新会话先用订单号及手机号后四位查业务库，取得已验证 `customer_id` 才查询长期记忆。Context Manager 按相关性、近因性和预算注入；实时订单状态仍由工具重查。本阶段初次评测时 `EPISODIC_MEMORY_ENABLED` 默认关闭，后来正常运行集成改为默认启用；业务校验不能等同正式账户认证。
- **验证与边界**：[42 题 Memory 离线报告](../evaluation/memory-evaluation.md)使用真实 BGE、作者标注合成事件，Recall@4 1.0000、MRR 0.9138、跨会话 Recall 1.0000；但 Precision@4 仅 0.2759，5/29 个有答案问题 Top-1 排错。没有真实 DeepSeek 端到端任务完成率；当前默认启用是运行配置，不代表已测得真实用户效果。

## 2. 检索命中与模型真正收到记忆是两道关

- **卡点**：Memory 评测中的 `c23` 已召回“台灯工单”事件，却没有进入模型上下文。
- **根因**：原中文词组过滤使用不重叠双字切分，查询与记忆中的关键短语错位；向量检索命中并不代表 Context Manager 的注入门槛通过。
- **解决**：`src/memory/context_manager.py` 的中文相关性过滤改用重叠双字词；评测同时记录检索排名和实际注入，而非只看 Recall@K。
- **验证与边界**：同一 42 题、同一 BGE 数据集保留了[修复前逐题结果](../../data/evaluation/memory/results-v1/before-context-gate.json)与[最终结果](../../data/evaluation/memory/results-v1/results.json)，相关事件实际注入率在最终结果为 1.0000。数据未独立人工复核，也没有新增留出集。

## 3. 中英文事件表达不一致导致语义召回下降

- **卡点**：中文“工单”“维修”问题检索英文 `ticket_create`、`create_support_ticket` 事件时，相关售后记录排名或召回不稳定。
- **解决**：`src/memory/episodic.py:completed_episode` 用中文业务标签摘要已完成任务，保留事件类型元数据、来源会话与客户过滤；只从已完成 trace 提取，不凭模型自由文本宣称工单已完成。
- **验证与边界**：同一 42 题真实 BGE 离线评测，改前 Recall@4 0.8276、MRR 0.6494、跨会话 Recall 0.75；改后分别为 1.0000、0.9138、1.0000。原始结果保存在[`before-event-labels.json`](../../data/evaluation/memory/results-v1/before-event-labels.json)。这是本合成开发集上的修复，不能外推到真实业务语料。

## 4. 摘要已生成并持久化，却未节省模型上下文

- **卡点**：早期压力实验中，DeepSeek 摘要存进 Redis，但两份均超过 Memory 注入预算，**0/2 实际进入模型视图**；另一个摘录摘要被附加在旧历史后，合计 Token 反而高于只动态裁剪。
- **根因**：摘要存储成功与 Context Manager 选入是不同阶段；原逻辑未从模型视图排除摘要游标覆盖的旧消息。Redis 摘要字段 8/8 保留，模型可见仅 6/8，不能混算。
- **解决**：`src/memory/compaction.py` 用位置与指纹游标、Redis 原子比较写入做增量摘要；`context_compaction_candidate.py` 验证游标和消息组边界，让预算内摘要替代旧消息、保留最近两个用户轮次和工具调用对。无效游标、超预算或近期消息不完整时回退原动态裁剪。只改模型输入视图，不覆盖 Checkpoint；`CONTEXT_COMPACTION_ENABLED` 默认关闭。
- **验证与边界**：[第四阶段压力报告](../evaluation/context-compaction-phase4.md)说明动态裁剪从 1038 到 618 估算 Token，原附加摘要方案到 998；[替代候选报告](../evaluation/context-compaction-replacement.md)在两份 DeepSeek 摘要上将注入从 0/2 改为 2/2，但候选合计 876 Token，仍比只裁剪多 258。后续[42 题报告](../evaluation/memory-evaluation.md)中的两条强制压缩旧长对话为 1038→703（相对完整历史减 32.27%），不是相对只裁剪的节省，也不是默认生产预算下的收益。

## 5. 并发压缩、旧游标与敏感信息

- **卡点**：并发请求可能重复压缩同段历史；两个相同 AI 文本会让纯内容游标错指后一个位置；真实 Redis Lua `cjson` 把空数组读回为对象。自由文本中的付款方式也可能漏过局部脱敏。
- **解决**：压缩游标绑定消息位置和指纹；Redis Lua CAS 只允许预期旧游标写入；旧格式游标保守取最早匹配。读取时只对摘要的空对象恢复数组；含支付方式/账户信息的整条消息跳过压缩。日志只记 Token 与回退原因，不记原始 CoT。
- **验证与边界**：[真实环境集成报告](../evaluation/context-compaction-phase4.md)使用独立 Memurai Redis 兼容服务验证 AOF 重启、TTL、6 次并发仅 1 次写入、重复保护、会话隔离及异常恢复，3 个专项测试通过。该环境不是官方 Linux Redis 容器；默认 pytest 未配置独立 URL 时跳过专项网络测试。

## 6. RAG 召回同主题政策，却缺少回答必需条件

- **卡点**：`rag-003` 只召回退货同主题内容，缺少“物流拦截失败后签收再按退货处理”；`rag-015` 已有“24 小时内联系承运商”，生成回答却把它说成“24 小时内核查完成”。前者是 Retrieval Miss，后者是生成误读，不能统一归咎于排序。
- **解决**：评测拆开 Recall/MRR/nDCG、独立证据充分性、生成正确性、引用支持与拒答；逐题存上下文、原回答和 Judge 原文，Judge 无法可靠判断时记 `null`。结构化证据块与逐事实引用只做候选实验；没有证据支持 Chunk 合并或全局上线重写。
- **验证与边界**：[证据充分性诊断](../evaluation/evidence-sufficiency-analysis.md)的 40 题独立审计中 23 题充分、13 题不足、4 题未知；10 题属于知识库无答案。Judge 已有漏判反例，其 1.0 正确率等值不能当真实准确率。[90 题第二轮结果](../../data/evaluation/rag/three-way-comparison-v2/metrics.md)显示 Hybrid 全集 Recall@2 为 0.7534、Direct 为 0.7192；Rewrite + Hybrid 留出集 Recall@2 与 Hybrid 同为 0.7963，未证明额外改写有收益。

## 7. 冻结 RAG Ground Truth 与现行政策文件 Hash 不同

- **卡点**：旧评测的 24 个 SHA256 失败看似政策库损坏。
- **根因**：40 题数据集绑定冻结政策 SHA；现行政策首页标题更改后文件 Hash 变化，旧测试却拿现行文件去校验冻结标签，二级政策内容未变。
- **解决**：旧评测测试显式使用已保存的冻结政策快照并核对原 SHA，同时保留原章节来源检查；没有修改政策正文、旧 Ground Truth 或关闭 SHA 校验。
- **验证**：[第四阶段报告](../evaluation/context-compaction-phase4.md#旧-rag-sha256-测试基线)记录旧 RAG 专项 48 通过。这是测试 Fixture 版本选择问题；新政策知识库仍按其自身版本评测。

## 8. 模型提出工具调用不等于安全完成业务动作

- **卡点**：多意图规划可能自行增加敏感工单动作；Agent 文字说“已创建”也不能证明工具执行。工单写操作需要用户确认，而模型的 `tool_calls` 不是授权。
- **解决**：`src/customer_support/routing.py:validate_plan` 限制 Planner 只规划 Router 和用户原文允许的动作，并校验依赖、条件及缺参；`src/agents/customer_support_agent.py` 每步只开放必要工具。MCP Client/Server 复用四个现有业务工具，工单在 LangGraph HITL 中断后才执行，STDIO Server 还验证内部签名；业务层保留身份校验与幂等键。MCP 错误明确上抛，日志走 stderr，避免污染 STDIO 协议。
- **验证与边界**：[Router / Planner 说明](../architecture/router-planner.md)、[MCP 说明](../mcp-business-tools.md)与相应 `tests/customer_support/` 回归覆盖计划校验、工具调用和审批恢复。现存 Router 文档明确没有可靠的真实 DeepSeek 准确率基准，不应声称意图 F1 或任务完成率。

## 9. LangGraph 事件与 SSE 不是“最后一个消息就是结果”

- **卡点**：早期真实 HTTP 接入曾在模型和工具已成功后仍返回 500；工单审批提示也曾被普通回复覆盖。
- **根因与解决**：LangGraph 事件含 `updates`、`values`、`messages` 与 `__interrupt__`，不能只取最后一项并假定为最终 State。服务端优先识别审批中断，再读取有效最终值；前端过滤内部工具/思考内容，等待首个可见输出时保留计时与取消处理。
- **验证与边界**：原始现象、修复及 HTTP 回归记录见[Bug 002](bug-002-qwen-agent-event-handling.md)；该历史案例不代表所有 Provider 的 SSE 都逐 Token 流式输出，当前 Ollama 客服路径可能只发最终可见消息。

## 当前仍需验证

- Memory 的 42 题是作者标注的合成数据，缺独立人工复核、真实长对话和端到端 Agent 任务完成率；情景记忆 Top-1 否定条件排序及 Precision@4 仍弱。
- 压缩在默认 4096 Token、80% 阈值的真实长会话中是否降低 Token、维持审批与任务连续性，尚无充分 A/B 证据，因此 Feature Flag 默认关闭。
- Router/Planner 的真实模型准确率、跨 Provider 工具调用稳定性，以及多实例部署下本地 Checkpoint/Redis/Chroma 的一致性，不能从当前离线测试推断。
