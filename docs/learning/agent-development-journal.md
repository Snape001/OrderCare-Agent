# OrderCare-Agent：Agent 开发问题与解决记录

整理日期：2026-10-29。本文是持续更新的开发记录，重点保留与 Agent 岗位相关的**问题、定位证据、解决办法和验证边界**。这里的测试数字只对应当时实际执行的命令；新增问题时在文末追加，不覆盖旧结论。详细的早期案例见本目录的 `bug-001`、`bug-002`、`bug-003`。

## 记录规范

每条新增记录写明：发生场景与输入、预期和实际行为、根因及定位方法、修改位置、自动化或真实模型验证结果、仍存在的限制。模型提出工具调用、工具实际执行、最终答复是三个不同的事实，应分别记录。不得记录 API Key、完整手机号或真实客户资料。

## 1. 关键词路由把问候送进 RAG

- **现象**：在 Offline Mock 中问“你好，请简单介绍一下你能帮助我处理哪些售后问题”，却返回特殊商品退换政策和检索分数。另一个方向的误路由是“订单完成 40 天后还能申请电子发票吗”曾被当成具体订单查询。
- **根因**：仅凭“售后”“订单”等宽泛词判断意图；分支顺序让前面的错误分支截住请求。RAG 本身检索到内容，不代表这个请求本应进入 RAG。
- **解决**：在 [`customer_support_mock.py`](../../src/agents/customer_support_mock.py) 中区分功能介绍、明确业务操作和一般政策问题；明确的订单查询和退款资格判断进入业务工具，政策问题继续复用原检索实现。
- **验证**：[`test_mock_agent.py`](../../tests/customer_support/test_mock_agent.py) 同时断言回复和工具调用次数，确保问候不调用 `search_policy`，政策问题仍返回来源。
- **经验**：先测“是否选对工具”，再测检索内容质量；路由测试必须包含词语重叠的反例。

## 2. 多轮补参丢失查询任务

- **现象**：用户先问物流，再输入 `C001`，Agent 要么误回欢迎语，要么继续索要订单号。`C001` 实际是演示客户 ID，不是订单号；查询还需要手机号后四位。
- **根因**：原 Mock State 只有待确认工单，没有待查询意图与有效参数；下一轮孤立的参数无法关联原任务。原订单号正则在紧邻中文时也可能漏识别。
- **解决**：在原 LangGraph State 增加 `pending_query`，保存查询类型与已校验格式的参数；用 Checkpoint 按会话恢复。格式错误只作为输入校验，订单是否存在及手机号是否匹配仍由 [`store.py`](../../src/customer_support/store.py) 查询确认。失败时返回统一提示，取消任务时清除状态。
- **验证**：按 `物流查询 → C001 → ORD1001 → 8821` 逐轮断言 State 和 `get_order_status` 调用；另测一次性提交、错误手机号重试、取消和不同 `thread_id` 隔离，见 [`test_mock_agent.py`](../../tests/customer_support/test_mock_agent.py)。
- **经验**：多轮对话不是把历史消息拼起来就够了；需要明确哪些业务槽位已经有效、何时保留、清除或重新验证。

## 3. 模型回答正确，不等于真实调用了工具

- **现象**：接入本地 `qwen3:4b` 后，仅看最终文字无法判断订单状态是数据库返回，还是模型猜测。
- **根因**：Agent 运行包含模型生成的 `AIMessage.tool_calls`、工具执行形成的 `ToolMessage`、模型最终答复三个阶段。只检查最后一阶段会产生虚假的通过结果。
- **解决**：[`verify_ollama_agent.py`](../../scripts/verify_ollama_agent.py) 分别记录模型提出的工具名和实际执行的工具名；Fake Model 测试还检查错误工具名、缺参数和工具结果回传，见 [`test_ollama_agent.py`](../../tests/customer_support/test_ollama_agent.py)。
- **验证**：真实 Ollama 最终一轮 6/6 通过；政策、订单、退款案例分别观察到 `search_policy`、`get_order_status`、`check_refund_eligibility` 的提出与执行。结果见本地 `reports/ollama-verification.json`。
- **经验**：Agent 测试应以执行轨迹和业务副作用为依据，不能把“回答像真的”当作工具调用证据。

## 4. 小模型把服务介绍误判为政策问题

- **现象**：首轮真实 Ollama 验证中，功能介绍类问候触发了 `search_policy`；同轮其他五项案例通过。
- **根因**：在线 Agent 原提示词把包含“售后”的问题宽泛归为具体政策咨询；模型据此选择了检索工具。它暴露的是模型路由边界，不是 RAG 算法故障。
- **解决**：在 [`customer_support_agent.py`](../../src/agents/customer_support_agent.py) 的系统提示中明确：纯问候和询问服务能力直接介绍服务，不调用工具。Ollama 模式仍由模型生成结构化工具调用，没有用关键词代码伪造模型选择。
- **验证**：调整后重跑全部六个真实案例，问候没有 `tool_calls` 或 `ToolMessage`，其余工具案例通过。这个结果只证明所测表达，不代表所有自然语言改写都稳定。
- **经验**：离线 Mock 的正确性不能直接外推到真实 LLM；要保留失败的自然语言输入，按轨迹判断是提示词、模型能力、工具 schema 还是业务层问题。

## 5. 工单写操作需要独立于模型的安全边界

- **现象**：模型可以提出创建工单，但“模型想调用”并不等于用户已授权。模糊确认文字也曾有误判风险。
- **解决**：在线图使用 `HumanInTheLoopMiddleware` 在 `create_support_ticket` 执行前中断；服务端把明确确认转换为 `approve`，其他答复走拒绝；工具层先校验订单与手机号，数据库层保留工单幂等键。相关位置见 [`customer_support_agent.py`](../../src/agents/customer_support_agent.py)、[`tools.py`](../../src/customer_support/tools.py)、[`confirmation.py`](../../src/customer_support/confirmation.py)。
- **验证**：Fake Model 的批准与拒绝测试覆盖中断恢复；真实 Ollama 工单案例观察到模型提出 `create_support_ticket`、工具**尚未执行**、拒绝后工单表仍为零。会话访问控制见 [`test_access_control.py`](../../tests/service/test_access_control.py)。
- **经验**：权限、身份校验、审批和幂等必须落在服务或工具层，不应只写在 Prompt 中。

## 6. LangGraph 事件不能只取最后一项

- **现象**：早期 Qwen 集成中，工具已经执行，FastAPI 却返回 500；工单审批中断也曾被普通回复覆盖。
- **根因**：图运行会产生 `updates`、`values` 和 `__interrupt__` 等不同事件，最后一项不一定是最终完整状态。
- **解决**：[`service.py`](../../src/service/service.py) 优先扫描中断；没有中断时再选最终 `values`。详细定位和当时的验证见 [`bug-002-qwen-agent-event-handling.md`](bug-002-qwen-agent-event-handling.md)。
- **经验**：Agent API 层必须理解图事件语义，不能假设一次调用只产生一条模型回复。

## 7. 本地模型配置与启动诊断

- **现象**：通用模型工厂已有 `ChatOllama`，但默认客服加载代码只在 Mock 和 Qwen 之间切换；仅设置 `OLLAMA_MODEL` 不会让默认客服使用本地模型。
- **解决**：在 [`settings.py`](../../src/core/settings.py) 增加明确的 `ollama` 客服模式和可配置连接、请求超时；客服加载时检查 Ollama `/api/tags` 及模型名称，再构建原有工具调用图。不可用时明确报错，不静默回退 Mock。现有 `langchain-ollama` 已在依赖和锁文件中，无须换框架或新增包。
- **验证**：本机 `qwen3:4b` 的 `/api/tags` 返回 200，真实加载得到 `CompiledStateGraph`；将地址设为不可达端口时，加载报 `Ollama is unavailable at OLLAMA_BASE_URL`。配置与失败路径还有自动化测试。
- **经验**：区分“项目支持某 Provider”和“目标 Agent 实际使用该 Provider”；模型实例化成功也不等于服务或指定模型可用。

## 8. 测试输入与环境也会造成假故障

- **中文编码**：早期 PowerShell 管道把中文问题变成问号，模型因此不选政策工具；改为 UTF-8 脚本请求后定位并解决，详见 [`bug-003-powershell-utf8-e2e.md`](bug-003-powershell-utf8-e2e.md)。
- **环境污染**：全量测试曾因脚本导入时 `load_dotenv()` 使默认设置测试读到本地 `.env` 值而失败；默认值测试复用 `mock_env` 隔离环境，没有删除原断言。
- **Windows 临时库**：首次真实 Ollama 验证在写报告前因未关闭临时 SQLite 连接而清理失败；脚本改为显式关闭连接后重跑，报告正常生成。
- **经验**：发现异常先确认输入编码、环境变量、连接生命周期和调用轨迹，再决定是否修改 Prompt 或业务规则。

## 当前验证边界与后续追加

截至本次整理，上一轮完整 pytest 为 **216 passed、2 skipped**（Docker 集成测试需要额外环境），离线 Agent 评测 **34/34**；真实 Ollama 六项案例 **6/6**。这些是有限样本，不代表线上准确率或并发稳定性。后续新增记录应保留真实失败输入和测试命令；如现象尚未复现或未验证，明确标为“待确认”，不得写成已修复。

## 9. Ollama 思考内容和工具参数进入用户界面

- **现象**：Streamlit 中出现模型自述的推理文字、`</think>` 和 `Tool Call: get_order_status`，随后才是最终答复；工具状态区域还展开原始参数和工具结果。
- **根因**：本机 `ChatOllama` 已设置 `reasoning=False`，但实测 `qwen3:4b` 的普通回答仍可能在 `content` 中包含孤立的 `</think>`，且没有独立的 `reasoning_content` 字段；FastAPI 原流式路径又转发 LangGraph 的所有 `messages`、`updates` 和 token，Streamlit 展开中间消息与工具调用。模型端关闭思考与用户展示边界是两层不同保障。
- **解决**：保留图内完整执行轨迹；Ollama 客服的对外接口只发布完成后的 AI 答复或不含参数的人工确认提示，不发布原始工具调用、工具结果与中间 token。对意外落入最终内容的 `<think>` 区块使用缓冲解析，先收齐再输出，支持跨块标签和孤立闭合标签。同步调用与历史读取使用相同的公共视图。其他 Agent 和 Mock 路径保持原行为。
- **验证**：[`test_customer_presentation.py`](../../tests/service/test_customer_presentation.py) 检查分块标签、订单/政策/问候答复、参数不泄露及工单中断；本机真实 `qwen3:4b` 返回的孤立闭合标签在公共视图中被去除。完整回归结果以本次最终报告为准。开发者仍可通过本地 Agent 图轨迹、已有离线验证报告和可选的 Langfuse Trace 排查工具行为，公共接口不暴露原始推理。
- **经验**：`reasoning=False` 是模型侧设置，不能代替 API 的输出白名单；Agent 的内部状态和用户可见消息必须分开建模。

## 10. 慢模型请求让聊天界面看似卡住

- **现象**：`qwen3:4b` 在工具调用前后可能长时间没有可展示的 SSE 消息；Streamlit 原来直接等待异步请求，用户看不到耗时，重复提交和失败后输入状态也缺少明确控制。客户端 `timeout=None` 未提供整体截止时间。
- **解决**：[`streamlit_app.py`](../../src/streamlit_app.py) 使用提交回调立即禁用聊天输入，并在原请求旁运行按秒更新的等待提示；设置可配置的整体超时，成功、异常、超时和脚本中断时清理状态并重新启用输入。语音输入封装也传递禁用与提交回调。客服界面只渲染完成的 AI 答复和人工确认提示；纯文本思考过滤移到 [`presentation.py`](../../src/schema/presentation.py)，供 API 与轻量前端复用。
- **验证**：界面测试检查请求尚未结束时出现 0、1、2 秒提示，以及超时取消、错误恢复、重复提交、内部工具消息隐藏和人工确认提示；语音输入测试检查禁用状态透传。此次完整 `pytest -q` 实际结果为 **237 passed、2 skipped**；跳过的是未启用 `--run-docker` 的 Docker 集成测试。本地 Streamlit 实测“请说明特殊商品退换有哪些限制，并给出政策来源”：页面先显示 0 秒，等待中观察到 5 秒和 10 秒，最终给出含政策来源的答复，等待提示消失且输入恢复；页面未见思考文字或原始工具参数。这次界面观察本身不证明实际工具调用，工具调用需另看 Agent 轨迹。
- **经验**：模型耗时与工具执行耗时要用同一个用户可见的请求状态表示；异步计时必须在请求仍运行时刷新，测试也应在请求完成前断言状态，而不能只检查最终耗时。输入锁与错误恢复需一起设计。
