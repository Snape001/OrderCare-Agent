# 关键模块与调用索引

| 阅读顺序 | 文件 | 核心入口与作用 |
|---:|---|---|
| 1 | `src/streamlit_app.py` | `main` 接收输入、维护 UI 会话、调用 `AgentClient.astream`；`draw_messages` 展示结果 |
| 2 | `src/client/client.py` | `AgentClient.astream/ainvoke/get_history` 发送 HTTP、解析 SSE、附带会话令牌 |
| 3 | `src/service/service.py` | `lifespan` 加载图；`stream → message_generator → _handle_input` 是请求主链；`invoke/history` 是非流式和历史入口 |
| 4 | `src/agents/agents.py` | `DEFAULT_AGENT`、`agents` 注册表、`load_agent/get_agent` 懒加载边界 |
| 5 | `src/agents/customer_support_agent.py` | `CustomerSupportAgent.load` 选 Provider；`build_customer_support_graph` 注册工具、中间件、HITL 并构建真实 Agent |
| 6 | `src/agents/customer_support_mock.py` | `CustomerSupportState`、`customer_support_node` 与单节点规则图；看 `pending_query/pending_ticket` |
| 7 | `src/customer_support/tools.py` | 四个 `@tool` 的 schema 和对业务函数的委托；工单调用前再校验身份 |
| 8 | `src/customer_support/store.py` | SQLite 演示业务库、订单/退款/工单逻辑与 MySQL/Olist 分派；MySQL 细节见 `mysql_store.py` |
| 9 | `src/customer_support/policy.py`、`src/customer_support/rag.py` | 政策读取、切片、BGE、Chroma、词法/向量融合与拒答 |
| 10 | `src/memory/__init__.py`、`src/memory/sqlite.py` | Checkpoint/Store 选择与默认 SQLite saver；会话隔离补看 `src/service/access.py` |

按这个顺序先追“请求从哪里进入、哪里恢复 State、哪里选工具”，再读 RAG 和数据库实现。`src/core/settings.py`、`src/core/llm.py` 分别是配置和通用模型工厂；真实客服的 Ollama/Qwen 构造当前在 `customer_support_agent.py`，不要只看通用工厂。`src/service/presentation.py` 和 `src/schema/presentation.py` 决定 Ollama 客服的对外可见内容。

## Evaluation 与 Deployment

| 用途 | 入口与证据 |
|---|---|
| 自动化回归 | `tests/`；`scripts/run_tests.ps1` / `scripts/run_tests.cmd`；Docker 用例需 `--run-docker` 与容器环境 |
| 规则/业务离线评测 | `scripts/evaluate_agent.py`，输入 `data/evaluation/agent_routing_cases.json`，输出 `agent_report.json` |
| RAG 评测 | `scripts/evaluate_rag.py`，对三种检索方法计算 Hit/MRR/拒答/延迟，输出 `rag_report.json` |
| 真实 Ollama 工具验证 | `scripts/verify_ollama_agent.py`，需本机模型；与常规 pytest 分开 |
| 本地启动 | `scripts/setup_demo.*`、`scripts/start_demo.*`，配置示例 `.env.example`、`.env.mock.example`、`.env.ollama.example`、`.env.qwen.example` |
| Docker | `compose.yaml`、`docker/Dockerfile.*`、`scripts/migrate_sqlite_to_mysql.py`：MySQL → 一次性导入 → FastAPI/Streamlit/只读浏览器 |

## 清理审计结论

`.tmp/` 含工具日志、锁及来源未明的缓存；`reports/` 是本地验证产物；`.ruff_cache/`、SQLite `*.db-wal`/`*.db-shm` 是运行缓存。它们已通过 `.gitignore` 防止误提交。唯一确认可移除的是 `.tmp/` 中零字节且无仓库引用的 `uv-4d7e800bdd650bc9.lock`；其他文件因可能承载用户数据或调试证据保留。

`docs/VertexAI.md`、`docs/RAG_Assistant.md`、`scripts/create_chroma_db.py` 属于通用演示 Agent 文档/脚本，虽非默认客服主链，但存在代码或文档引用；`media/` 图像及 `src/run_agent.py` 等演示入口也保留。当前没有足够证据把它们判为死代码。旧文档中的外部项目链接与默认客服定位不完全一致，可日后单独校订，不作为本次删除依据。
