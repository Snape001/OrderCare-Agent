# OrderCare-Agent

电商售后智能客服Agent，基于 LangChain、LangGraph、MCP 与 RAG，覆盖政策咨询、订单查询、退款资格判断及人工确认建单。

> 政策、订单和工单均为演示数据；不执行真实退款，也不提供正式账户认证。

## 功能

- **Agent 编排：** LangGraph 管理工具调用循环、条件任务、Checkpoint 与人工确认恢复。
- **业务工具：** MCP 封装政策检索、订单查询、退款判断和工单创建；工单写入具备确认与幂等保护。
- **政策检索：** 36 篇售后政策，使用 Dense/BM25 混合召回、Query Rewrite 与 BGE 重排，返回证据来源。
- **韧性保护：** 检索与 MCP 调用支持缓存、超时、熔断和明确降级。
- **Memory：** Redis 会话状态、Chroma 情景记忆、SQLite 用户画像；上下文按 Token 预算动态拼接与裁剪。
- **应用：** FastAPI/SSE 服务和 Streamlit 客服工作台。

架构细节见 [Router / Planner](docs/architecture/router-planner.md)、[Memory](docs/architecture/layered-memory.md)、[RAG](docs/architecture/rag-architecture.md) 和 [MCP 工具](docs/mcp-business-tools.md)。

## 快速启动（Windows）

需要 Python 3.12、uv、Ollama 和 Redis。首次运行会下载依赖、Embedding 与本地 reranker 模型（约 1.1 GB）。

```powershell
git clone https://github.com/Snape001/OrderCare-Agent.git
cd OrderCare-Agent
ollama pull qwen3:4b
if (!(Test-Path .env)) { Copy-Item .env.ollama.example .env }
.\scripts\setup_demo.cmd
.\scripts\start_demo.cmd
```

另开终端启动界面：

```powershell
uv run streamlit run src/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

工作台：<http://127.0.0.1:8501> · API 文档：<http://127.0.0.1:8080/docs> · 停止服务：`.\scripts\stop_demo.cmd`

模型 Provider 与环境变量见 [.env.ollama.example](.env.ollama.example) 和 [.env.example](.env.example)。政策 Query Rewrite 默认使用已配置的 DeepSeek；未配置或改写失败时回退原问题。

## 评测

。当前 RAG v5 使用 50 道标注题比较 Dense、Rerank Hybrid 和 Rewrite + Rerank Hybrid；在测评集上的 Recall@3 分别为 **0.84、0.90、0.96**。详见 [RAG v5 实验](docs/evaluation/rag-v5.md) 与 [评测数据目录](data/evaluation/rag/)。
| 检索方案 | Recall@3 | Precision@3 | MRR@3 | nDCG@3 |
|---|---:|---:|---:|---:|
| Dense | 0.8400 | 0.2800 | 0.7033 | 0.7383 |
| 重排 Hybrid | 0.9000 | 0.3000 | 0.7933 | 0.8209 |
| Rewrite + 重排 Hybrid | **0.9600** | **0.3200** | **0.8433** | **0.8736** |

实验结果表明，Rewrite + 重排 Hybrid 综合表现最佳，Recall@3 达到 0.9600，较 Dense 基线提升 12 个百分点。

另外，项目包含 20 道客服 Agent 端到端用例，覆盖政策问答、订单查询、退款、条件任务和工单确，结果为 **20/20**。

```powershell
uv run pytest -q
uv run python scripts/evaluate_rag.py
```

涉及 Rewrite 的在线评测可能产生 API 费用；运行参数和复现条件以各版本报告为准。

## 项目结构

```text
src/agents/             Agent 图与任务编排
src/customer_support/   售后工具、MCP 与 RAG
src/memory/             Memory、上下文组装与压缩
src/service/            FastAPI 服务与工作台接口
src/evaluation/         评测实现
data/policies/          版本化政策
data/evaluation/        评测集与报告
docs/                   架构和使用说明
scripts/                初始化、索引与评测脚本
tests/                  自动化测试
```

模拟规则仅用于演示；生产部署前需补充正式身份认证、权限控制和运行治理。
