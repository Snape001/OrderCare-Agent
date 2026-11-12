# RAG 迭代总结

## 迭代记录

| 阶段 | 实验结果 | 遇到的问题与处理 |
| --- | --- | --- |
| v1：Dense 与 RRF Hybrid | 40 题、Recall@2 均为 0.8833；Dense 的 MRR@2/nDCG@2 略高。Rewrite 将 Recall@2 提至 0.9167，但平均增加约 677 ms/题。 | Hybrid 未稳定胜过向量，Rewrite 成本高且提升有限；保留离线比较，不直接切换线上。 |
| v2：扩展政策与问题集 | 结果显示 Hybrid Recall@2 从 0.7192 提至 0.7534；Rewrite 与 Hybrid 持平。 | 语料和评测分布变化导致指标与 v1 不可直接横比；因此后续固定语料哈希、Gold 证据和独立版本产物。 |
| v3：BM25 与配对集 | 36 份政策切为 71 个 Chunk，建立 40 题 Formal/Colloquial 配对集。Dense Recall@3 0.9062，Hybrid 0.8125，Rewrite + Hybrid 0.8438。 | BM25/RRF 并未提升该集表现；清理政策模板噪声、过滤不可检索章节，并校验 Gold Chunk。保留 Dense 作为必要基线。 |
| v4：挑战集与 MCP 在线验证 | 40 题上 Hybrid Recall@3 1.0000，Dense 0.9250；MCP 返回与同配置进程内 Hybrid 排名一致。 | 这是按检索表现筛选的挑战集，dev/test 不是无偏留出集；同时 Hybrid 的 MRR/nDCG 低于 Dense，不能据 Recall 单项宣称整体更优。 |
| v5：扩至 50 题，RRF 复测 | 50 题上 Dense / Hybrid / Rewrite + Hybrid 的 Recall@3 为 0.8400 / 0.8800 / 0.9600。 | BM25 候选与 RRF 的排序能力有限；Rewrite 对新加挑战题改善明显，但需要付出 API 时间与 Token。 |
| 当前版本：双路 Top-3 + Cross-Encoder 重排 | Dense / 重排 Hybrid / Rewrite + 重排 Hybrid：Recall@3 为 **0.8400 / 0.9000 / 0.9600**，MRR@3 为 **0.7033 / 0.7933 / 0.8433**，nDCG@3 为 **0.7383 / 0.8209 / 0.8736**。Precision@3 为 0.2800 / 0.3000 / 0.3200。 | 两路候选按 Chunk 去重后由 BGE reranker 排序，避免 RRF 排序缺陷。50 次 DeepSeek 改写成功，8 次校验回退，输入/输出 Token 8140/802；Rewrite + 重排平均约 1.01 秒/题。现已接入默认 `search_policy`。 |

## 当前版本与复现

最终候选使用 v3 的 36 份政策、71 个 Chunk 和 v5 的 50 题配对挑战集。Dense 仍为 BGE 向量 Top-3；Hybrid 分别取 Dense Top-3 与 BM25 正分 Top-3，合并去重后由固定版本的本地 BGE reranker 取最终 Top-3；Rewrite 分支先用 DeepSeek 改写并校验，再以有效 Query 执行相同混合召回和重排。

本数据集按既往检索表现筛选，所有提升仅说明在当前挑战集上的结果，不代表无偏泛化或实际线上收益。当前默认 `search_policy` 已启用同一检索链；改写失败或缺少 DeepSeek 配置时使用原问题继续检索。

- 最新逐题结果与耗时：[重排实验报告](../../data/evaluation/rag/rerank-comparison-v5/report.md)
- 原 RRF 对照及缓存：[v5 三方案结果](../../data/evaluation/rag/three-way-comparison-v5/metrics.md)
- 语料和数据集背景：[v5 评测说明](rag-v5.md)
