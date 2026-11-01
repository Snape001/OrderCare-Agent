# Ollama / DeepSeek Provider

客服 Agent 复用现有 `CustomerSupportAgent.load → get_model → create_agent`。DeepSeek 由 `langchain-openai` 的 `ChatOpenAI` 连接官方 OpenAI-compatible Chat Completions API；无新依赖。模型调用后仍经过现有 LangGraph 工具、Checkpoint、工单人工确认和 SSE 服务层。

## 切换

将 `.env.deepseek.example` 中的设置复制到被 Git 忽略的 `.env`，填写自己的 `DEEPSEEK_API_KEY`，然后运行项目原有的服务启动命令。`LLM_PROVIDER=deepseek` 时使用 DeepSeek；改为 `LLM_PROVIDER=ollama` 并设置 `OLLAMA_MODEL=qwen3:4b` 时使用本地 Ollama。`LLM_PROVIDER` 未设置时仍按旧的 `CUSTOMER_SUPPORT_MODE` 选择；两者同时设置时前者优先。切换后重启后端，并创建新会话，避免旧审批中断被不同图恢复。

`DEEPSEEK_BASE_URL=https://api.deepseek.com`、`DEEPSEEK_MODEL=deepseek-flash`、`DEEPSEEK_TEMPERATURE=0`、`DEEPSEEK_MAX_TOKENS=4096`、`DEEPSEEK_TIMEOUT=60` 可按环境调整。模型名取自[官方首次调用文档](https://api-docs.deepseek.com/zh-cn/)；DeepSeek [Tool Calls 指南](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)使用 Chat Completions function calls。本项目设置非思考模式以配合工具调用。

默认测试只用测试密钥和注入的模型，不访问 DeepSeek。真实 API 验证必须在自行配置密钥后显式运行：启动后端，使用网页分别测试普通问答、政策来源、带订单号与手机号后四位的订单查询、退款资格、同会话追问，以及工单审批和 SSE 流式输出。模型连接或认证错误会返回明确错误，不切换到其他 Provider。真实外部 API 全链路尚未在本次运行，因为手动触发可能产生费用。

不要在命令行粘贴密钥；放入本地 `.env`。若密钥曾出现在聊天记录中，建议到 DeepSeek 控制台轮换。
