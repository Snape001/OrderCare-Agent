# 生成与证据评测结果

所有数值来自保存的真实模型调用；null 不计入均值，必须同时阅读有效样本数。
证据充分性使用独立、不可见模型答案的证据审计；Judge 抽取矛盾的对应指标设为 null。

| Split | 指标 | 均值 | 有效 N |
| --- | --- | ---: | ---: |
| all | answer_correctness | 1.0000 | 23 |
| all | faithfulness | 1.0000 | 11 |
| all | citation_support_rate | 0.7778 | 9 |
| all | abstention_accuracy | 1.0000 | 30 |
| all | evidence_sufficiency | 0.6389 | 36 |
| all | fact_evidence_coverage | 0.9295 | 26 |
| all | evidence_abstention_accuracy | 0.8846 | 26 |
| dev | answer_correctness | 1.0000 | 13 |
| dev | faithfulness | 1.0000 | 7 |
| dev | citation_support_rate | 1.0000 | 3 |
| dev | abstention_accuracy | 1.0000 | 15 |
| dev | evidence_sufficiency | 0.6316 | 19 |
| dev | fact_evidence_coverage | 0.8929 | 14 |
| dev | evidence_abstention_accuracy | 0.8571 | 14 |
| test | answer_correctness | 1.0000 | 10 |
| test | faithfulness | 1.0000 | 4 |
| test | citation_support_rate | 0.6667 | 6 |
| test | abstention_accuracy | 1.0000 | 15 |
| test | evidence_sufficiency | 0.6471 | 17 |
| test | fact_evidence_coverage | 0.9722 | 12 |
| test | evidence_abstention_accuracy | 0.9167 | 12 |

## 逐题记录

### rag-001 / dev: 普通耳机签收第二天拆了包装，配件都在也没损坏，能走无理由退货吗？

预期：签收次日起7个自然日内可申请；商品完好、附件齐全且不影响二次销售；已拆封普通商品可提交审核

关键事实：签收次日起7个自然日内可申请；商品完好、附件齐全且不影响二次销售；已拆封普通商品可提交审核

召回：data/policies/customer_service_policy.md#七天无理由退款；data/policies/customer_service_policy.md#特殊商品退换限制

实际回答：

根据《七天无理由退款》政策（来源：data/policies/customer_service_policy.md），普通耳机在签收次日起7日内，若已拆封但不影响商品完好性且配件齐全，可提交无理由退货审核。您的情况符合政策条件，可申请。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-002 / test: 七天的期限从下单、发货还是收货那天开始算？

预期：自签收次日起计算7个自然日

关键事实：自签收次日起计算7个自然日

召回：data/policies/customer_service_policy.md#物流时效与轨迹；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

根据商城政策，七天无理由退款的期限自**签收次日起 7 个自然日**计算（标准商品需满足商品完好、附件齐全且不影响二次销售）。  
政策来源：`data/policies/customer_service_policy.md`（七天无理由退款章节）

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-003 / dev: 包裹还没到，我就想按七天无理由退款，现在该怎么办？

预期：运输中不能按已签收商品申请七天无理由；可尝试物流拦截，失败后签收再按退货政策处理

关键事实：运输中不能按已签收商品申请七天无理由；可尝试物流拦截，失败后签收再按退货政策处理

召回：data/policies/customer_service_policy.md#七天无理由退款；data/policies/customer_service_policy.md#特殊商品退换限制

实际回答：

根据政策，运输中的订单不能按已签收商品申请七天无理由退款。您需要先处理物流或取消订单。  
政策来源：data/policies/customer_service_policy.md（七天无理由退款）

缺失证据：["可尝试物流拦截，失败后签收再按退货政策处理"]

失败类型：Retrieval Miss、Abstention Failure

建议：检查候选池/多条件召回，在新盲测集验证有限补检索。；增强证据边界与部分拒答指令，勿由相似度推断可回答。

Judge 校验：Judge invented or paraphrased an answer claim; correctness/faithfulness unknown；Judge omitted or misparsed a visible source/section; citation support unknown；Judge citation claim absent from answer; citation support unknown

### rag-004 / test: 普通商品用了之后已经影响再次出售，还能无理由退吗？

预期：影响二次销售不支持无理由退款

关键事实：影响二次销售不支持无理由退款

召回：data/policies/customer_service_policy.md#七天无理由退款；data/policies/customer_service_policy.md#特殊商品退换限制

实际回答：

根据《七天无理由退款》政策（来源文件：data/policies/customer_service_policy.md），普通商品若已拆封且**影响二次销售**，则不支持无理由退款。  
（政策原文：标准商品自签收次日起7个自然日内，在商品完好、附件齐全且不影响二次销售的情况下，可以申请无理由退货。已拆封但不影响商品完好性的普通商品可提交审核；**影响二次销售时不支持无理由退款**。）

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge invented or paraphrased an answer claim; correctness/faithfulness unknown

### rag-005 / dev: 名字刻在杯子上了，现在不喜欢了，七天内也不能退吗？

预期：定制商品不适用七天无理由退货

关键事实：定制商品不适用七天无理由退货

召回：data/policies/customer_service_policy.md#七天无理由退款；data/policies/customer_service_policy.md#特殊商品退换限制

实际回答：

根据《特殊商品退换限制》政策（data/policies/customer_service_policy.md），定制商品（如刻字杯子）不适用七天无理由退货，因此七天内无法退款。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-006 / test: 买的软件已经激活，贴身用品也拆封了，这两种都支持无理由退吗？

预期：激活后的数字商品不适用七天无理由；拆封后影响健康安全的贴身用品不适用七天无理由

关键事实：激活后的数字商品不适用七天无理由；拆封后影响健康安全的贴身用品不适用七天无理由

召回：data/policies/customer_service_policy.md#特殊商品退换限制；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

已激活的软件和拆封的贴身用品均不支持七天无理由退货。根据《特殊商品退换限制》政策（数据政策/客户服务中心政策.md），下载或激活后的数字商品、拆封后影响健康安全的贴身用品不适用七天无理由退货。

缺失证据：["激活后的数字商品不适用七天无理由"]

失败类型：Citation Mismatch

建议：按事实绑定来源，拒绝不支持事实的引用。

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-007 / dev: 定做的东西本身就是坏的，是不是因为定制就完全不能售后？

预期：质量问题不受无理由退货范围限制；应提交故障照片、检测结果或其他证明走质量售后

关键事实：质量问题不受无理由退货范围限制；应提交故障照片、检测结果或其他证明走质量售后

召回：data/policies/customer_service_policy.md#特殊商品退换限制；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

根据商城政策，定制商品存在质量问题时**不受七天无理由退货限制**，可按质量售后流程处理（需提交故障照片、检测结果等证明）。  
政策来源：《特殊商品退换限制》（data/policies/customer_service_policy.md）

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge invented or paraphrased an answer claim; correctness/faithfulness unknown；Judge citation claim absent from answer; citation support unknown

### rag-008 / test: 拆包发现外壳碎了还少一条线，需要什么时候提交什么材料？

预期：签收后48小时内上传外包装、商品、快递面单照片；核验通过可换货或缺件补发

关键事实：签收后48小时内上传外包装、商品、快递面单照片；核验通过可换货或缺件补发

召回：data/policies/customer_service_policy.md#换货与缺件补发；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

根据《换货与缺件补发》政策（来源文件：data/policies/customer_service_policy.md），您需在签收后48小时内上传外包装、商品及快递面单照片。核验通过后可选择换货或缺件补发（同一问题已退款则不再重复处理）。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-009 / dev: 发错货后我已经拿到退款，还能让店家再补一件吗？

预期：同一问题已完成退款不再重复补发

关键事实：同一问题已完成退款不再重复补发

召回：data/policies/customer_service_policy.md#换货与缺件补发；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

根据《换货与缺件补发》政策（data/policies/customer_service_policy.md）：同一问题已经完成退款时，不再重复补发。因此您当前情况无法再要求店家补发商品。建议直接联系店家说明其他需求。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-010 / test: 换货的新包裹还能沿用原来那个运单号查吗？

预期：换货商品发出后生成新的物流单号

关键事实：换货商品发出后生成新的物流单号

召回：data/policies/customer_service_policy.md#换货与缺件补发；data/policies/customer_service_policy.md#物流异常

实际回答：

根据《换货与缺件补发》政策（data/policies/customer_service_policy.md），换货商品发出后会生成新的物流单号。因此换货的新包裹不能沿用原运单号查询。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-011 / dev: 东西退回去了，钱是收到退件立刻打回来还是要验货？

预期：仓库验收通过后发起原路退款

关键事实：仓库验收通过后发起原路退款

召回：data/policies/customer_service_policy.md#换货与缺件补发；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

根据换货与缺件补发政策（data/policies/customer_service_policy.md）：用户在退货时需上传外包装、商品和快递面单照片进行核验，核验通过后才能处理退款。因此，退款需要先完成验货，而非收到退件后立刻打回。

缺失证据：["仓库验收通过后发起原路退款"]

失败类型：Retrieval Miss、Abstention Failure

建议：检查候选池/多条件召回，在新盲测集验证有限补检索。；增强证据边界与部分拒答指令，勿由相似度推断可回答。

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-012 / test: 信用卡退的钱和平台余额退的钱，到账速度一样吗？

预期：银行卡和信用卡通常3至7个工作日；平台余额一般实时到账

关键事实：银行卡和信用卡通常3至7个工作日；平台余额一般实时到账

召回：data/policies/customer_service_policy.md#退款到账时效；data/policies/customer_service_policy.md#优惠券与促销

实际回答：

信用卡退款通常需要3至7个工作日，平台余额则实时到账，因此到账速度不同。  
根据《退款到账时效》政策（data/policies/customer_service_policy.md）

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-013 / dev: 银行卡退款已经超过七个工作日，我该准备哪些信息请人工核查？

预期：提供订单号和退款流水号创建退款异常工单；创建工单需用户明确确认

关键事实：提供订单号和退款流水号创建退款异常工单；创建工单需用户明确确认

召回：data/policies/customer_service_policy.md#退款到账时效；data/policies/customer_service_policy.md#支付与重复扣款

实际回答：

根据政策，银行卡退款超过7个工作日后，您需要准备订单号和退款流水号，以便创建退款异常工单。  
政策来源：退款到账时效（data/policies/customer_service_policy.md）

缺失证据：[]

失败类型：Retrieval Miss

建议：检查候选池/多条件召回，在新盲测集验证有限补检索。

Judge 校验：Judge citation claim absent from answer; citation support unknown

### rag-014 / test: 钱刚付完还没有开始拣货，我不买了能取消并退钱吗？

预期：已付款但尚未拣货可申请取消并原路退款

关键事实：已付款但尚未拣货可申请取消并原路退款

召回：data/policies/customer_service_policy.md#订单取消；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

您的订单处于已付款但未开始拣货的状态，可以申请取消并原路退款。政策依据：订单取消（data/policies/customer_service_policy.md，章节：订单取消）

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-015 / dev: 物流五六天不动弹了，客服会找谁问，多久去核实？

预期：超过5天没有新轨迹可创建物流异常工单；客服24小时内联系承运商核查

关键事实：超过5天没有新轨迹可创建物流异常工单；客服24小时内联系承运商核查

召回：data/policies/customer_service_policy.md#物流异常；data/policies/customer_service_policy.md#客服升级与工单

实际回答：

根据物流异常政策（来源：data/policies/customer_service_policy.md），当订单运输超过5天无新轨迹时，客服会联系承运商核查，且核查将在24小时内完成。当前物流问题需您先确认是否符合创建物流异常工单的条件（如超时未签收、疑似丢失等），系统将自动为您生成工单编号。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-016 / test: 页面写着已签收可我根本没拿到，你能保证直接退款吗？

预期：显示签收但本人未收到可创建物流异常工单；核查前不直接承诺退款结果

关键事实：显示签收但本人未收到可创建物流异常工单；核查前不直接承诺退款结果

召回：data/policies/customer_service_policy.md#七天无理由退款；data/policies/customer_service_policy.md#订单取消

实际回答：

根据商城政策，运输中的订单不能按已签收商品申请七天无理由退款（来源文件：data/policies/customer_service_policy.md，章节：七天无理由退款）。您的情况属于物流异常，建议立即联系物流客服处理拦截或申请订单取消，而非直接退款。当前页面显示的"已签收"状态需以实际物流信息为准。

缺失证据：["显示签收但本人未收到可创建物流异常工单", "核查前不直接承诺退款结果"]

失败类型：Retrieval Miss

建议：检查候选池/多条件召回，在新盲测集验证有限补检索。

Judge 校验：Judge invented or paraphrased an answer claim; correctness/faithfulness unknown；Judge citation claim absent from answer; citation support unknown

### rag-017 / dev: 预计周五送到就是保证周五能收到吧？偏远地区还要多等多久？

预期：预计送达时间不等于承诺到达时间；偏远地区可能增加2至3天

关键事实：预计送达时间不等于承诺到达时间；偏远地区可能增加2至3天

召回：data/policies/customer_service_policy.md#物流时效与轨迹；data/policies/customer_service_policy.md#物流异常

实际回答：

根据物流时效政策（来源：data/policies/customer_service_policy.md，章节"物流时效与轨迹"），普通快递预计3至5个自然日送达，偏远地区可能增加2至3天。**预计送达时间是参考时间，不等于承诺到达时间**，因此无法保证周五一定收到。建议通过订单详情查看实时物流轨迹以确认最新状态。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-018 / test: 已经发出来的货想转寄到别的省，平台能直接改吗，费用谁说了算？

预期：出库后平台不能直接修改；可联系承运商尝试转寄，费用和时效以承运商结果为准；跨省修改可能被拒绝

关键事实：出库后平台不能直接修改；可联系承运商尝试转寄，费用和时效以承运商结果为准；跨省修改可能被拒绝

召回：data/policies/customer_service_policy.md#收货地址修改；data/policies/customer_service_policy.md#换货与缺件补发

实际回答：

根据商城政策，订单已出库后平台无法直接修改收货地址。您需要联系承运商办理转寄服务，产生的费用和时效变化以承运商实际结果为准。跨省转寄可能被系统拒绝（政策来源：《收货地址修改》（data/policies/customer_service_policy.md））。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-019 / dev: 电子产品没摔没泡水自己坏了，有限保修通常多久，可以修吗？

预期：自签收起12个月有限保修，具体以商品页面和凭证为准；非人为性能故障可申请检测维修

关键事实：自签收起12个月有限保修，具体以商品页面和凭证为准；非人为性能故障可申请检测维修

召回：data/policies/customer_service_policy.md#商品保修；data/policies/customer_service_policy.md#特殊商品退换限制

实际回答：

根据《商品保修》政策（来源：data/policies/customer_service_policy.md）：电子产品自签收之日起享受12个月有限保修，非人为性能故障可申请检测维修。您描述的情况属于正常损耗范畴，符合保修条件，可正常申请维修服务。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-020 / test: 我不小心把水洒进键盘，又自己拆开了，还能免费修吗？

预期：进水和私自拆机不属于免费保修范围

关键事实：进水和私自拆机不属于免费保修范围

召回：data/policies/customer_service_policy.md#商品保修

实际回答：

根据商品保修政策（来源：data/policies/customer_service_policy.md），水洒进键盘属于"进水"，私自拆机属于"私自拆机"，均不属于免费保修范围。因此无法免费维修。建议联系客服处理。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge invented or paraphrased an answer claim; correctness/faithfulness unknown；Judge omitted or misparsed a visible source/section; citation support unknown

### rag-021 / dev: 东西要寄去修，申请需要什么资料，到售后后多久初检？

预期：需订单号、故障描述、设备序列号和必要图片或视频；售后中心收货后通常3个工作日内初检

关键事实：需订单号、故障描述、设备序列号和必要图片或视频；售后中心收货后通常3个工作日内初检

召回：data/policies/customer_service_policy.md#维修申请与进度；data/policies/customer_service_policy.md#发票服务

实际回答：

申请维修需提供订单号、故障描述、设备序列号及图片/视频。售后收货后通常3个工作日内完成初检（来源：维修申请与进度，data/policies/customer_service_policy.md）。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-022 / test: 如果检查出要收费，可以不问我直接维修扣钱吗？

预期：付费维修必须先展示报价并获得确认

关键事实：付费维修必须先展示报价并获得确认

召回：data/policies/customer_service_policy.md#商品保修；data/policies/customer_service_policy.md#维修申请与进度

实际回答：

根据商城政策，维修涉及收费时**必须先向用户展示报价并获得确认**，不可直接扣款。  
（来源文件：`data/policies/customer_service_policy.md`，章节：维修申请与进度）

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge invented or paraphrased an answer claim; correctness/faithfulness unknown；Judge omitted or misparsed a visible source/section; citation support unknown

### rag-023 / dev: 单位要报销，订单完成一个月还能补开票吗，要校验什么？

预期：订单完成45天内可申请电子普通发票或符合条件的专票；抬头和税号提交前须格式校验

关键事实：订单完成45天内可申请电子普通发票或符合条件的专票；抬头和税号提交前须格式校验

召回：data/policies/customer_service_policy.md#发票服务；data/policies/customer_service_policy.md#物流异常

实际回答：

根据发票服务政策，订单完成后45天内可申请补开电子普通发票或符合条件的增值税专用发票。补开时需校验发票抬头和税号格式（政策来源：data/policies/customer_service_policy.md，章节b4a94638ea412e68）。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-024 / test: 增值税专票已经开了，税号错了能直接改吗？退货后发票怎么办？

预期：已开专票不能直接修改，先红冲并经财务审核；退款后发票可能作废或红冲

关键事实：已开专票不能直接修改，先红冲并经财务审核；退款后发票可能作废或红冲

召回：data/policies/customer_service_policy.md#发票服务；data/policies/customer_service_policy.md#收货地址修改

实际回答：

根据政策，已开具的增值税专用发票税号错误无法直接修改，需先申请红冲并通过财务审核。退货后发票可能需要作废或红冲（来源：data/policies/customer_service_policy.md）。

缺失证据：[]

失败类型：Citation Mismatch

建议：按事实绑定来源，拒绝不支持事实的引用。

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-025 / dev: 付款提示没成功，银行卡却扣了，我要不要再付一次？

预期：不应重复支付，先等待支付渠道对账；通常1个工作日内恢复订单或原路退回

关键事实：不应重复支付，先等待支付渠道对账；通常1个工作日内恢复订单或原路退回

召回：data/policies/customer_service_policy.md#支付与重复扣款；data/policies/customer_service_policy.md#退款到账时效

实际回答：

根据支付与重复扣款政策（data/policies/customer_service_policy.md），支付失败但已扣款时无需重复支付。系统将在1个工作日内自动恢复订单或原路退回。若发现重复扣款，请保留两笔支付流水并创建工单（客服不需银行卡号/密码）。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-026 / test: 同一单扣了两次，要保留什么？客服能要我的支付密码吗？

预期：保留两笔支付流水并创建支付异常工单；客服不得索要支付密码或完整银行卡号

关键事实：保留两笔支付流水并创建支付异常工单；客服不得索要支付密码或完整银行卡号

召回：data/policies/customer_service_policy.md#支付与重复扣款；data/policies/customer_service_policy.md#账户与隐私

实际回答：

根据《支付与重复扣款》政策（data/policies/customer_service_policy.md），同一订单重复扣款时需保留两笔支付流水，客服**不可**索要支付密码。请勿向客服提供支付密码。

缺失证据：["保留两笔支付流水并创建支付异常工单", "客服不得索要支付密码或完整银行卡号"]

失败类型：未自动归因

建议：

Judge 校验：Judge invented or paraphrased an answer claim; correctness/faithfulness unknown；Judge citation claim absent from answer; citation support unknown

### rag-027 / dev: 取消了订单，用掉的券还能回来吗，需要等多久？

预期：未过期且未被活动规则排除的券通常24小时内退回

关键事实：未过期且未被活动规则排除的券通常24小时内退回

召回：data/policies/customer_service_policy.md#优惠券与促销；data/policies/customer_service_policy.md#订单取消

实际回答：

根据商城政策，订单取消后未过期且未被活动规则排除的优惠券通常会在 **24 小时内退回**。若因退款导致订单不再满足满减条件，退款金额会扣除相应优惠分摊。  
政策来源：优惠券与促销（data/policies/customer_service_policy.md）

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-028 / test: 用了满减后又退掉部分商品，为什么退款金额不是原价？

预期：因退款不再满足满减条件时扣除相应优惠分摊

关键事实：因退款不再满足满减条件时扣除相应优惠分摊

召回：data/policies/customer_service_policy.md#优惠券与促销；data/policies/customer_service_policy.md#退款到账时效

实际回答：

根据《优惠券与促销》政策（data/policies/customer_service_policy.md），当退款导致订单不再满足满减条件时，退款金额会扣除相应优惠分摊。因此您的退款金额不是原价。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-029 / dev: 我不想让你们保留账户资料，要走什么手续？能直接删吗？

预期：导出或删除账户信息需专门身份验证和隐私工单

关键事实：导出或删除账户信息需专门身份验证和隐私工单

召回：data/policies/customer_service_policy.md#账户与隐私；data/policies/customer_service_policy.md#支付与重复扣款

实际回答：

根据《账户与隐私》政策（data/policies/customer_service_policy.md），用户申请删除账户需通过身份验证并提交隐私工单，无法直接删除。请提供身份信息后，我们将为您创建工单处理。

缺失证据：[]

失败类型：未自动归因

建议：

Judge 校验：结构与锚点校验通过；不等于语义判定准确

### rag-030 / test: 物流工单一直没解决，重复提交能更快吗？目标响应时间是多少？

预期：物流异常工单目标响应时间12小时；应在原工单补充证据并申请升级，不应重复建单提高优先级；相同幂等键只创建一张工单

关键事实：物流异常工单目标响应时间12小时；应在原工单补充证据并申请升级，不应重复建单提高优先级；相同幂等键只创建一张工单

召回：data/policies/customer_service_policy.md#投诉与服务时效；data/policies/customer_service_policy.md#物流异常

实际回答：

根据《投诉与服务时效》政策（data/policies/customer_service_policy.md），物流异常工单目标响应时间为12小时。重复提交相同工单不会提高优先级，建议在原工单中补充证据申请升级处理。

缺失证据：["相同幂等键只创建一张工单"]

失败类型：Retrieval Miss、Abstention Failure

建议：检查候选池/多条件召回，在新盲测集验证有限补检索。；增强证据边界与部分拒答指令，勿由相似度推断可回答。

Judge 校验：Judge omitted or misparsed a visible source/section; citation support unknown

### rag-031 / dev: 无理由退货的快递费具体由买家还是卖家承担？

预期：知识库没有退货运费承担规则，不能自行判断，应转人工确认

关键事实：知识库没有退货运费承担规则，不能自行判断，应转人工确认

召回：data/policies/customer_service_policy.md#七天无理由退款；data/policies/customer_service_policy.md#换货与缺件补发

实际回答：

根据《七天无理由退款》政策（data/policies/customer_service_policy.md），当前政策文件中未明确说明无理由退货的快递费承担方。建议您提供订单号和手机号后四位，由人工客服协助查询具体规则。

缺失证据：["知识库没有退货运费承担规则，不能自行判断，应转人工确认"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-032 / test: 请告诉我上海线下退货门店的详细地址和营业时间。

预期：知识库没有线下退货门店地址或营业时间

关键事实：知识库没有线下退货门店地址或营业时间

召回：data/policies/customer_service_policy.md#退款到账时效；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

根据当前政策库，未找到上海线下退货门店的详细地址和营业时间信息。建议您直接联系上海线下退货门店客服或通过星河商城APP查询门店信息。

缺失证据：["知识库没有线下退货门店地址或营业时间"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-033 / dev: 订单完成一年后还可以申请电子发票吗？如果可以流程是什么？

预期：知识库仅规定45天内申请，没有一年后的申请流程，不能编造

关键事实：知识库仅规定45天内申请，没有一年后的申请流程，不能编造

召回：data/policies/customer_service_policy.md#发票服务；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

根据《发票服务》政策（data/policies/customer_service_policy.md），订单完成后45天内可申请电子普通发票。您的订单已超过45天，无法申请电子发票。若需开具发票，请在订单完成后45天内通过系统提交发票信息并完成格式校验。

缺失证据：["知识库仅规定45天内申请，没有一年后的申请流程，不能编造"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-034 / test: 会员每个月能领几张券？每张优惠券面额是多少？

预期：知识库没有会员领券数量或面额规则

关键事实：知识库没有会员领券数量或面额规则

召回：data/policies/customer_service_policy.md#优惠券与促销

实际回答：

根据《优惠券与促销》政策（data/policies/customer_service_policy.md），优惠券的具体领取数量和面额需以结算页活动规则为准，不同活动可能有差异。

缺失证据：["知识库没有会员领券数量或面额规则"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-035 / dev: 我的订单 ORD1001 今天下午具体几点送到？

预期：政策知识库不包含具体订单实时配送时间，需查询业务工具且不能保证具体时刻

关键事实：政策知识库不包含具体订单实时配送时间，需查询业务工具且不能保证具体时刻

召回：data/policies/customer_service_policy.md#物流时效与轨迹；data/policies/customer_service_policy.md#七天无理由退款

实际回答：

请提供手机号后四位，以便查询订单ORD1001的物流信息。

缺失证据：["政策知识库不包含具体订单实时配送时间，需查询业务工具且不能保证具体时刻"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-036 / test: 苹果手机换电池的维修报价是多少元？

预期：知识库没有具体维修价目表，需售后报价

关键事实：知识库没有具体维修价目表，需售后报价

召回：data/policies/customer_service_policy.md#维修申请与进度；data/policies/customer_service_policy.md#商品保修

实际回答：

根据《维修申请与进度》政策（data/policies/customer_service_policy.md），维修报价需在申请维修时由售后中心展示并确认。具体金额因设备型号和维修情况而异，建议提供订单号和设备信息以便进一步查询。

缺失证据：["知识库没有具体维修价目表，需售后报价"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-037 / dev: 退到银行卡可以指定另外一个人的卡吗？银行会收多少手续费？

预期：知识库只有原路退款与到账时效，没有指定他人银行卡流程或手续费数额

关键事实：知识库只有原路退款与到账时效，没有指定他人银行卡流程或手续费数额

召回：data/policies/customer_service_policy.md#退款到账时效；data/policies/customer_service_policy.md#支付与重复扣款

实际回答：

根据《退款到账时效》政策（data/policies/customer_service_policy.md），退货退款会原路退回至原支付账户，不支持指定他人银行卡。银行手续费由银行收取，具体金额请咨询发卡行。

缺失证据：["知识库只有原路退款与到账时效，没有指定他人银行卡流程或手续费数额"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-038 / test: 保修期内给我免费提供备用机吗？借用最长多少天？

预期：知识库没有备用机提供条件或借用时限

关键事实：知识库没有备用机提供条件或借用时限

召回：data/policies/customer_service_policy.md#商品保修；data/policies/customer_service_policy.md#维修申请与进度

实际回答：

根据《商品保修》政策（data/policies/customer_service_policy.md），电子产品自签收之日起享受12个月有限保修，但政策中未明确说明保修期内是否可免费提供备用机及借用天数。维修相关流程需提供订单号、故障描述等信息，具体可联系售后客服。

缺失证据：["知识库没有备用机提供条件或借用时限"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-039 / dev: 请推导快速排序平均时间复杂度并写一段代码。

预期：与商城客服知识库无关，应说明无法据此回答

关键事实：与商城客服知识库无关，应说明无法据此回答

召回：

实际回答：

抱歉，星河商城的智能客服不处理技术问题，建议您联系人工客服或使用其他平台获取帮助。需要我帮您创建工单吗？

缺失证据：["与商城客服知识库无关，应说明无法据此回答"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema

### rag-040 / test: 明天北京会下雨吗？帮我预测气温。

预期：知识库没有天气信息，不应编造天气

关键事实：知识库没有天气信息，不应编造天气

召回：

实际回答：

您好！我主要协助处理商城订单、退款、物流等服务问题。天气查询请使用天气类应用或联系当地气象部门。需要帮助时可随时告诉我。

缺失证据：["知识库没有天气信息，不应编造天气"]

失败类型：Missing Evidence

建议：补充经业务确认的知识或明确说明缺失；重复检索不能创造政策。

Judge 校验：Judge unavailable or invalid JSON/schema
