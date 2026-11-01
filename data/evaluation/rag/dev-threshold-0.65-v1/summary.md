# RAG evaluation

Dataset: `ordercare-rag-v1.0`; K=2.

Retrieval metrics use source + section labels; generation metrics are separate.
Empty-context relevance is 0; no-answer queries are excluded from Recall/MRR/nDCG.

| Method / split | Recall | MRR | nDCG | Context relevance | No-answer rejection | P95 ms | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid / all | 0.6667 | 0.7333 | 0.7050 | 0.4000 | 0.6000 | 9.0069 | 0 |
| hybrid / dev | 0.6667 | 0.7333 | 0.7050 | 0.4000 | 0.6000 | 9.0069 | 0 |
| hybrid / test | N/A | N/A | N/A | N/A | N/A | N/A | 0 |

## hybrid: generation / judge

```json
{
  "answer_correctness": null,
  "faithfulness": null,
  "citation_support_rate": null,
  "abstention_accuracy": null,
  "evaluated": 0,
  "errors": 0,
  "generation_latency_ms": null,
  "judge_latency_ms": null
}
```

## Failure diagnostics

- rag-001 [dev] 普通耳机签收第二天拆了包装，配件都在也没损坏，能走无理由退货吗？ → 七天无理由退款, 特殊商品退换限制; irrelevant_context
- rag-003 [dev] 包裹还没到，我就想按七天无理由退款，现在该怎么办？ → 七天无理由退款, 特殊商品退换限制; missing_supporting_sections, irrelevant_context
- rag-005 [dev] 名字刻在杯子上了，现在不喜欢了，七天内也不能退吗？ → (empty); answerable_question_rejected
- rag-009 [dev] 发错货后我已经拿到退款，还能让店家再补一件吗？ → 换货与缺件补发, 七天无理由退款; irrelevant_context
- rag-011 [dev] 东西退回去了，钱是收到退件立刻打回来还是要验货？ → 换货与缺件补发; missing_supporting_sections, irrelevant_top1, irrelevant_context
- rag-013 [dev] 银行卡退款已经超过七个工作日，我该准备哪些信息请人工核查？ → 退款到账时效; missing_supporting_sections
- rag-019 [dev] 电子产品没摔没泡水自己坏了，有限保修通常多久，可以修吗？ → 商品保修, 特殊商品退换限制; irrelevant_context
- rag-021 [dev] 东西要寄去修，申请需要什么资料，到售后后多久初检？ → 维修申请与进度, 发票服务; irrelevant_context
- rag-023 [dev] 单位要报销，订单完成一个月还能补开票吗，要校验什么？ → (empty); answerable_question_rejected
- rag-027 [dev] 取消了订单，用掉的券还能回来吗，需要等多久？ → 优惠券与促销, 订单取消; irrelevant_context
- rag-029 [dev] 我不想让你们保留账户资料，要走什么手续？能直接删吗？ → (empty); answerable_question_rejected
- rag-033 [dev] 订单完成一年后还可以申请电子发票吗？如果可以流程是什么？ → 发票服务; unsupported_question_returned_context
- rag-035 [dev] 我的订单 ORD1001 今天下午具体几点送到？ → 物流时效与轨迹; unsupported_question_returned_context

Failure reasons describe label mismatches, not an LLM-inferred root cause.
Generation null means not measured (never substituted with retrieval scores).
