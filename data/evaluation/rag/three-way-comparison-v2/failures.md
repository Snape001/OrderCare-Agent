# 逐题检索差异与失败案例

## rag-001 / dev / 无理由退货
问题：普通耳机签收第二天拆了包装，配件都在也没损坏，能走无理由退货吗？
- dense: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['七天无理由退款', '换货后再次申请']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '换货后再次申请']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：普通耳机签收第二天拆了包装，配件都在也没损坏，能走无理由退货吗？；校验问题：[]

## rag-002 / dev / 无理由退货
问题：七天的期限从下单、发货还是收货那天开始算？
- dense: ['分批发货与签收状态', '物流时效与轨迹']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['分批发货与签收状态', '物流时效与轨迹']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['分批发货与签收状态', '物流时效与轨迹']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：七天期限从下单、发货还是收货当天开始计算？；校验问题：[]

## rag-003 / dev / 复杂条件
问题：包裹还没到，我就想按七天无理由退款，现在该怎么办？
- dense: ['七天无理由退款', '换货后再次申请']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['七天无理由退款', '换货后再次申请']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '换货后再次申请']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：包裹还没到，想按七天无理由退款，现在该怎么办？；校验问题：[]

## rag-004 / dev / 无理由退货
问题：普通商品用了之后已经影响再次出售，还能无理由退吗？
- dense: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '退货申请与审核材料']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：普通商品使用后已影响再次出售，还能无理由退货吗？；校验问题：[]

## rag-005 / test / 特殊商品
问题：名字刻在杯子上了，现在不喜欢了，七天内也不能退吗？
- dense: ['特殊商品退换限制', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：名字刻在杯子上了，现在不喜欢了，七天内也不能退吗？；校验问题：[]

## rag-006 / test / 特殊商品
问题：买的软件已经激活，贴身用品也拆封了，这两种都支持无理由退吗？
- dense: ['特殊商品退换限制', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['特殊商品退换限制', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['特殊商品退换限制', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：已激活的软件和已拆封的贴身用品是否都支持无理由退货？；校验问题：[]

## rag-007 / test / 质量售后
问题：定做的东西本身就是坏的，是不是因为定制就完全不能售后？
- dense: ['特殊商品退换限制', '质量问题退换路径']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['质量问题退换路径', '特殊商品退换限制']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['质量问题退换路径', '特殊商品退换限制']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：定做的商品本身是坏的，是不是因为定制就完全不能售后？；校验问题：[]

## rag-008 / test / 质量售后
问题：拆包发现外壳碎了还少一条线，需要什么时候提交什么材料？
- dense: ['破损包裹与证据', '补充证据与升级']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['破损包裹与证据', '补充证据与升级']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['破损包裹与证据', '补充证据与升级']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：拆包发现外壳碎了还少一条线，需要什么时候提交什么材料？；校验问题：[]

## rag-009 / test / 质量售后
问题：发错货后我已经拿到退款，还能让店家再补一件吗？
- dense: ['换货与缺件补发', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['换货与缺件补发', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['换货与缺件补发', '退换货与优惠分摊']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：发错货后已拿到退款，还能让店家再补一件吗？；校验问题：[]

## rag-010 / test / 质量售后
问题：换货的新包裹还能沿用原来那个运单号查吗？
- dense: ['多包裹与错投', '换货与缺件补发']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['多包裹与错投', '换货与缺件补发']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['多包裹与错投', '换货与缺件补发']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：换货的新包裹还能沿用原来的运单号查询吗？；校验问题：[]

## rag-011 / dev / 退款流程
问题：东西退回去了，钱是收到退件立刻打回来还是要验货？
- dense: ['换货与缺件补发', '代签与签收争议']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['换货与缺件补发', '代签与签收争议']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['换货与缺件补发', '代签与签收争议']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：东西退回去了，钱是收到退件立刻打回来还是要验货？；校验问题：[]

## rag-012 / dev / 退款流程
问题：信用卡退的钱和平台余额退的钱，到账速度一样吗？
- dense: ['退款到账时效', '退款发起与渠道时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['退款到账时效', '退款发起与渠道时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['退款发起与渠道时效', '退款到账时效']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：信用卡退款和平台余额退款的到账速度一样吗？；校验问题：[]

## rag-013 / dev / 复杂条件
问题：银行卡退款已经超过七个工作日，我该准备哪些信息请人工核查？
- dense: ['退款到账时效', '退款发起与渠道时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['退款到账时效', '退款发起与渠道时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['退款到账时效', '退款发起与渠道时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：银行卡退款已超过七个工作日，请人工核查需准备哪些信息？；校验问题：[]

## rag-014 / dev / 退款资格
问题：钱刚付完还没有开始拣货，我不买了能取消并退钱吗？
- dense: ['订单取消', '退换货与优惠分摊']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['订单取消', '退换货与优惠分摊']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['订单取消', '退换货与优惠分摊']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：钱刚付完还没有开始拣货，我不买了能取消并退钱吗？；校验问题：[]

## rag-015 / test / 物流异常
问题：物流五六天不动弹了，客服会找谁问，多久去核实？
- dense: ['物流异常', '延迟与无轨迹核查']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['物流异常', '延迟与无轨迹核查']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['物流异常', '延迟与无轨迹核查']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：物流五六天不动弹了，客服会找谁问，多久去核实？；校验问题：[]

## rag-016 / test / 物流异常
问题：页面写着已签收可我根本没拿到，你能保证直接退款吗？
- dense: ['退货申请与审核材料', '七天无理由退款']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['退货申请与审核材料', '七天无理由退款']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['代签与签收争议', '七天无理由退款']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：页面显示已签收但我没收到，能否保证直接退款？；校验问题：[]

## rag-017 / test / 物流时效
问题：预计周五送到就是保证周五能收到吧？偏远地区还要多等多久？
- dense: ['物流时效与轨迹', '延迟与无轨迹核查']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['物流时效与轨迹', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['物流时效与轨迹', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：预计周五送到是否保证周五能收到？偏远地区还要多等多久？；校验问题：[]

## rag-018 / test / 复杂条件
问题：已经发出来的货想转寄到别的省，平台能直接改吗，费用谁说了算？
- dense: ['收货地址修改', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['收货地址修改', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['收货地址修改', '退款发起与渠道时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：已发出的货想转寄到别的省，平台能直接改吗，费用谁说了算？；校验问题：[]

## rag-019 / dev / 保修
问题：电子产品没摔没泡水自己坏了，有限保修通常多久，可以修吗？
- dense: ['商品保修', '免费保修的例外']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['商品保修', '保修起算与凭证']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['商品保修', '保修起算与凭证']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：电子产品没摔没泡水自己坏了，有限保修通常多久，可以修吗？；校验问题：[]

## rag-020 / dev / 保修
问题：我不小心把水洒进键盘，又自己拆开了，还能免费修吗？
- dense: ['免费保修的例外', '商品保修']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['免费保修的例外', '商品保修']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['商品保修', '免费保修的例外']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：不小心把水洒进键盘，又自己拆开了，还能免费修吗？；校验问题：[]

## rag-021 / test / 维修
问题：东西要寄去修，申请需要什么资料，到售后后多久初检？
- dense: ['初检、报价与用户选择', '维修申请与进度']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['维修申请与进度', '初检、报价与用户选择']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['维修申请与进度', '初检、报价与用户选择']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：东西寄去修，申请需要什么资料，到售后后多久初检？；校验问题：[]

## rag-022 / test / 维修
问题：如果检查出要收费，可以不问我直接维修扣钱吗？
- dense: ['维修后同故障复检', '初检、报价与用户选择']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['维修后同故障复检', '保修起算与凭证']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['维修后同故障复检', '保修起算与凭证']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：如果检查出要收费，可以不问我直接维修扣钱吗？；校验问题：[]

## rag-023 / dev / 发票
问题：单位要报销，订单完成一个月还能补开票吗，要校验什么？
- dense: ['发票服务', '发票、红冲与退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['发票服务', '发票、红冲与退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['发票服务', '发票、红冲与退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：单位报销，订单完成一个月还能补开票吗，要校验什么？；校验问题：[]

## rag-024 / dev / 复杂条件
问题：增值税专票已经开了，税号错了能直接改吗？退货后发票怎么办？
- dense: ['发票、红冲与退款', '发票服务']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['发票、红冲与退款', '发票服务']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['发票、红冲与退款', '发票服务']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：增值税专票已开，税号错了能直接改吗？退货后发票怎么办？；校验问题：[]

## rag-025 / test / 支付
问题：付款提示没成功，银行卡却扣了，我要不要再付一次？
- dense: ['支付失败与重复扣款', '支付与重复扣款']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['支付失败与重复扣款', '支付与重复扣款']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['支付失败与重复扣款', '支付与重复扣款']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：付款提示未成功但银行卡已扣款，是否需要再次付款？；校验问题：['negation_added:未', 'negation_removed:不', 'negation_removed:没']

## rag-026 / test / 复杂条件
问题：同一单扣了两次，要保留什么？客服能要我的支付密码吗？
- dense: ['支付失败与重复扣款', '支付与重复扣款']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['支付与重复扣款', '支付失败与重复扣款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['支付与重复扣款', '支付失败与重复扣款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：同一单扣了两次，要保留什么？客服能要我的支付密码吗？；校验问题：[]

## rag-027 / dev / 优惠券
问题：取消了订单，用掉的券还能回来吗，需要等多久？
- dense: ['优惠券返还与门槛', '退换货与优惠分摊']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['优惠券与促销', '优惠券返还与门槛']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['优惠券与促销', '优惠券返还与门槛']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：取消了订单，用掉的券还能回来吗，需要等多久？；校验问题：[]

## rag-028 / dev / 优惠券
问题：用了满减后又退掉部分商品，为什么退款金额不是原价？
- dense: ['退换货与优惠分摊', '优惠券返还与门槛']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['退换货与优惠分摊', '优惠券返还与门槛']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['退换货与优惠分摊', '优惠券返还与门槛']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：使用满减后部分商品退货，退款金额为什么不是原价？；校验问题：[]

## rag-029 / dev / 隐私
问题：我不想让你们保留账户资料，要走什么手续？能直接删吗？
- dense: ['账户与隐私', '补充证据与升级']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['账户与隐私', '补充证据与升级']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['账户与隐私', '补充证据与升级']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：我不想让你们保留账户资料，要走什么手续？能直接删吗？；校验问题：[]

## rag-030 / dev / 复杂条件
问题：物流工单一直没解决，重复提交能更快吗？目标响应时间是多少？
- dense: ['投诉与服务时效', '工单类别与响应时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['投诉与服务时效', '工单类别与响应时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['投诉与服务时效', '工单类别与响应时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：物流工单一直没解决，重复提交能更快吗？目标响应时间是多少？；校验问题：[]

## rag-031 / dev / 库内缺失
问题：无理由退货的快递费具体由买家还是卖家承担？
- dense: ['退货申请与审核材料', '丢件核实后的选择']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['退货申请与审核材料', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['退货申请与审核材料', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：无理由退货的快递费具体由买家还是卖家承担？；校验问题：[]

## rag-032 / test / 库内缺失
问题：请告诉我上海线下退货门店的详细地址和营业时间。
- dense: ['退货申请与审核材料', '退款到账时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['退货申请与审核材料', '退款到账时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['退款发起与渠道时效', '退款到账时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：上海线下退货门店的详细地址和营业时间；校验问题：[]

## rag-033 / dev / 库内缺失
问题：订单完成一年后还可以申请电子发票吗？如果可以流程是什么？
- dense: ['发票服务', '发票、红冲与退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['发票服务', '发票、红冲与退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['发票服务', '发票、红冲与退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：订单完成一年后还可以申请电子发票吗？如果可以流程是什么？；校验问题：[]

## rag-034 / dev / 库内缺失
问题：会员每个月能领几张券？每张优惠券面额是多少？
- dense: ['优惠券与促销', '优惠券返还与门槛']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['优惠券与促销', '优惠券返还与门槛']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['优惠券与促销', '优惠券返还与门槛']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：会员每个月能领几张券？每张优惠券面额是多少？；校验问题：[]

## rag-035 / test / 动态事实
问题：我的订单 ORD1001 今天下午具体几点送到？
- dense: ['物流时效与轨迹', '延迟与无轨迹核查']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['物流时效与轨迹', '保修起算与凭证']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['物流时效与轨迹', '保修起算与凭证']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：我的订单 ORD1001 今天下午具体几点送到？；校验问题：[]

## rag-036 / test / 库内缺失
问题：苹果手机换电池的维修报价是多少元？
- dense: ['初检、报价与用户选择', '商品保修']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['初检、报价与用户选择', '商品保修']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['初检、报价与用户选择', '商品保修']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：苹果手机换电池维修报价多少元；校验问题：[]

## rag-037 / dev / 库内缺失
问题：退到银行卡可以指定另外一个人的卡吗？银行会收多少手续费？
- dense: ['退款到账时效', '退款发起与渠道时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['退款到账时效', '退款发起与渠道时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['退款到账时效', '退款发起与渠道时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：退款到银行卡可以指定另外一个人的卡吗？银行会收多少手续费？；校验问题：[]

## rag-038 / test / 库内缺失
问题：保修期内给我免费提供备用机吗？借用最长多少天？
- dense: ['商品保修', '保修起算与凭证']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['商品保修', '免费保修的例外']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['商品保修', '免费保修的例外']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：保修期内免费提供备用机吗？借用最长多少天？；校验问题：[]

## rag-041 / dev / returns
问题：耳机刚签收，包装拆了但配件都在，点了退货申请就算通过了吗？
- dense: ['七天无理由退款', '退货申请与审核材料']；Recall=1.0，MRR=1.0；失败标记=[]
- hybrid: ['退货申请与审核材料', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['退货申请与审核材料', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：耳机刚签收，包装已拆但配件都在，提交退货申请就算通过了吗？；校验问题：[]

## rag-042 / dev / returns
问题：货还在路上，我想先按收到货的七天退，能把期限从今天算吗？
- dense: ['分批发货与签收状态', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=[]
- hybrid: ['分批发货与签收状态', '换货后再次申请']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['分批发货与签收状态', '换货后再次申请']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：货还在路上，我想先按收到货的七天退，能把期限从今天算吗？；校验问题：[]

## rag-043 / dev / returns
问题：套装只想退里面一件，赠品我丢了，退款能按那件原价给吗？
- dense: ['套装、赠品与部分退货', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['套装、赠品与部分退货', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['套装、赠品与部分退货', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：套装只想退里面一件，赠品丢了，退款能按那件原价给吗？；校验问题：[]

## rag-044 / dev / returns
问题：满减券买的两件只退一件，留下那件不够门槛，钱和券怎么算？
- dense: ['退换货与优惠分摊', '优惠券返还与门槛']；Recall=0.6666666666666666，MRR=1.0；失败标记=['missing_supporting_sections']
- hybrid: ['退换货与优惠分摊', '套装、赠品与部分退货']；Recall=0.3333333333333333，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['退换货与优惠分摊', '套装、赠品与部分退货']；Recall=0.3333333333333333，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：满减券购买两件只退一件，留下那件不够门槛，钱和券怎么算？；校验问题：[]

## rag-045 / dev / returns
问题：换来的耳机又坏了，我还能重新按七天无理由退吗？
- dense: ['换货后再次申请', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=[]
- hybrid: ['换货后再次申请', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['换货后再次申请', '特殊商品退换限制']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：换来的耳机又坏了，还能重新按七天无理由退吗？；校验问题：[]

## rag-046 / test / special
问题：刻了名字的杯子有裂纹，不能无理由退是不是连售后也没了？
- dense: ['特殊商品退换限制', '质量问题退换路径']；Recall=1.0，MRR=1.0；失败标记=[]
- hybrid: ['质量问题退换路径', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['质量问题退换路径', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：刻了名字的杯子有裂纹，不能无理由退是不是连售后也没了？；校验问题：[]

## rag-048 / test / special
问题：贴身用品拆封后有破损，我还可以走质量问题流程吗？
- dense: ['特殊商品退换限制', '七天无理由退款']；Recall=0.3333333333333333，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['特殊商品退换限制', '破损包裹与证据']；Recall=0.6666666666666666，MRR=1.0；失败标记=['missing_supporting_sections']
- rewrite_hybrid: ['特殊商品退换限制', '破损包裹与证据']；Recall=0.6666666666666666，MRR=1.0；失败标记=['missing_supporting_sections']
- 重写：贴身用品拆封后有破损，还可以走质量问题流程吗？；校验问题：[]

## rag-049 / test / special
问题：定制杯子只是颜色不喜欢，签收两天还能无理由退吗？
- dense: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：定制杯子只是颜色不喜欢，签收两天还能无理由退吗？；校验问题：[]

## rag-050 / test / special
问题：定制礼物有故障但我没照片，客服可以直接保证退款吗？
- dense: ['套装、赠品与部分退货', '特殊商品退换限制']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['质量问题退换路径', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['质量问题退换路径', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：定制礼物有故障但我没照片，客服可以直接保证退款吗？；校验问题：[]

## rag-051 / test / exchange
问题：给我发错型号了，签收后一天要换货，得拍哪些地方？
- dense: ['换货与缺件补发', '七天无理由退款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['换货与缺件补发', '破损包裹与证据']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['换货与缺件补发', '破损包裹与证据']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：发错型号了，签收后一天要换货，得拍哪些地方？；校验问题：[]

## rag-052 / test / exchange
问题：漏发的配件已经退款成功了，还能让你们再补一份吗？
- dense: ['换货与缺件补发', '套装、赠品与部分退货']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['换货与缺件补发', '套装、赠品与部分退货']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['换货与缺件补发', '维修与质量退换衔接']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：漏发的配件已经退款成功了，还能再补一份吗？；校验问题：[]

## rag-053 / test / exchange
问题：同一单两箱，只收到第一箱，我想退第二箱，七天从第一箱签收算吗？
- dense: ['七天无理由退款', '分批发货与签收状态']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['七天无理由退款', '分批发货与签收状态']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '分批发货与签收状态']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：同一单两箱，只收到第一箱，想退第二箱，七天从第一箱签收算吗？；校验问题：[]

## rag-054 / test / exchange
问题：套装只退坏的一件又没法把赠品寄回，客服能先确定退款数吗？
- dense: ['套装、赠品与部分退货', '七天无理由退款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['套装、赠品与部分退货', '七天无理由退款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['套装、赠品与部分退货', '七天无理由退款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：套装只退坏的一件且无法把赠品寄回，客服能先确定退款数吗？；校验问题：['negation_added:无', 'negation_removed:没']

## rag-055 / test / exchange
问题：换货包裹刚到又是同样故障，应该重新补发还是能继续申请售后？
- dense: ['换货与缺件补发', '破损包裹与证据']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['维修与质量退换衔接', '破损包裹与证据']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['维修与质量退换衔接', '破损包裹与证据']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：换货包裹刚到又是同样故障，应该重新补发还是能继续申请售后？；校验问题：[]

## rag-056 / dev / refund
问题：退货昨天才寄回去，第三方支付的钱今天应该到账了吗？
- dense: ['退款发起与渠道时效', '退款到账时效']；Recall=1.0，MRR=1.0；失败标记=[]
- hybrid: ['退款发起与渠道时效', '退款到账时效']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['退款到账时效', '退款发起与渠道时效']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：昨天才寄回退货，第三方支付的钱今天应该到账了吗？；校验问题：[]

## rag-057 / dev / refund
问题：银行卡退款发起第4个工作日没到，是不是已经超时要建异常单？
- dense: ['退款到账时效', '补充证据与升级']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['退款到账时效', '退款发起与渠道时效']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['退款到账时效', '退款发起与渠道时效']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：银行卡退款发起第4个工作日未到账，是否已超时需建异常单？；校验问题：['negation_added:未', 'negation_removed:不', 'negation_removed:没']

## rag-058 / dev / refund
问题：余额加第三方支付的订单只退回余额部分，算全额到账了吗？
- dense: ['多支付方式退款核对', '退换货与优惠分摊']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['多支付方式退款核对', '退款发起与渠道时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['多支付方式退款核对', '退款发起与渠道时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：余额加第三方支付的订单只退回余额部分，算全额到账吗？；校验问题：[]

## rag-059 / dev / refund
问题：我只提交了退货申请仓库还没验收，能从提交那天算银行卡7个工作日吗？
- dense: ['退款到账时效', '退款发起与渠道时效']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['退款发起与渠道时效', '退款到账时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['退款发起与渠道时效', '退款到账时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：我只提交了退货申请，仓库还没验收，能从提交那天算银行卡7个工作日吗？；校验问题：[]

## rag-060 / dev / refund
问题：退款能转到我朋友的银行卡吗，具体改收款账户步骤是什么？
- dense: ['退款发起与渠道时效', '退款到账时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['退款发起与渠道时效', '退款到账时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['退款发起与渠道时效', '退款到账时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：退款能转到朋友的银行卡吗，具体改收款账户步骤是什么？；校验问题：[]

## rag-061 / test / shipping
问题：快递六天没新轨迹，异常工单12小时响应是不是12小时就能找到包裹？
- dense: ['延迟与无轨迹核查', '物流异常']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['物流异常', '延迟与无轨迹核查']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['物流异常', '延迟与无轨迹核查']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：快递六天没有新轨迹，异常工单12小时响应是不是12小时就能找到包裹？；校验问题：['negation_added:没有']

## rag-063 / test / shipping
问题：承运商确认包裹丢了而且有货，我能选择补发还是退款？
- dense: ['丢件核实后的选择', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['丢件核实后的选择', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['丢件核实后的选择', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：承运商确认包裹丢失且有货，我能选择补发还是退款？；校验问题：[]

## rag-066 / dev / warranty
问题：耳机签收11个月没摔没进水坏了，有订单没发票一定免费修吗？
- dense: ['商品保修', '免费保修的例外']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['商品保修', '保修起算与凭证']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['商品保修', '保修起算与凭证']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：耳机签收11个月没摔没进水坏了，有订单没发票一定免费修吗？；校验问题：[]

## rag-067 / dev / warranty
问题：手机还没过一年但我把它泡水里了，通用保修包不包免费？
- dense: ['免费保修的例外', '商品保修']；Recall=1.0，MRR=1.0；失败标记=[]
- hybrid: ['免费保修的例外', '保修起算与凭证']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['免费保修的例外', '保修起算与凭证']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：手机未过一年但泡水了，通用保修包不包免费？；校验问题：['negation_added:未', 'negation_removed:没']

## rag-068 / dev / warranty
问题：发票找不到但订单号和序列号都有，能先申请检测吗？
- dense: ['工单身份校验与确认', '保修起算与凭证']；Recall=0.5，MRR=0.5；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['保修起算与凭证', '账户与隐私']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['保修起算与凭证', '账户与隐私']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：发票找不到但订单号和序列号都有，能先申请检测吗？；校验问题：[]

## rag-069 / dev / warranty
问题：电池用久了续航变差，一年内是不是一定免费换新？
- dense: ['商品保修', '免费保修的例外']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['商品保修', '免费保修的例外']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['商品保修', '免费保修的例外']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：电池用久了续航变差，一年内是不是一定免费换新？；校验问题：[]

## rag-070 / dev / warranty
问题：电池自然衰减需要付费换电池的话，具体收我多少钱？
- dense: ['免费保修的例外', '商品保修']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['免费保修的例外', '初检、报价与用户选择']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['免费保修的例外', '初检、报价与用户选择']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：电池自然衰减需要付费换电池的话，具体收我多少钱？；校验问题：[]

## rag-071 / test / repair
问题：设备寄修收到了，初检一般几天？如果要收钱能不问我就动手吗？
- dense: ['初检、报价与用户选择', '保修起算与凭证']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['初检、报价与用户选择', '维修申请与进度']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['初检、报价与用户选择', '维修申请与进度']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：设备寄修收到后初检一般几天？如果要收钱能不问我直接动手吗？；校验问题：[]

## rag-072 / test / repair
问题：报价太高我没同意，还会继续修吗？可以原样寄回来吗？
- dense: ['维修后同故障复检', '补充证据与升级']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['初检、报价与用户选择', '维修后同故障复检']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['初检、报价与用户选择', '维修后同故障复检']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：报价太高我没同意，还会继续修吗？可以原样寄回来吗？；校验问题：[]

## rag-073 / test / repair
问题：修好寄回20天同一个毛病又犯了，还要再付同一项目的钱吗？
- dense: ['维修后同故障复检', '支付失败与重复扣款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['维修后同故障复检', '支付失败与重复扣款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['维修后同故障复检', '支付失败与重复扣款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：修好寄回20天同一个毛病又犯了，还要再付同一项目的钱吗？；校验问题：[]

## rag-075 / test / repair
问题：手机寄修期间你们能免费借我备用机吗，最多借几天？
- dense: ['商品保修', '保修起算与凭证']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['商品保修', '免费保修的例外']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['商品保修', '免费保修的例外']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：手机寄修期间能否免费借用备用机，最多借几天？；校验问题：[]

## rag-078 / dev / invoice
问题：订单退了钱，之前开的专票肯定不用处理了吧？
- dense: ['发票、红冲与退款', '退换货与优惠分摊']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['发票、红冲与退款', '退换货与优惠分摊']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['发票、红冲与退款', '发票服务']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：订单退款后，之前开的专票是否不用处理？；校验问题：[]

## rag-079 / dev / invoice
问题：订单完成两个月了，现在补开专票走哪个入口、审核几天？
- dense: ['发票、红冲与退款', '发票服务']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['发票、红冲与退款', '发票服务']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['发票、红冲与退款', '发票服务']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：订单完成两个月了，现在补开专票走哪个入口、审核几天？；校验问题：[]

## rag-080 / dev / invoice
问题：专票红冲审核过了，是不是说明银行卡退款已经到账？
- dense: ['发票、红冲与退款', '退款到账时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['发票、红冲与退款', '退款到账时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['发票、红冲与退款', '退款到账时效']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：专票红冲审核过了，是不是说明银行卡退款已经到账？；校验问题：[]

## rag-082 / test / payment
问题：同一订单扣了两次，只给你一张流水截图够吗？能要我完整卡号吗？
- dense: ['支付失败与重复扣款', '补充证据与升级']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['支付失败与重复扣款', '支付与重复扣款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['支付失败与重复扣款', '支付与重复扣款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：同一订单扣了两次，只给一张流水截图够吗？能要我完整卡号吗？；校验问题：[]

## rag-083 / test / payment
问题：余额和第三方一起付，余额退回了但微信没到，该按哪个时效查？
- dense: ['多支付方式退款核对', '支付失败与重复扣款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['多支付方式退款核对', '退款发起与渠道时效']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['多支付方式退款核对', '退款发起与渠道时效']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：余额和第三方一起付，余额退回了但微信没到，该按哪个时效查？；校验问题：[]

## rag-084 / test / payment
问题：礼品卡和券能叠加吗？礼品卡余额退回要多久？
- dense: ['优惠券与促销', '优惠券返还与门槛']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['优惠券与促销', '优惠券返还与门槛']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['优惠券与促销', '优惠券返还与门槛']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：礼品卡和券能叠加吗？礼品卡余额退回要多久？；校验问题：[]

## rag-085 / test / payment
问题：重复扣款明天一定全退吗？要是没退赔我多少违约金？
- dense: ['支付与重复扣款', '支付失败与重复扣款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['支付与重复扣款', '支付失败与重复扣款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['支付与重复扣款', '支付失败与重复扣款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：重复扣款明天一定全退吗？要是没退赔我多少违约金？；校验问题：[]

## rag-086 / dev / ticket
问题：物流异常单说12小时响应，承运商联系却说24小时，哪个是找到包裹的时间？
- dense: ['工单类别与响应时效', '延迟与无轨迹核查']；Recall=1.0，MRR=1.0；失败标记=[]
- hybrid: ['工单类别与响应时效', '物流异常']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['工单类别与响应时效', '物流异常']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：物流异常单标注12小时响应，承运商联系称24小时，哪个是找到包裹的时间？；校验问题：[]

## rag-087 / dev / ticket
问题：同一工单我补了新照片，重新点提交能给我新单号并优先吗？
- dense: ['补充证据与升级', '重复提交与幂等']；Recall=1.0，MRR=1.0；失败标记=[]
- hybrid: ['补充证据与升级', '换货与缺件补发']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['补充证据与升级', '换货与缺件补发']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：同一工单补了新照片，重新点提交能给我新单号并优先吗？；校验问题：[]

## rag-088 / dev / ticket
问题：我只问了订单在哪，系统可以不问我就建售后工单吗？
- dense: ['工单身份校验与确认', '客服升级与工单']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['工单身份校验与确认', '客服升级与工单']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['工单身份校验与确认', '客服升级与工单']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：我只问了订单在哪，系统可以不问我就建售后工单吗？；校验问题：[]

## rag-089 / dev / ticket
问题：客服处理结果不满意还涉及人身安全，继续重复建单还是马上升级？
- dense: ['补充证据与升级', '客服升级与工单']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['补充证据与升级', '投诉与服务时效']；Recall=1.0，MRR=1.0；失败标记=[]
- rewrite_hybrid: ['补充证据与升级', '投诉与服务时效']；Recall=1.0，MRR=1.0；失败标记=[]
- 重写：客服处理结果不满意且涉及人身安全，继续重复建单还是马上升级？；校验问题：[]

## rag-090 / dev / ticket
问题：投诉升级以后固定能赔我多少钱，按什么金额标准？
- dense: ['补充证据与升级', '投诉与服务时效']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['投诉与服务时效', '补充证据与升级']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['投诉与服务时效', '补充证据与升级']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：投诉升级以后固定能赔多少钱，按什么金额标准？；校验问题：[]
