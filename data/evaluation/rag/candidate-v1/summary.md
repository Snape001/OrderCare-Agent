# RAG evaluation

Dataset: `ordercare-rag-v1.0`; K=2.

Retrieval metrics use source + section labels; generation metrics are separate.
Empty-context relevance is 0; no-answer queries are excluded from Recall/MRR/nDCG.

| Method / split | Recall | MRR | nDCG | Context relevance | No-answer rejection | P95 ms | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| hybrid / all | 0.9167 | 0.9333 | 0.9208 | 0.3833 | 0.2000 | 8.8726 | 0 |
| hybrid / dev | 0.9333 | 1.0000 | 0.9716 | 0.3750 | 0.2000 | 9.0401 | 0 |
| hybrid / test | 0.9000 | 0.8667 | 0.8699 | 0.3917 | 0.2000 | 8.7146 | 0 |

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
- rag-002 [test] 七天的期限从下单、发货还是收货那天开始算？ → 物流时效与轨迹, 七天无理由退款; irrelevant_top1, irrelevant_context
- rag-003 [dev] 包裹还没到，我就想按七天无理由退款，现在该怎么办？ → 七天无理由退款, 特殊商品退换限制; missing_supporting_sections, irrelevant_context
- rag-004 [test] 普通商品用了之后已经影响再次出售，还能无理由退吗？ → 七天无理由退款, 特殊商品退换限制; irrelevant_context
- rag-005 [dev] 名字刻在杯子上了，现在不喜欢了，七天内也不能退吗？ → 特殊商品退换限制, 七天无理由退款; irrelevant_context
- rag-006 [test] 买的软件已经激活，贴身用品也拆封了，这两种都支持无理由退吗？ → 特殊商品退换限制, 七天无理由退款; irrelevant_context
- rag-007 [dev] 定做的东西本身就是坏的，是不是因为定制就完全不能售后？ → 特殊商品退换限制, 七天无理由退款; irrelevant_context
- rag-008 [test] 拆包发现外壳碎了还少一条线，需要什么时候提交什么材料？ → 换货与缺件补发, 七天无理由退款; irrelevant_context
- rag-009 [dev] 发错货后我已经拿到退款，还能让店家再补一件吗？ → 换货与缺件补发, 七天无理由退款; irrelevant_context
- rag-010 [test] 换货的新包裹还能沿用原来那个运单号查吗？ → 换货与缺件补发, 物流异常; irrelevant_context
- rag-011 [dev] 东西退回去了，钱是收到退件立刻打回来还是要验货？ → 退款到账时效, 换货与缺件补发; irrelevant_context
- rag-012 [test] 信用卡退的钱和平台余额退的钱，到账速度一样吗？ → 退款到账时效, 优惠券与促销; irrelevant_context
- rag-013 [dev] 银行卡退款已经超过七个工作日，我该准备哪些信息请人工核查？ → 退款到账时效, 支付与重复扣款; missing_supporting_sections, irrelevant_context
- rag-014 [test] 钱刚付完还没有开始拣货，我不买了能取消并退钱吗？ → 订单取消, 七天无理由退款; irrelevant_context
- rag-015 [dev] 物流五六天不动弹了，客服会找谁问，多久去核实？ → 物流异常, 客服升级与工单; irrelevant_context
- rag-016 [test] 页面写着已签收可我根本没拿到，你能保证直接退款吗？ → 七天无理由退款, 订单取消; missing_supporting_sections, irrelevant_top1, irrelevant_context
- rag-017 [dev] 预计周五送到就是保证周五能收到吧？偏远地区还要多等多久？ → 物流时效与轨迹, 物流异常; irrelevant_context
- rag-018 [test] 已经发出来的货想转寄到别的省，平台能直接改吗，费用谁说了算？ → 收货地址修改, 换货与缺件补发; irrelevant_context
- rag-019 [dev] 电子产品没摔没泡水自己坏了，有限保修通常多久，可以修吗？ → 商品保修, 特殊商品退换限制; irrelevant_context
- rag-021 [dev] 东西要寄去修，申请需要什么资料，到售后后多久初检？ → 维修申请与进度, 发票服务; irrelevant_context
- rag-022 [test] 如果检查出要收费，可以不问我直接维修扣钱吗？ → 商品保修, 维修申请与进度; irrelevant_top1, irrelevant_context
- rag-023 [dev] 单位要报销，订单完成一个月还能补开票吗，要校验什么？ → 发票服务, 物流异常; irrelevant_context
- rag-024 [test] 增值税专票已经开了，税号错了能直接改吗？退货后发票怎么办？ → 发票服务, 收货地址修改; irrelevant_context
- rag-025 [dev] 付款提示没成功，银行卡却扣了，我要不要再付一次？ → 支付与重复扣款, 退款到账时效; irrelevant_context
- rag-027 [dev] 取消了订单，用掉的券还能回来吗，需要等多久？ → 优惠券与促销, 订单取消; irrelevant_context
- rag-028 [test] 用了满减后又退掉部分商品，为什么退款金额不是原价？ → 优惠券与促销, 退款到账时效; irrelevant_context
- rag-029 [dev] 我不想让你们保留账户资料，要走什么手续？能直接删吗？ → 账户与隐私, 支付与重复扣款; irrelevant_context
- rag-030 [test] 物流工单一直没解决，重复提交能更快吗？目标响应时间是多少？ → 投诉与服务时效, 物流异常; missing_supporting_sections, irrelevant_context
- rag-031 [dev] 无理由退货的快递费具体由买家还是卖家承担？ → 七天无理由退款, 换货与缺件补发; unsupported_question_returned_context
- rag-032 [test] 请告诉我上海线下退货门店的详细地址和营业时间。 → 退款到账时效, 七天无理由退款; unsupported_question_returned_context
- rag-033 [dev] 订单完成一年后还可以申请电子发票吗？如果可以流程是什么？ → 发票服务, 七天无理由退款; unsupported_question_returned_context
- rag-034 [test] 会员每个月能领几张券？每张优惠券面额是多少？ → 优惠券与促销; unsupported_question_returned_context
- rag-035 [dev] 我的订单 ORD1001 今天下午具体几点送到？ → 物流时效与轨迹, 七天无理由退款; unsupported_question_returned_context
- rag-036 [test] 苹果手机换电池的维修报价是多少元？ → 维修申请与进度, 商品保修; unsupported_question_returned_context
- rag-037 [dev] 退到银行卡可以指定另外一个人的卡吗？银行会收多少手续费？ → 退款到账时效, 支付与重复扣款; unsupported_question_returned_context
- rag-038 [test] 保修期内给我免费提供备用机吗？借用最长多少天？ → 商品保修, 维修申请与进度; unsupported_question_returned_context

Failure reasons describe label mismatches, not an LLM-inferred root cause.
Generation null means not measured (never substituted with retrieval scores).
