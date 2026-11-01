# 客服业务工具 MCP 接入

## 结构

`customer_support.mcp_server` 使用 Python MCP SDK 1.x 的 `FastMCP`，通过本地 STDIO 暴露四个工具。每个工具调用 `customer_support.tools` 中已有的 LangChain 工具；订单身份校验、退款判断、RAG 检索与工单幂等性仍由原业务函数负责。

客服 Agent 加载时，`customer_support.mcp_client` 通过现有 `langchain-mcp-adapters` 发现工具，并把 MCP 文本内容块还原成原 Graph 使用的 JSON 工具结果。工具名称不变，因此 Router、Planner、Agent Loop 与 `HumanInTheLoopMiddleware` 的调用方式不变。模型仍由 `LLM_PROVIDER` / `CUSTOMER_SUPPORT_MODE` 选择 DeepSeek 或 Ollama；Checkpoint、Memory、会话 ID 均留在原 LangGraph 服务链中。

| MCP Tool | 参数 | 原业务工具 |
| --- | --- | --- |
| `get_order_status` | `order_id`, `phone_last4` | `get_order_status_tool` |
| `check_refund_eligibility` | `order_id`, `phone_last4` | `check_refund_eligibility_tool` |
| `search_policy` | `query` | `search_policy_tool` |
| `create_support_ticket` | `order_id`, `phone_last4`, `category`, `summary`；Server 还要求内部签名 | `create_support_ticket_tool` |

所有工具返回 JSON 对象，包含布尔值 `ok`；原有业务字段（例如 `eligible`、`order_id`、`references`）保持在顶层。工具内部异常统一返回 `ok=false` 和 `error_code=MCP_TOOL_ERROR`，日志只写 stderr。MCP 连接错误会向上抛出，不切换模型或回退到本地工具。

## 工单确认

Graph 仍在调用 `create_support_ticket` 前中断，等待用户批准；拒绝时不会调用 MCP 写工具。STDIO Server 要求工单参数的内部签名，否则返回 `APPROVAL_REQUIRED`。签名由客服 MCP Client 在工具实际执行时添加，且不会出现在提供给模型的参数 Schema 中；现有 `HumanInTheLoopMiddleware` 在该执行前暂停。STDIO Server 仅供同机可信进程使用，本阶段没有远程 MCP 服务。

## 启动与验证

正常启动项目即可由客服 Agent 自动启动本地 MCP 子进程，无需另开端口。手动启动 Server（它会等待 MCP 客户端连接，不打印协议消息）：

```powershell
$env:PYTHONPATH="src"
uv run --frozen python -m customer_support.mcp_server
```

另开终端验证工具发现：

```powershell
$env:PYTHONPATH="src"
uv run --frozen python -c "import asyncio; from customer_support.mcp_client import load_business_mcp_tools; print([tool.name for tool in asyncio.run(load_business_mcp_tools())])"
```

验证命令会自行启动一个 STDIO 子进程。运行测试时设 `CUSTOMER_SUPPORT_DB_PATH` 指向隔离 SQLite 文件；自动化测试已使用独立临时数据库，未写入默认业务库。当前 `langchain-mcp-adapters` 已在项目依赖中；显式约束 `mcp>=1.28,<2` 是为了保持与已锁定的 Python MCP SDK 1.x API 一致。
