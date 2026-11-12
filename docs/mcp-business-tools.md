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

所有工具返回 JSON 对象，包含布尔值 `ok`；原有业务字段（例如 `eligible`、`order_id`、`references`）保持在顶层。工具内部异常统一返回 `ok=false` 和 `error_code=MCP_TOOL_ERROR`，日志只写 stderr。MCP Client 对工具调用施加超时和按工具隔离的熔断保护；连接、协议和超时故障返回明确的 `ok=false` 结果及人工处理提示，不绕过 MCP 调用本地工具。

## 调用保护

政策检索的成功结果缓存由 `customer_support.policy.search_policy` 统一维护，TTL 默认 600 秒，键包含原始 Query、政策文件内容指纹和检索配置版本；缓存有容量上限，仅缓存带有证据的成功结果，返回副本。直接调用、调试入口和 MCP 业务工具因共用该入口而使用相同策略。订单查询与退款资格仍由 MCP Client 缓存 15 秒，键包含完整工具参数；工单写入不缓存、不自动重试。缓存和熔断状态属于进程内存，进程重启后清空。

保护分为两层：`search_policy` 入口负责改写后的本地索引检索/重排超时和独立熔断；MCP Client 负责 MCP 连接、协议和工具调用超时及传输熔断。两层都在各自服务进程内维护状态。政策检索连续 3 次执行故障后熔断 30 秒，到期仅允许一个探测请求；正常空结果不计故障且不缓存。检索故障返回 `ok=false`、稳定错误码及人工处理提示，不伪装成知识库空结果。改写服务异常由既有逻辑回退到原始 Query，不计作本地检索故障。同步本地检索通过固定大小线程池等待截止时间；超时会停止等待并触发熔断，但 Python 无法强制终止已经运行的推理线程，线程会占用有限工作槽直至自行结束。

MCP 每个工具连续 3 次遇到超时、连接/协议错误或 `MCP_TOOL_ERROR` 后熔断 30 秒，到期仅允许一个探测请求。业务拒绝（如订单不存在、身份校验失败）不触发熔断。默认单次 MCP 工具超时 30 秒，工单工具 20 秒。工单调用超时或连接中断时返回 `TICKET_STATUS_UNKNOWN`，提示先核查工单状态再决定是否重试，因为 MCP 断连时服务端可能已经完成写入；现有确认签名和业务幂等键仍生效。

可通过 `.env` 中的 `POLICY_SEARCH_CACHE_TTL_SECONDS`、`POLICY_SEARCH_CACHE_MAX_ENTRIES`、`POLICY_SEARCH_TIMEOUT_SECONDS`、`POLICY_SEARCH_CIRCUIT_FAILURE_THRESHOLD`、`POLICY_SEARCH_CIRCUIT_RESET_SECONDS`、`POLICY_SEARCH_WORKER_LIMIT` 调整检索执行保护；`MCP_BUSINESS_CACHE_TTL_SECONDS`、`MCP_READ_CACHE_MAX_ENTRIES`、`MCP_TOOL_TIMEOUT_SECONDS`、`MCP_TICKET_TIMEOUT_SECONDS`、`MCP_CIRCUIT_FAILURE_THRESHOLD` 和 `MCP_CIRCUIT_RESET_SECONDS` 调整 MCP 传输保护。Trace 只记录事件类别、状态、错误码类型与耗时，不记录缓存键或用户 Query。

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
