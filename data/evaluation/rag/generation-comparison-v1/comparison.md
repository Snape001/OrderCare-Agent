# 生成 Baseline / Candidate 对比

检索结果冻结复用；延迟为第一阶段实测回放，未重新计时。以下生成指标仅在双方都有效的同一批样本上计算差值。

| Split | 指标 | Baseline | Candidate | 差值 | 配对 N |
| --- | --- | ---: | ---: | ---: | ---: |
| all | answer_correctness | 1.0000 | 1.0000 | 0.0000 | 16 |
| all | faithfulness | 1.0000 | 1.0000 | 0.0000 | 4 |
| all | citation_support_rate | 1.0000 | 1.0000 | 0.0000 | 2 |
| all | abstention_accuracy | 1.0000 | 1.0000 | 0.0000 | 25 |
| all | evidence_sufficiency | 0.6389 | 0.6389 | 0.0000 | 36 |
| all | fact_evidence_coverage | 0.9295 | 0.9295 | 0.0000 | 26 |
| all | evidence_abstention_accuracy | 0.9091 | 0.9091 | 0.0000 | 22 |
| all | recall@2 | 0.8833 | 0.8833 | 0.0000 | 可答题 |
| all | mrr@2 | 0.8833 | 0.8833 | 0.0000 | 可答题 |
| all | ndcg@2 | 0.8751 | 0.8751 | 0.0000 | 可答题 |
| all | context_relevance@2 | 0.3708 | 0.3708 | 0.0000 | 可答题 |
| all | generation_latency_ms | 11123.9548 | 15904.6778 | 4780.7230 | 全部调用 |
| all | judge_latency_ms | 8864.9566 | 9342.6178 | 477.6612 | 全部调用 |
| all | retrieval_p95_ms (replayed) | 8.9372 | 8.9372 | 0 | 回放 |
| all | generation_input_tokens | 39592 | 34673 | -4919 | 总计 |
| all | generation_output_tokens | 27934 | 41243 | 13309 | 总计 |
| all | generation_total_tokens | 67526 | 75916 | 8390 | 总计 |
| all | judge_input_tokens | 33719 | 29737 | -3982 | 总计 |
| all | judge_output_tokens | 21901 | 20378 | -1523 | 总计 |
| all | judge_total_tokens | 55620 | 50115 | -5505 | 总计 |
| dev | answer_correctness | 1.0000 | 1.0000 | 0.0000 | 9 |
| dev | faithfulness | 1.0000 | 1.0000 | 0.0000 | 3 |
| dev | citation_support_rate | 1.0000 | 1.0000 | 0.0000 | 1 |
| dev | abstention_accuracy | 1.0000 | 1.0000 | 0.0000 | 11 |
| dev | evidence_sufficiency | 0.6316 | 0.6316 | 0.0000 | 19 |
| dev | fact_evidence_coverage | 0.8929 | 0.8929 | 0.0000 | 14 |
| dev | evidence_abstention_accuracy | 0.9000 | 0.9000 | 0.0000 | 10 |
| dev | recall@2 | 0.8667 | 0.8667 | 0.0000 | 可答题 |
| dev | mrr@2 | 0.9000 | 0.9000 | 0.0000 | 可答题 |
| dev | ndcg@2 | 0.8803 | 0.8803 | 0.0000 | 可答题 |
| dev | context_relevance@2 | 0.3500 | 0.3500 | 0.0000 | 可答题 |
| dev | generation_latency_ms | 12406.3307 | 17522.9861 | 5116.6555 | 全部调用 |
| dev | judge_latency_ms | 9560.7769 | 9907.8281 | 347.0512 | 全部调用 |
| dev | retrieval_p95_ms (replayed) | 8.9183 | 8.9183 | 0 | 回放 |
| dev | generation_input_tokens | 20004 | 17457 | -2547 | 总计 |
| dev | generation_output_tokens | 15444 | 22560 | 7116 | 总计 |
| dev | generation_total_tokens | 35448 | 40017 | 4569 | 总计 |
| dev | judge_input_tokens | 17085 | 13686 | -3399 | 总计 |
| dev | judge_output_tokens | 11859 | 9843 | -2016 | 总计 |
| dev | judge_total_tokens | 28944 | 23529 | -5415 | 总计 |
| test | answer_correctness | 1.0000 | 1.0000 | 0.0000 | 7 |
| test | faithfulness | 1.0000 | 1.0000 | 0.0000 | 1 |
| test | citation_support_rate | 1.0000 | 1.0000 | 0.0000 | 1 |
| test | abstention_accuracy | 1.0000 | 1.0000 | 0.0000 | 14 |
| test | evidence_sufficiency | 0.6471 | 0.6471 | 0.0000 | 17 |
| test | fact_evidence_coverage | 0.9722 | 0.9722 | 0.0000 | 12 |
| test | evidence_abstention_accuracy | 0.9167 | 0.9167 | 0.0000 | 12 |
| test | recall@2 | 0.9000 | 0.9000 | 0.0000 | 可答题 |
| test | mrr@2 | 0.8667 | 0.8667 | 0.0000 | 可答题 |
| test | ndcg@2 | 0.8699 | 0.8699 | 0.0000 | 可答题 |
| test | context_relevance@2 | 0.3917 | 0.3917 | 0.0000 | 可答题 |
| test | generation_latency_ms | 9841.5788 | 14286.3694 | 4444.7905 | 全部调用 |
| test | judge_latency_ms | 8169.1363 | 8866.6512 | 697.5149 | 全部调用 |
| test | retrieval_p95_ms (replayed) | 8.9372 | 8.9372 | 0 | 回放 |
| test | generation_input_tokens | 19588 | 17216 | -2372 | 总计 |
| test | generation_output_tokens | 12490 | 18683 | 6193 | 总计 |
| test | generation_total_tokens | 32078 | 35899 | 3821 | 总计 |
| test | judge_input_tokens | 16634 | 16051 | -583 | 总计 |
| test | judge_output_tokens | 10042 | 10535 | 493 | 总计 |
| test | judge_total_tokens | 26676 | 26586 | -90 | 总计 |
