# RAG evaluation

Dataset: `ordercare-rag-v1.0`; K=2.

Retrieval metrics use source + section labels; generation metrics are separate.
Empty-context relevance is 0; no-answer queries are excluded from Recall/MRR/nDCG.

| Method / split | Recall | MRR | nDCG | Context relevance | No-answer rejection | P95 ms | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid / all | 0.3667 | 0.4000 | 0.3858 | 0.3000 | 0.8000 | 9.6033 | 0 |
| hybrid / dev | 0.3667 | 0.4000 | 0.3858 | 0.3000 | 0.8000 | 9.6033 | 0 |
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

- rag-003 [dev] 包裹还没到，我就想按七天无理由退款，现在该怎么办？ → 七天无理由退款; missing_supporting_sections
- rag-005 [dev] 名字刻在杯子上了，现在不喜欢了，七天内也不能退吗？ → (empty); answerable_question_rejected
- rag-007 [dev] 定做的东西本身就是坏的，是不是因为定制就完全不能售后？ → (empty); answerable_question_rejected
- rag-009 [dev] 发错货后我已经拿到退款，还能让店家再补一件吗？ → (empty); answerable_question_rejected
- rag-011 [dev] 东西退回去了，钱是收到退件立刻打回来还是要验货？ → (empty); answerable_question_rejected
- rag-013 [dev] 银行卡退款已经超过七个工作日，我该准备哪些信息请人工核查？ → (empty); answerable_question_rejected
- rag-015 [dev] 物流五六天不动弹了，客服会找谁问，多久去核实？ → (empty); answerable_question_rejected
- rag-023 [dev] 单位要报销，订单完成一个月还能补开票吗，要校验什么？ → (empty); answerable_question_rejected
- rag-027 [dev] 取消了订单，用掉的券还能回来吗，需要等多久？ → (empty); answerable_question_rejected
- rag-029 [dev] 我不想让你们保留账户资料，要走什么手续？能直接删吗？ → (empty); answerable_question_rejected
- rag-033 [dev] 订单完成一年后还可以申请电子发票吗？如果可以流程是什么？ → 发票服务; unsupported_question_returned_context

Failure reasons describe label mismatches, not an LLM-inferred root cause.
Generation null means not measured (never substituted with retrieval scores).
