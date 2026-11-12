# v5：50 题配对 RAG 挑战集

## 数据与复现

`data/evaluation/rag/dataset-v5.json` 保留 v4 的 40 题及其原顺序、标签，新增 `pair-21` 至 `pair-25` 的 10 道可答题。新增三组在 dev、两组在 test；每组的规范和口语问法共用 Gold 章节、证据原文和 Chunk ID。Gold 来自 v3 的五份此前未用于 v4 Gold 标注的政策。构建脚本是 `scripts/build_rag_v5.py`；已有版本文件不可覆盖。数据集记录 v3 语料和 v4 数据集 SHA-256，加载时检查章节、引用原文和实际 Chunk。

本组是**按检索表现筛选的挑战题**，并非无偏留出集。题目和 Gold 已在最终评测前固定；统计结果适用于本挑战集，不能推断线上平均提升。

在项目根目录运行：

```powershell
.venv\Scripts\python.exe scripts/evaluate_three_way_rag.py --cases data/evaluation/rag/dataset-v5.json --policy data/policies/v3 --output data/evaluation/rag/three-way-comparison-v5 --top-k 3 --rewrite-prompt policy-terms --allow-paid-api
```

该命令显式启用 DeepSeek 付费改写 API。三种方案使用同一 v3 语料、索引设置和 Top-3；v5 使用政策术语归一化改写提示词，并保留重写校验及失败回退。此轮 RRF 实验执行时，线上检索默认配置尚未改动。

## 本次实测

| 分组 / 方法 | Recall@3 | Precision@3 | MRR@3 | nDCG@3 |
| --- | ---: | ---: | ---: | ---: |
| 新增 10 题 / Dense | 0.5000 | 0.1667 | 0.3333 | 0.3762 |
| 新增 10 题 / Hybrid | 0.4000 | 0.1333 | 0.3000 | 0.3262 |
| 新增 10 题 / Rewrite + Hybrid | **0.8000** | **0.2667** | **0.4833** | **0.5655** |
| 全部 50 题 / Dense | 0.8400 | 0.2800 | 0.7033 | 0.7383 |
| 全部 50 题 / Hybrid | 0.8800 | 0.2933 | 0.6633 | 0.7188 |
| 全部 50 题 / Rewrite + Hybrid | 0.9600 | 0.3200 | 0.7167 | 0.7793 |

新增题的 Rewrite + Hybrid Recall@3 严格高于另两种方案。50 次改写 API 调用均成功，其中 5 次校验回退；输入 / 输出 Token 共 7140 / 796。逐题排名、有效改写与四项指标见 `data/evaluation/rag/three-way-comparison-v5/new10.md`；完整原始结果见同目录 `results.json`，汇总见 `metrics.md`。

## 重排实验

独立实验脚本 `scripts/evaluate_rerank_rag_v5.py` 使用同一 50 题、v3 语料与 BGE 向量模型。Dense 保持原有 Top-3，并逐题与上述历史结果核对。新 Hybrid 对原 Query 分别取 Dense Top-3 与正分 BM25 Top-3，按 Chunk ID 去重后，用固定版本的本地 `BAAI/bge-reranker-base` ONNX 模型按 Query、章节标题和 Chunk 正文打分，取最终 Top-3；不执行 RRF。Dense 候选继续使用 0.50 相关性阈值。Rewrite 分支重新调用 50 次 DeepSeek，沿用政策术语提示词和安全回退，有效改写 Query 同时用于两路召回及重排。

运行命令：

```powershell
.venv\Scripts\python.exe scripts/evaluate_rerank_rag_v5.py --allow-paid-api
```

首次下载的约 1.1 GB ONNX 权重缓存在 `data/models/bge-reranker-base/`，不进入 Git。实测结果保存在 `data/evaluation/rag/rerank-comparison-v5/` 的 `results.json`、`report.md` 和独立 `rewrite-cache.json`。报告区分模型下载、加载、预热、候选检索、重排、改写 API 与逐题端到端耗时。原三方案 RRF 结果保留在 `three-way-comparison-v5/`；实验完成后，默认 `search_policy` 已切换到本次改写与重排链路。

本次 50 题结果：

| 方法 | Recall@3 | Precision@3 | MRR@3 | nDCG@3 |
| --- | ---: | ---: | ---: | ---: |
| Dense | 0.8400 | 0.2800 | 0.7033 | 0.7383 |
| 重排 Hybrid | 0.9000 | 0.3000 | 0.7933 | 0.8209 |
| Rewrite + 重排 Hybrid | 0.9600 | 0.3200 | 0.8433 | 0.8736 |

本次 DeepSeek 50 次请求均成功，8 题安全校验回退；实际输入 / 输出 Token 为 8140 / 802。重排 Hybrid 候选检索与重排均值分别为 34.4 / 138.2 ms；Rewrite + 重排的逐题端到端均值为 1011.4 ms，P95 为 1332.6 ms。模型文件传输观察值约 128 秒，加载 1.84 秒，预热 16.4 ms。逐题胜负、分组指标和候选列表见新实验报告及 JSON。
