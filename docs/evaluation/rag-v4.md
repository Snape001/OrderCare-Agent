# v4：混合检索定向挑战集

## 数据集

使用 v3 的 36 份政策文件、71 个可检索 Chunk。`dataset-v4.json` 由 `scripts/build_rag_v4.py` 的 20 条证据优先意图生成，共 40 道可答题；每组 Formal/Colloquial 共享标准答案与同一个 Gold Chunk。dev/test 各 10 组，Gold 覆盖 20 份细分政策文件以及订单、退换货、物流、支付退款、保修维修、发票、促销、工单投诉和隐私业务域。

第一组包含“保修缺少凭证怎么处理？”，证据为 `warranty.md#保修起算与凭证` 中“缺少凭证时先核对订单，不直接承诺免费维修。”。题目在固定 Gold 后按检索表现筛选；这是**定向挑战集**，两个 split 都不是无偏留出集，不能据此推断线上流量中的总体提升。

## 在线检索口径

Dense、BM25 各取 Top-3；线上 `search_policy` 沿用现有 RRF 并返回 Top-3，不接入重排或查询扩展。实验用 `ORDERCARE_EVAL_POLICY_PATH` 和 `ORDERCARE_EVAL_CHROMA_PATH` 仅在隔离的 STDIO MCP 子进程中指定 v3 与独立索引；不设置时服务继续使用原默认语料。Dense 对照与 MCP 服务采用同样的索引、阈值及语料；每题先验证 MCP 排名与进程内 Hybrid 排名一致。

执行 `uv run --frozen python scripts/evaluate_online_rag_v4.py`。逐题 JSON 与分组报告保存在 `data/evaluation/rag/online-comparison-v4/`。比较 Recall@3、Precision@3、MRR@3 和 nDCG@3；单题仅有一个 Gold 章节，因此命中时 Recall 为 1、Precision 为 1/3。另分开记录索引、预热、进程内检索和 MCP 往返耗时，后者包含传输开销。

## 本轮结果

| 分组 | Dense Recall@3 / Precision@3 | Hybrid Recall@3 / Precision@3 |
| --- | ---: | ---: |
| 全部 40 题 | 0.9250 / 0.3083 | 1.0000 / 0.3333 |
| dev 20 题 | 0.8500 / 0.2833 | 1.0000 / 0.3333 |
| test 20 题 | 1.0000 / 0.3333 | 1.0000 / 0.3333 |

逐题 Hybrid 胜 3、负 0、平 37。此次不调用 DeepSeek、不做生成评审，API Token 为 0。详细排名、MRR、nDCG、延迟与失败案例见 `online-comparison-v4/report.md` 和 `results.json`。

排序质量并未全面胜出：全部题的 MRR@3 为 Dense 0.7958、Hybrid 0.7542，nDCG@3 为 Dense 0.8289、Hybrid 0.8170。预热后的进程内检索均值分别约 26.2 ms、27.2 ms，MCP 往返均值约 32.9 ms。挑战集上 Recall/Precision 的优势不能概括为所有检索指标都更好。
