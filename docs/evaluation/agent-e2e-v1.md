# 客服 Agent 端到端测评

基于冻结的 [20 道用例](../../data/evaluation/agent-e2e-cases-v1.json)，使用真实 DeepSeek Agent、MCP 业务工具与 DeepSeek Judge 跑完 20 题。最终严格通过 **18/20**；政策检索调用 **8/8**，7 道可答检索题章节级平均 Recall@3 为 **0.5714**。工单批准后创建 2/2，拒绝后无写入 2/2。

人工复核认为两处预期超出了用户实际请求，另发 [v1.1 用例](../../data/evaluation/agent-e2e-cases-v1.1.json)，沿用同一次运行轨迹与 Judge 逐项判定后为 **20/20**。[复核报告](../../data/evaluation/agent-e2e-v1/20261112T132053Z-manual-v1.1/report.md)记录每处修正。18/20 → 20/20 是评分标准变化，**不是 Agent 重新运行或能力提升**。

[完整报告](../../data/evaluation/agent-e2e-v1/20261112T132053Z-rejudge-132746/report.md) · [汇总数据](../../data/evaluation/agent-e2e-v1/20261112T132053Z-rejudge-132746/summary.json) · [人工抽查](../../data/evaluation/agent-e2e-v1/20261112T132053Z-rejudge-132746/human-review.json)

失败题为 `015`（冻结用例要求独立订单查询，Agent 只用可返回订单信息的退款资格工具）和 `017`（工单答复遗漏 12 小时响应目标）。本次显式接受用例语料哈希与当前 v3 政策哈希不一致，因此不能作为旧语料的严格复现。详细限制见完整报告。
