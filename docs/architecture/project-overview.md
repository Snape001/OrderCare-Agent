# OrderCare-Agent 项目总览

## 定位与技术栈

电商客服演示系统：政策问答、订单/物流查询、退款资格判断、确认后创建工单。入口是 Streamlit + FastAPI；Agent 使用 LangChain `create_agent` / LangGraph，真实模型可选 Ollama `qwen3:4b` 或阿里云百炼 Qwen，离线模式用确定性 Mock 图。政策检索使用 BGE 中文 Embedding、Chroma 和本地词法召回。业务库本地默认 SQLite，Docker Compose 可切 MySQL；会话 Checkpoint 默认独立的 SQLite。配置在 `src/core/settings.py` 和环境变量中。

## 目录地图

| 目录 | 职责与主要文件 |
|---|---|
| `src/streamlit_app.py`, `src/client/client.py` | 聊天 UI、HTTP/SSE 客户端、等待计时与前端展示过滤 |
| `src/service/` | FastAPI 路由、请求身份与会话隔离、SSE、公共展示过滤 |
| `src/agents/` | Agent 注册/懒加载；真实客服 `customer_support_agent.py`；离线图 `customer_support_mock.py`；其余演示 Agent |
| `src/customer_support/` | 政策解析、RAG、业务工具、SQLite/MySQL/Olist 数据访问和确认判定 |
| `src/memory/` | Checkpoint 和 Store 的 SQLite/Postgres/Mongo 适配 |
| `src/core/`, `src/schema/` | 模型工厂、设置、请求/响应模型及纯文本展示过滤 |
| `data/policies/`, `data/evaluation/` | 政策源文件、评测集与必要报告；本地 Chroma/模型/数据库为运行产物 |
| `scripts/`, `tests/` | 启动、导入、验证、离线评测及 pytest 回归 |
| `docker/`, `compose.yaml` | 服务镜像与 MySQL、迁移、API、Streamlit 编排 |
| `docs/learning/` | 已有问题与实习开发记录，保留历史结论 |

## 层间关系

`Streamlit → AgentClient → FastAPI → Agent 注册表 → LangGraph 图 → Tools → RAG/业务库`。FastAPI 负责绑定 Checkpoint、鉴权和 SSE，业务工具负责实际数据校验。`src/agents/agents.py` 还注册了通用聊天、研究、MCP 等演示 Agent；它们不等同于默认客服业务流程。

## 当前边界

- 真实客服的图由 `create_agent` 生成，内部工具循环不是项目手写的显式 `StateGraph` 边；Mock 图则只有 `customer_support` 节点到 `END`。
- 当前 Ollama 客服 SSE 在图完成后只发布最终安全答复或人工确认提示，故 UI 等待期间可能没有 token；`src/streamlit_app.py` 显示计时。
- `src/core/llm.py` 有通用 DeepSeek 模型工厂分支，但 `CustomerSupportAgent.load()` 当前只选择 Mock/Qwen/Ollama；不能把 DeepSeek 客服说成已接入。
- 本地 SQLite Checkpoint 持久化会话消息，但默认长期 Store 是进程内 `InMemoryStore`；没有 Redis、Planner 或跨任务订单槽位管理。

## 建议阅读路线

先看 [执行链](agent-execution-flow.md)，再看 [状态](state-and-memory.md)、[RAG](rag-architecture.md) 和 [模块索引](module-reference.md)。
