# 客服多路 Router + Planner（MVP）

客服仍由 `create_agent` 驱动原有 LangChain/LangGraph 工具循环。Router 是 `before_agent` middleware：使用当前 DeepSeek 或 Ollama 模型的 function calling 结构化输出，给出多意图和实体；订单号、手机号后四位及其他实体由用户原文校验。缺少身份字段时结束本轮并追问。单意图直接生成一个简单任务，不调用 Planner。

多意图或条件请求再调用 Planner，输出至多六个带 ID、依赖和 `when` 的顺序步骤。计划只允许映射到现有 `search_policy`、`get_order_status`、`check_refund_eligibility`、`create_support_ticket` 或总结。校验禁止额外写入任务、前向依赖及无退款检查的条件分支。模型的规划输出不直接执行数据库函数。

`before_model` 和 `wrap_model_call` 从 Checkpoint 中的 ToolMessage 计算任务状态，每次只开放当前任务对应的工具并指定 tool choice。`eligible` 必须来自退款资格工具的成功结果；失败时停止并说明错误，成功时跳过维修查询，失败时才查维修政策。当前没有实际执行退款的写工具，Agent 只能报告资格和后续申请流程。工单继续经过原有 `HumanInTheLoopMiddleware` 的 approve/reject 中断，Checkpoint 恢复后不会再次调用 Router。`route`、`plan`、`task_trace` 与消息保存在同一图状态。

结构化分类先于正文生成，因此每轮增加一次本地/云模型请求；复杂请求再增加一次 Planner 请求。现有模型调用失败会明确报错。Router 与 Planner 未做真实 DeepSeek API 的准确率基准测试；`routing_metrics`、`planning_correctness`、`planning_metrics` 提供意图精确匹配率、按顺序/依赖/条件匹配的规划正确率、规划有效率和任务完成率的基础计算接口，离线测试使用固定标注/工具输出验证逻辑，不把模拟模型结果宣称为真实模型准确率。当前只支持简单顺序与退款资格条件，不能替代完整业务编排。

Router 的结构化 `Route` 可选复用 Memory 的同一 Redis 客户端做短缓存，减少高频重复分类调用。缓存键只由归一化后的当前 query 生成（折叠空白，不包含最近对话或模型标识），值只保存 `intents`、`conditional` 和 `product_name`，不保存订单号、手机号后四位或 `issue`；命中后仍用当前对话重新执行 `validated_route`，因此当前原文不存在的订单号/手机号不会被缓存带出。TTL 默认 300 秒，读写超时默认 0.2 秒，Redis 异常、超时或坏数据均按 miss 处理，不阻断路由；Planner 不进入该缓存。缓存事件在 router trace 中以 `cache=hit|miss|error|disabled` 记录。由于键不含最近对话，同一 query 在不同上下文中会共享分类结果，这是提高命中率的显式取舍；如需严格按多轮上下文隔离，应改为包含最近 HumanMessage 的键并同步调整 TTL。
