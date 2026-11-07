# Automatic Context Compaction：离线验证

运行：`$env:PYTHONPATH='src'; uv run --frozen python scripts/evaluate_compaction.py`。脚本使用固定的四轮合成客服对话、假 Redis Store 和保守 Token 估算，不调用 DeepSeek、Ollama 或付费 API。原始逐项结果保存于 [`results.json`](../../data/evaluation/context-compaction-v1/results.json)。

| 指标 | 离线结果 | 计算范围 |
| --- | ---: | --- |
| 未裁剪输入估算 Token | 1103 | System Prompt + 完整合成对话 |
| 压缩并动态组装后估算 Token | 566 | System Prompt + 结构化摘要 + 保留的近期消息 |
| 相对未裁剪输入节省率 | 48.69% | `(1103 - 566) / 1103`；包含第二阶段 Context Manager 的历史筛选收益 |
| 关键字段保留率 | 3/3 | 人工列出的订单号、政策引用、文字客服偏好均在摘要中 |
| 任务连续性检查 | 通过 | 当前问题、系统动态事实规则和三项标注信息仍可见 |
| API 调用 | 0 | 完全离线 |

专项测试覆盖 80% 阈值触发与未触发、增量合并、重复压缩、两次并发仅一次写入、Redis 重启后的摘要读取、不同会话身份隔离、Redis 故障、工具消息配对、原始 Checkpoint 保留，以及当前轮次消息保护。测试使用 Mock Redis 与假模型；真实 Redis 容器和真实 LLM 尚未做冒烟验证。

摘要是保守摘录：只取旧用户消息与结构化工具结果，不读取 AI 的思考或中间文本；手机号后四位等敏感片段脱敏，过长或超出摘要预算的历史段会跳过。因此 3/3 是合成样本的字段检查，不能代表真实复杂对话的语义正确率。上线前需用独立人工标注的长对话评估事实遗漏、错误合并和任务完成率。真实模型冒烟测试需先估算调用次数与费用并获得确认。

本次全量 pytest：315 通过、2 跳过、24 失败。失败均为旧版 RAG 数据集 `dataset-v1.json` 与当前政策文件的 SHA256 不一致，未修改 Gold Dataset、政策快照或校验逻辑。相关 Agent/Memory 回归测试 27 通过；敏感片段回归测试 3 通过。Ruff、mypy 和 `git diff --check` 均通过。当前环境未安装 Docker，Redis 行为由离线假服务验证。
