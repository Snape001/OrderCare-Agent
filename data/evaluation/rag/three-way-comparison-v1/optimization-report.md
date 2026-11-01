# RAG 三方案实验报告

40题检索全部完成；生成层仅对三方案证据有变化的题及两个对照题成对评测。
生成样本：14题；每方案同一组题。

## 检索指标

# 三种 RAG 检索方案对比

| 方案 / 数据集 | Recall@2 | MRR@2 | nDCG@2 | 无答案空检索率 | 平均检索 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| dense / all | 0.8833 | 0.9000 | 0.8874 | 0.2000 | 16.9658 |
| dense / dev | 0.8667 | 0.9333 | 0.9050 | 0.2000 | 17.0239 |
| dense / test | 0.9000 | 0.8667 | 0.8699 | 0.2000 | 16.9078 |
| hybrid / all | 0.8833 | 0.8833 | 0.8751 | 0.2000 | 17.6317 |
| hybrid / dev | 0.8667 | 0.9000 | 0.8803 | 0.2000 | 17.7625 |
| hybrid / test | 0.9000 | 0.8667 | 0.8699 | 0.2000 | 17.5010 |
| rewrite_hybrid / all | 0.9167 | 0.9167 | 0.9085 | 0.2000 | 18.6445 |
| rewrite_hybrid / dev | 0.8667 | 0.9000 | 0.8803 | 0.2000 | 19.2841 |
| rewrite_hybrid / test | 0.9667 | 0.9333 | 0.9366 | 0.2000 | 18.0050 |

重写请求数：40；校验拒绝数：1；输入/输出 Token：4225/765。

证据充分性和生成指标须经单独的语义评审；未执行时记为 null。

## 生成与证据指标（有效样本均值）

### 独立证据充分性：全部40题

| 方案 / split | Evidence Sufficiency | 有效题数 |
| --- | ---: | ---: |
| dense / all | 0.6250 | 40/40 |
| dense / dev | 0.6000 | 20/20 |
| dense / test | 0.6500 | 20/20 |
| hybrid / all | 0.6250 | 40/40 |
| hybrid / dev | 0.6000 | 20/20 |
| hybrid / test | 0.6500 | 20/20 |
| rewrite_hybrid / all | 0.6500 | 40/40 |
| rewrite_hybrid / dev | 0.6000 | 20/20 |
| rewrite_hybrid / test | 0.7000 | 20/20 |

### 生成回答：成对14题

| 方案 / split | Correctness | Faithfulness | Citation | Abstention | Evidence sufficiency | 生成题数 / Judge有效题数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dense / all | 0.9545 (11) | 0.9643 (7) | 1.0000 (11) | 1.0000 (12) | 0.6429 (14) | 14 / 12 |
| dense / dev | 1.0000 (8) | 1.0000 (6) | 1.0000 (8) | 1.0000 (8) | 0.7778 (9) | 9 / 8 |
| dense / test | 0.8333 (3) | 0.7500 (1) | 1.0000 (3) | 1.0000 (4) | 0.4000 (5) | 5 / 4 |
| hybrid / all | 1.0000 (9) | 1.0000 (4) | 1.0000 (6) | 1.0000 (12) | 0.6429 (14) | 14 / 12 |
| hybrid / dev | 1.0000 (8) | 1.0000 (4) | 1.0000 (5) | 1.0000 (8) | 0.7778 (9) | 9 / 8 |
| hybrid / test | 1.0000 (1) | null (0) | 1.0000 (1) | 1.0000 (4) | 0.4000 (5) | 5 / 4 |
| rewrite_hybrid / all | 1.0000 (9) | 1.0000 (6) | 1.0000 (8) | 1.0000 (13) | 0.7143 (14) | 14 / 13 |
| rewrite_hybrid / dev | 1.0000 (7) | 1.0000 (5) | 1.0000 (6) | 1.0000 (8) | 0.7778 (9) | 9 / 8 |
| rewrite_hybrid / test | 1.0000 (2) | 1.0000 (1) | 1.0000 (2) | 1.0000 (5) | 0.6000 (5) | 5 / 5 |

无答案题的**生成拒答准确率**单独统计；14题样本中共有4道无答案题，Judge无效的题不计入分母：

| 方案 | 拒答准确率 | 有效/无答案样本 |
| --- | ---: | ---: |
| dense | 1.0000 | 2/4 |
| hybrid | 1.0000 | 2/4 |
| rewrite_hybrid | 1.0000 | 3/4 |

## 成对比较（右方案减左方案）

### dense_vs_hybrid

| split | 指标 | 配对N | 左 | 右 | 差值 |
| --- | --- | ---: | ---: | ---: | ---: |
| all | answer_correctness | 9 | 1.0000 | 1.0000 | 0.0000 |
| all | faithfulness | 4 | 1.0000 | 1.0000 | 0.0000 |
| all | citation_support_rate | 6 | 1.0000 | 1.0000 | 0.0000 |
| all | abstention_accuracy | 12 | 1.0000 | 1.0000 | 0.0000 |
| all | evidence_sufficiency | 14 | 0.6429 | 0.6429 | 0.0000 |
| all | fact_evidence_coverage | 10 | 0.9000 | 0.9000 | 0.0000 |
| dev | answer_correctness | 8 | 1.0000 | 1.0000 | 0.0000 |
| dev | faithfulness | 4 | 1.0000 | 1.0000 | 0.0000 |
| dev | citation_support_rate | 5 | 1.0000 | 1.0000 | 0.0000 |
| dev | abstention_accuracy | 8 | 1.0000 | 1.0000 | 0.0000 |
| dev | evidence_sufficiency | 9 | 0.7778 | 0.7778 | 0.0000 |
| dev | fact_evidence_coverage | 7 | 1.0000 | 1.0000 | 0.0000 |
| test | answer_correctness | 1 | 1.0000 | 1.0000 | 0.0000 |
| test | faithfulness | 0 | null | null | null |
| test | citation_support_rate | 1 | 1.0000 | 1.0000 | 0.0000 |
| test | abstention_accuracy | 4 | 1.0000 | 1.0000 | 0.0000 |
| test | evidence_sufficiency | 5 | 0.4000 | 0.4000 | 0.0000 |
| test | fact_evidence_coverage | 3 | 0.6667 | 0.6667 | 0.0000 |

### hybrid_vs_rewrite_hybrid

| split | 指标 | 配对N | 左 | 右 | 差值 |
| --- | --- | ---: | ---: | ---: | ---: |
| all | answer_correctness | 7 | 1.0000 | 1.0000 | 0.0000 |
| all | faithfulness | 4 | 1.0000 | 1.0000 | 0.0000 |
| all | citation_support_rate | 5 | 1.0000 | 1.0000 | 0.0000 |
| all | abstention_accuracy | 12 | 1.0000 | 1.0000 | 0.0000 |
| all | evidence_sufficiency | 14 | 0.6429 | 0.7143 | 0.0714 |
| all | fact_evidence_coverage | 10 | 0.9000 | 1.0000 | 0.1000 |
| dev | answer_correctness | 7 | 1.0000 | 1.0000 | 0.0000 |
| dev | faithfulness | 4 | 1.0000 | 1.0000 | 0.0000 |
| dev | citation_support_rate | 5 | 1.0000 | 1.0000 | 0.0000 |
| dev | abstention_accuracy | 8 | 1.0000 | 1.0000 | 0.0000 |
| dev | evidence_sufficiency | 9 | 0.7778 | 0.7778 | 0.0000 |
| dev | fact_evidence_coverage | 7 | 1.0000 | 1.0000 | 0.0000 |
| test | answer_correctness | 0 | null | null | null |
| test | faithfulness | 0 | null | null | null |
| test | citation_support_rate | 0 | null | null | null |
| test | abstention_accuracy | 4 | 1.0000 | 1.0000 | 0.0000 |
| test | evidence_sufficiency | 5 | 0.4000 | 0.6000 | 0.2000 |
| test | fact_evidence_coverage | 3 | 0.6667 | 1.0000 | 0.3333 |

## API、延迟与限制

DeepSeek 请求 163 次；输入 143616、输出 37945 Token，其中缓存命中输入 76416。
按官方当前 Flash 价估算，低峰约 ¥0.220508，高峰约 ¥0.441017；非实际账单。
仅 Query Rewrite：40次，均值 677.3 ms，输入/输出 4225/765 Token，低峰估算 ¥0.007285。
各阶段请求/Token/费用估算见 `comparison.json` 的 `api_usage_by_phase`。

| 方案 | 40题检索总 ms | 14题生成总 ms | 14题 Judge总 ms |
| --- | ---: | ---: | ---: |
| dense | 678.6 | 15951.2 | 38527.3 |
| hybrid | 705.3 | 18728.5 | 40114.0 |
| rewrite_hybrid | 745.8 | 17273.6 | 38769.3 |

重写总耗时单列，未计入本地检索耗时。逐题延迟和 Token 见 JSON。
改写校验只能捕捉显式数字、实体词和否定漂移，不能证明语义完全一致。
同模型 Judge 是估计，格式或原文锚点不可靠时保留 null。
生成只覆盖14题，不能将样本均值称为40题整体答案质量。

## 结论与推荐

- **Hybrid 对 Direct：**40题 Recall@2 均为0.8833；Dense 的 MRR@2=0.9000、nDCG@2=0.8874，Hybrid 分别为0.8833、0.8751。11题的 Top-2 顺序或章节不同，但总体无检索收益。同组14题的有效生成评分没有显示 Hybrid 优势。当前数据不支持声称混合检索优于直接向量检索。
- **Rewrite 对 Hybrid：**40题 Recall@2 由0.8833到0.9167；留出集由0.9000到0.9667，仅 rag-016 从未命中变为完整命中。该题独立证据充分性由0到1，但 Hybrid 对该题的答案评分经严格复审为 null，不能声称整体回答正确率上升。开发集三个检索指标均未改善。全部40题独立证据充分性由0.625到0.650，留出集由0.650到0.700，均为单题增益。
- **代价与决策：**重写额外约677 ms/题，远高于约18 ms的本地检索；40次请求仅改变一题的召回。当前不启用线上 Query Rewrite，保留实验开关。优先解决同主题无答案题的证据充分性与拒答：三方案无答案空检索率均仅0.20。
- **完整性：**工作区政策 SHA 与 v1 标签不符，仅顶层标题变更；实验保存并校验 Git 冻结版本，逐节证明当前16个索引章节与冻结版本完全相同。未修改 Ground Truth、线上策略或政策文件。

