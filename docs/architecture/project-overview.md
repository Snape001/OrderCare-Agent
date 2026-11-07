# OrderCare-Agent 项目总览

## 定位与技术栈

电商客服演示系统：政策问答、订单/物流查询、退款资格判断、确认后创建工单。入口是 Streamlit + FastAPI；Agent 使用 LangChain `create_agent` / LangGraph，真实模型可选 Ollama、Qwen、DeepSeek 或通用 LLM Provider；调用失败明确报错，不自动降级。结构化 Router 按意图分流，复杂请求才进入顺序 Planner；四个业务工具经本地 STDIO MCP 调用。政策检索使用 BGE 中文 Embedding、Chroma 和词法召回。业务库本地默认 SQLite，Docker Compose 可切 MySQL；会话 Checkpoint 默认独立的 SQLite。正常运行自动启用的分层 Memory 使用 Redis、独立 Chroma Collection 和 SQLite 用户画像；配置在 `src/core/settings.py` 与环境变量中。

## 目录地图

| 目录 | 职责与主要文件 |
|---|---|
| `src/streamlit_app.py`, `src/client/client.py` | 聊天 UI、HTTP/SSE 客户端、等待计时与前端展示过滤 |
| `src/service/` | FastAPI 路由、请求身份与会话隔离、SSE、公共展示过滤 |
| `src/agents/` | Agent 注册/懒加载；真实客服 `customer_support_agent.py`；其余演示 Agent |
| `src/customer_support/` | 政策解析、RAG、业务工具、SQLite/MySQL/Olist 数据访问和确认判定 |
| `src/memory/` | Checkpoint/Store 适配；Redis 会话/工作记忆、SQLite 画像、Chroma 情景记忆、Context Manager 和可选压缩 |
| `src/core/`, `src/schema/` | 模型工厂、设置、请求/响应模型及纯文本展示过滤 |
| `data/policies/`, `data/evaluation/` | 政策源文件、评测集与必要报告；本地 Chroma/模型/数据库为运行产物 |
| `scripts/`, `tests/` | 启动、导入、验证、离线评测及 pytest 回归 |
| `docker/`, `compose.yaml` | 服务镜像与 MySQL、Redis、迁移、API、Streamlit 编排 |
| `docs/learning/` | 已有问题与实习开发记录，保留历史结论 |

## 层间关系

`Streamlit → AgentClient → FastAPI 身份与 Memory 读取 → LangGraph Router/Planner → Context Manager → 模型/本地 MCP 工具循环 → 任务完成后的 Memory 写入`。FastAPI 负责绑定 Checkpoint、会话隔离和 SSE；业务工具负责实时订单校验与工单幂等。跨会话记忆只有经业务订单身份校验后才按 `customer_id` 查询。`src/agents/agents.py` 还注册了通用聊天、研究、MCP 等演示 Agent；它们不等同于默认客服业务流程。

## 当前边界

- 真实客服的图由 `create_agent` 生成，内部工具循环不是项目手写的显式 `StateGraph` 边。
- 当前 Ollama 客服 SSE 在图完成后只发布最终安全答复或人工确认提示，故 UI 等待期间可能没有 token；`src/streamlit_app.py` 显示计时。
- `CustomerSupportAgent.load()` 支持 `deepseek` 和 `llm`，复用通用模型工厂；所选模型必须支持工具调用，客服入口拒绝 fake。
- 本地 SQLite Checkpoint 持久化会话消息与中断；框架默认 Store 仍是进程内 `InMemoryStore`。正常客服运行要求 Redis 并默认启用 Chroma 情景记忆；只有摘要替代历史的 `CONTEXT_COMPACTION_ENABLED` 默认关闭。
- Router/Planner 只实现有限顺序和退款资格条件分支；不能据此声称通用任务规划。情景记忆 42 题是作者标注的合成离线评测，真实 Agent 端到端任务完成率仍未测。
- 服务端和 STDIO MCP 子进程各有 Python 进程；BGE 在单进程复用，但没有跨进程共享模型实例。

## 建议阅读路线

先看 [执行链](agent-execution-flow.md)，再看 [状态](state-and-memory.md)、[分层 Memory](layered-memory.md)、[RAG](rag-architecture.md) 和 [模块索引](module-reference.md)。开发中遇到的问题与证据见 [工程难点记录](../learning/engineering-challenges.md)。
