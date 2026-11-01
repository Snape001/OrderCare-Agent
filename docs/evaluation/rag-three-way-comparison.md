# RAG 三方案对比：2026-10-31

## 实验协议

同一份 40 题 `dataset-v1.json`、同一政策章节与 BGE/Chroma 索引、Top-2、原有阈值和生成 Prompt。Direct 使用现有 `dense`，Hybrid 使用现有 `hybrid`；第三组仅在独立评测脚本中用 DeepSeek 改写 Query，再调用同一个 `hybrid`。线上 `search_policy` 默认策略未改。

数据集记录的政策 SHA256 为 `f0aa9a1d...`，当前工作区文件为 `bd19858c...`。差异来自顶层标题“星河商城客服业务政策”改为“OrderCare客服业务政策”。评测保存 Git 中的冻结版本，并要求其完整 SHA256 与数据集相同，再逐节确认当前 16 个索引章节的标题与正文完全相同。任一校验失败就停止；没有改写 Ground Truth，也没有关闭原校验。原评测测试若直接对当前文件调用 `load_dataset`，仍会因 SHA 不一致失败，这是预期的完整性保护。

Query Rewrite 的 Prompt 与模型参数存入 `rewrite-cache.json`。重写保留订单号、数字、已知商品词和否定表达；自动校验拒绝明显漂移，并将该题保守地按原 Query 检索。校验不能证明语义完全一致，因此原始回答与改写文本都保留供复审。此次 40 条中 1 条因为“没”改为“未”被保守拒绝。

生成复用 `GenerationRunner` 的生产政策 Prompt 回放与严格结构化 Judge。为控制调用次数，只对三组证据有差异的 12 题和 2 道对照题生成，三组使用同一组 14 题。独立 Evidence Sufficiency 审计覆盖全部 40 题，按同一题的相同证据去重；39 个可答上下文实际调用 DeepSeek，无答案题直接依据冻结标签记证据不足。Judge 不可靠的指标保留 `null`，有效样本数与配对样本数单列。

## 结果与决策

| 方案 | 40题 Recall@2 | MRR@2 | nDCG@2 | 留出集 Recall@2 | 独立证据充分性 | 无答案空检索率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Direct | 0.8833 | 0.9000 | 0.8874 | 0.9000 | 0.6250 | 0.2000 |
| Hybrid | 0.8833 | 0.8833 | 0.8751 | 0.9000 | 0.6250 | 0.2000 |
| Rewrite + Hybrid | 0.9167 | 0.9167 | 0.9085 | 0.9667 | 0.6500 | 0.2000 |

Hybrid 与 Direct 的召回相同，排序略差。Dense 在 `rag-005` 的定制杯子问题把特殊商品章节排第一，Hybrid 排第二；其余排序差异没有提高标注检索指标。改写只改变 `rag-016` 的 Top-2：把“显示签收却没收到”对应的物流异常章节召回，独立证据充分性由 0 变成 1。开发集没有检索收益。没有发现已确认的“召回提升但回答质量下降”案例；留出集生成评分有效配对数不足，不能据此排除此风险。

14题生成样本中的4道无答案题，严格 Judge 能可靠评分的分别只有 Direct 2题、Hybrid 2题、Rewrite + Hybrid 3题；这些有效题的拒答准确率均为1.0。其余为 `null`，不能据此声称40题的无答案拒答已解决。三方案在检索层仍有8/10道无答案题返回同主题上下文。

平均本地检索约 17–19 ms；DeepSeek 改写额外平均 677 ms/题。此次共 163 次 API 请求，包括 40 次重写、42 次生成、42 次综合 Judge、39 次独立证据审计；输入 143616、输出 37945 Token。按 [DeepSeek 官方 Flash 价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)与报告内缓存命中数估算，低峰约 ¥0.22、高峰约 ¥0.44，实际账单可能不同。该价格快照对应 2026-10-31。

**建议保持当前线上 Hybrid，不自动启用重写。**这 40 题没有证据支持改动线上默认检索；一题留出集增益不足以覆盖所有查询的额外延迟。下一步优先改善同主题无答案时的证据边界判断，并用独立人工复审扩大留出集。

## 产物与复现

- `results.json`：三方案 40 题逐题命中、排名、分数和来源。
- `rewrite-cache.json`：40 次原始重写、校验结果、Token 与延迟。
- `evidence-results.json`：全量答案盲审，保留原始 Judge 输出。
- `generation-results.json`：14 题三方案的实际上下文、回答、引用与 Judge 原文。
- `comparison.json`、`metrics.md`、`optimization-report.md`、`failures.md`、`generation-failures.md`：离线汇总、配对比较与失败定位。

在项目根目录运行；`.env` 配置 `DEEPSEEK_API_KEY`，API Key 不写入结果文件。付费阶段必须显式带 `--allow-paid-api`：

```powershell
uv run --frozen python scripts/evaluate_three_way_rag.py --allow-paid-api
uv run --frozen python scripts/audit_three_way_evidence.py --allow-paid-api
uv run --frozen python scripts/evaluate_three_way_generation.py --allow-paid-api --judge
uv run --frozen python scripts/report_three_way_rag.py
```

已有完整检索结果时，第一条可加 `--resume` 直接复用；重写、证据和生成阶段都逐题缓存成功结果，不自动重试错误结果。最后一条纯离线，不调用 API。如需对全部 40 题生成，应在新的实验目录重新建立结果并显式使用 `--all`，不能在现有 14 题缓存中混用。
