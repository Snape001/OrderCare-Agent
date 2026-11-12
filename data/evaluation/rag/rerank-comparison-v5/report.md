# v5 50 题：Dense 与重排检索

| 分组 | 方法 | Recall@3 | Precision@3 | MRR@3 | nDCG@3 |
| --- | --- | ---: | ---: | ---: | ---: |
| all | dense | 0.8400 | 0.2800 | 0.7033 | 0.7383 |
| dev | dense | 0.7692 | 0.2564 | 0.6218 | 0.6589 |
| test | dense | 0.9167 | 0.3056 | 0.7917 | 0.8244 |
| style:colloquial | dense | 0.7600 | 0.2533 | 0.5533 | 0.6062 |
| style:formal | dense | 0.9200 | 0.3067 | 0.8533 | 0.8705 |
| new10 | dense | 0.5000 | 0.1667 | 0.3333 | 0.3762 |
| all | rerank_hybrid | 0.9000 | 0.3000 | 0.7933 | 0.8209 |
| dev | rerank_hybrid | 0.8846 | 0.2949 | 0.7372 | 0.7752 |
| test | rerank_hybrid | 0.9167 | 0.3056 | 0.8542 | 0.8705 |
| style:colloquial | rerank_hybrid | 0.8000 | 0.2667 | 0.6933 | 0.7209 |
| style:formal | rerank_hybrid | 1.0000 | 0.3333 | 0.8933 | 0.9209 |
| new10 | rerank_hybrid | 0.6000 | 0.2000 | 0.5000 | 0.5262 |
| all | rewrite_rerank_hybrid | 0.9600 | 0.3200 | 0.8433 | 0.8736 |
| dev | rewrite_rerank_hybrid | 0.9615 | 0.3205 | 0.7949 | 0.8379 |
| test | rewrite_rerank_hybrid | 0.9583 | 0.3194 | 0.8958 | 0.9122 |
| style:colloquial | rewrite_rerank_hybrid | 0.9200 | 0.3067 | 0.7533 | 0.7967 |
| style:formal | rewrite_rerank_hybrid | 1.0000 | 0.3333 | 0.9333 | 0.9505 |
| new10 | rewrite_rerank_hybrid | 0.9000 | 0.3000 | 0.7000 | 0.7524 |

## 耗时与 Token

- index_build: 1965.6 ms
- model_prefetch_transfer_observed: 128372.0 ms
- model_download_and_file_lookup: 722.0 ms
- model_load: 1842.7 ms
- model_hash_and_initialization_total: 4926.6 ms
- model_warmup: 16.4 ms
- dense_retrieval: 总计 1205.0 ms，均值 24.1 ms，P95 36.3 ms
- hybrid_candidate_retrieval: 总计 1722.0 ms，均值 34.4 ms，P95 47.1 ms
- hybrid_rerank: 总计 6909.7 ms，均值 138.2 ms，P95 198.9 ms
- hybrid_end_to_end: 总计 8632.5 ms，均值 172.6 ms，P95 241.2 ms
- rewrite_api: 总计 41795.8 ms，均值 835.9 ms，P95 1130.8 ms
- rewrite_candidate_retrieval: 总计 1846.2 ms，均值 36.9 ms，P95 51.9 ms
- rewrite_rerank: 总计 6926.4 ms，均值 138.5 ms，P95 201.2 ms
- rewrite_end_to_end: 总计 50570.4 ms，均值 1011.4 ms，P95 1332.6 ms
- DeepSeek 请求：50，成功 50，失败 0，校验回退 8
- 实际 API 输入/输出 Token：8140/802；用量完整：True；缺失：[]
- Dense 与本地重排 API Token：0。模型下载与加载为一次性开销；逐题端到端包含改写 API、候选检索和重排。

## 逐题胜负（Recall@3）

- rerank_hybrid: 胜 4，负 1，平 45
- rewrite_rerank_hybrid: 胜 7，负 1，平 42

| 题目 | Dense Recall | 重排 Hybrid Recall / 胜负 | Rewrite + 重排 Recall / 胜负 |
| --- | ---: | --- | --- |
| pair-01-formal | 0.0 | 1.0 / win | 1.0 / win |
| pair-01-colloquial | 0.0 | 1.0 / win | 1.0 / win |
| pair-02-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-02-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-03-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-03-colloquial | 0.0 | 1.0 / win | 1.0 / win |
| pair-04-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-04-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-05-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-05-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-06-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-06-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-07-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-07-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-08-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-08-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-09-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-09-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-10-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-10-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-11-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-11-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-12-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-12-colloquial | 1.0 | 0.0 / loss | 0.0 / loss |
| pair-13-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-13-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-14-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-14-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-15-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-15-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-16-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-16-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-17-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-17-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-18-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-18-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-19-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-19-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-20-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-20-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-21-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-21-colloquial | 0.0 | 0.0 / tie | 0.0 / tie |
| pair-22-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-22-colloquial | 0.0 | 0.0 / tie | 1.0 / win |
| pair-23-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-23-colloquial | 0.0 | 0.0 / tie | 1.0 / win |
| pair-24-formal | 0.0 | 1.0 / win | 1.0 / win |
| pair-24-colloquial | 0.0 | 0.0 / tie | 1.0 / win |
| pair-25-formal | 1.0 | 1.0 / tie | 1.0 / tie |
| pair-25-colloquial | 1.0 | 1.0 / tie | 1.0 / tie |

本数据集按既往检索表现筛选；dev/test 仅供分组分析，不能视为无偏留出集。
逐题候选、排名、命中和改写记录见 results.json。
