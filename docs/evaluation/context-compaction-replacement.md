# Context Compaction：摘要替代旧历史的离线候选实验

> 本文保留当时的离线实验结论。候选组装器后来已通过 `CONTEXT_COMPACTION_ENABLED` 开关接入 Agent 模型调用链，**默认仍关闭**；当前实现与 42 题 Memory 评测见[架构说明](../architecture/layered-memory.md)及[Memory 评测](memory-evaluation.md)。下文“尚未接入线上”等措辞仅描述本实验当时的状态。

## 实现边界

新增 [`CompactedContextAssembler`](../../src/memory/context_compaction_candidate.py)，只由离线脚本调用；现有 `assemble_model_context` 与线上 `ContextManager.assemble` 调用方式均未改变。候选接收完整的 `{cursor, summary}` 记录，校验指纹、位置和完整消息组边界，然后仅从模型视图移除游标覆盖的旧消息。LangGraph Checkpoint、Redis TTL、Lua 并发写入、业务工具与 Agent State 保持原样。游标无效或会覆盖要求保留的最近 N 个用户轮次时，候选回退到现有动态组装结果。

候选预算独立配置为摘要 320 Token、长期记忆 120 Token、最近 2 个用户轮次（**包含当前轮次**）。组装优先保留系统规则、当前请求、审批与任务状态、最近原始对话；随后按“约束、实体、引用、目标、待办、决定、已完成、偏好”的顺序择取摘要事实，最后才添加相关短期摘要和长期记忆。如果摘要预算无法容纳必要的约束、实体或引用，则保留现有动态组装结果，不删除旧历史。当前 RAG/业务工具结果仍由既有 `ContextManager` 按独立预算整组选择，不能拆开 Tool Call 与 ToolMessage；历史订单状态在摘要中仅作线索，模型仍被要求重新核验。候选不会读取模型原始思考。

## 数据与口径

复用 [`context-compaction-v2/dataset-v1.json`](../../data/evaluation/context-compaction-v2/dataset-v1.json) 的两组固定合成对话和原有压缩器，不修改数据集、已保存的 DeepSeek 六次输出或历史结果，也**没有新增 API 调用**。运行：

```powershell
$env:PYTHONPATH='src'
uv run python scripts/evaluate_compaction_candidate.py
```

默认逐题数据见 [`candidate-replacement-v1.json`](../../data/evaluation/context-compaction-v2/candidate-replacement-v1.json)。所有方案使用相同的保守字符 Token 估算器、总预算 900；为让短样本触发压缩，离线压缩器使用总预算 350、摘要上限 1200。生产默认总预算 4096、80% 阈值及摘要上限 384，**这两组短对话在生产默认配置下不会触发压缩**。事实保留率采用同一套严格字符串/来源章节校验；同义改写可能被判缺失，不能与第四阶段的人工语义 8/8 直接比较。

| 指标（两题合计） | 原始完整上下文 | 仅动态裁剪 | 旧策略：摘要追加 | 候选：摘要替代旧历史 |
| --- | ---: | ---: | ---: | ---: |
| 模型视图估算 Token | 1038 | 618 | 998 | **703** |
| 摘要实际注入 | 不适用 | 不适用 | 1/2 | **2/2** |
| 标注事实保留（严格校验） | 8/8 | 3/8 | 6/8 | **8/8** |
| 相对完整上下文 Token 减少 | 0% | 40.46% | 3.85% | **32.27%** |
| 相对仅动态裁剪 Token 变化 | +420 | 0 | +380 | **+85** |
| 超出总预算 | 0/2 | 0/2 | 0/2 | **0/2** |

候选每题分别为 `560 → 382` 与 `478 → 321` Token。相比“追加摘要”，替代策略少 295 Token（约 29.56%），并把注入率从 1/2 提到 2/2；但相比**仅动态裁剪**仍多 85 Token，收益是更多关键事实进入模型视图，而非最低 Token 开销。摘要源事实中 7/17 条是重复字段或已在近期对话出现，源重复信息比例 **41.18%**；候选对精确重复做去重后，最终注入行的精确重复比例 **0%**。这不涵盖同义重复。

为观察预算权衡，还在同一两题上做了不涉及 API 的敏感性检查，原始记录分别保存于 `candidate-replacement-budget160/200/240.json`：

| 摘要预算 | 视图 Token | 摘要注入 | 严格事实保留 | 相对仅动态裁剪 |
| ---: | ---: | ---: | ---: | ---: |
| 160 | 578 | 1/2 | 5/8 | −40 |
| 200 | 630 | 2/2 | 7/8 | +12 |
| 240 | 663 | 2/2 | 8/8 | +45 |
| 320（预设主实验） | 703 | 2/2 | 8/8 | +85 |

这些预算结果是在**同一开发样本**上观察的，不能事后选 240 并声称有留出集收益。160 在一题因必要事实装不下而安全回退，另一题虽省 Token，但总共只保留 5/8 条标注事实；240 和 320 都保全事实，但仍高于仅动态裁剪 Token。

### 复用已保存的 DeepSeek 摘要

为直接复核第四阶段 DeepSeek 摘要 **0/2 注入**的问题，离线脚本还复用已保存的六次模型输出，**没有新 API 调用**：

```powershell
uv run python scripts/evaluate_compaction_candidate.py --summary-source saved_deepseek --output data/evaluation/context-compaction-v2/candidate-replacement-llm-v1.json
```

逐题记录见 [`candidate-replacement-llm-v1.json`](../../data/evaluation/context-compaction-v2/candidate-replacement-llm-v1.json)。同一 320 Token 摘要预算下，两份模型摘要均进入模型视图（**0/2 → 2/2**），合计 **876** 估算 Token，较完整上下文少 15.61%，但较仅动态裁剪**多 258**。严格字面/来源校验为 **6/8**；缺失两项是第二题条件与审批约束的同义表述，不能直接认定模型语义忘记，也不能将第四阶段对完整摘要的人工 8/8 视为此预算内选取结果的独立评分。候选不应据此替换线上策略。

## 安全验证与结论

新增测试覆盖游标替代与最近轮次、错误游标回退、游标不能截断工具调用组、RAG 当前证据与审批/验证/任务状态保留、预算不足时安全回退、精确去重、短期/长期记忆优先级、旧格式游标遇到重复消息。相关 pytest **22 通过**。实验脚本及候选模块通过 Ruff 和 mypy，`git diff --check` 通过。生产 Agent 没有导入候选模块，也没有增加启用开关。

**暂不启用线上。** 两组短合成对话下，候选解决了“摘要不注入”和“旧历史与摘要重复出现”，但相对只裁剪方案仍增加 Token；没有新的真实模型三方案回答 A/B、真实长会话、留出集或默认生产阈值下的效果证据。下一步若获准，应先收集足够长且确实触发默认阈值的离线样本，再评估事实保留、工具连续性和延迟；本阶段不自动调用 DeepSeek。
