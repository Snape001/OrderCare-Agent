# 逐题检索差异与失败案例

## rag-001 / dev / 无理由退货
问题：普通耳机签收第二天拆了包装，配件都在也没损坏，能走无理由退货吗？
- dense: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：普通耳机签收第二天拆了包装，配件都在也没损坏，能走无理由退货吗？；校验问题：[]

## rag-002 / test / 无理由退货
问题：七天的期限从下单、发货还是收货那天开始算？
- dense: ['物流时效与轨迹', '七天无理由退款']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['物流时效与轨迹', '七天无理由退款']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['物流时效与轨迹', '七天无理由退款']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：七天的期限从下单、发货还是收货那天开始算？；校验问题：[]

## rag-003 / dev / 复杂条件
问题：包裹还没到，我就想按七天无理由退款，现在该怎么办？
- dense: ['七天无理由退款', '特殊商品退换限制']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：包裹还没到，想按七天无理由退款，现在该怎么办？；校验问题：[]

## rag-004 / test / 无理由退货
问题：普通商品用了之后已经影响再次出售，还能无理由退吗？
- dense: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['七天无理由退款', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：普通商品使用后已影响再次出售，还能无理由退货吗？；校验问题：[]

## rag-005 / dev / 特殊商品
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

## rag-007 / dev / 质量售后
问题：定做的东西本身就是坏的，是不是因为定制就完全不能售后？
- dense: ['特殊商品退换限制', '商品保修']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['特殊商品退换限制', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['特殊商品退换限制', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：定做的商品本身是坏的，是否因为定制就完全不能售后？；校验问题：[]

## rag-008 / test / 质量售后
问题：拆包发现外壳碎了还少一条线，需要什么时候提交什么材料？
- dense: ['换货与缺件补发', '商品保修']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['换货与缺件补发', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['换货与缺件补发', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：拆包发现外壳碎了还少一条线，需要什么时候提交什么材料？；校验问题：[]

## rag-009 / dev / 质量售后
问题：发错货后我已经拿到退款，还能让店家再补一件吗？
- dense: ['换货与缺件补发', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['换货与缺件补发', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['换货与缺件补发', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：发错货后已拿到退款，还能让店家再补一件吗？；校验问题：[]

## rag-010 / test / 质量售后
问题：换货的新包裹还能沿用原来那个运单号查吗？
- dense: ['换货与缺件补发', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['换货与缺件补发', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['换货与缺件补发', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：换货的新包裹还能沿用原来的运单号查询吗？；校验问题：[]

## rag-011 / dev / 退款流程
问题：东西退回去了，钱是收到退件立刻打回来还是要验货？
- dense: ['换货与缺件补发', '七天无理由退款']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['换货与缺件补发', '七天无理由退款']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['换货与缺件补发', '七天无理由退款']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：东西退回去了，钱是收到退件立刻打回来还是要验货？；校验问题：[]

## rag-012 / test / 退款流程
问题：信用卡退的钱和平台余额退的钱，到账速度一样吗？
- dense: ['退款到账时效', '优惠券与促销']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['退款到账时效', '优惠券与促销']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['退款到账时效', '优惠券与促销']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：信用卡退款和平台余额退款的到账速度一样吗？；校验问题：[]

## rag-013 / dev / 复杂条件
问题：银行卡退款已经超过七个工作日，我该准备哪些信息请人工核查？
- dense: ['退款到账时效', '支付与重复扣款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['退款到账时效', '支付与重复扣款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['退款到账时效', '支付与重复扣款']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：银行卡退款已超过七个工作日，请人工核查需准备哪些信息？；校验问题：[]

## rag-014 / test / 退款资格
问题：钱刚付完还没有开始拣货，我不买了能取消并退钱吗？
- dense: ['订单取消', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['订单取消', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['订单取消', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：钱刚付完还没有开始拣货，我不买了能取消并退钱吗？；校验问题：[]

## rag-015 / dev / 物流异常
问题：物流五六天不动弹了，客服会找谁问，多久去核实？
- dense: ['物流异常', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['物流异常', '客服升级与工单']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['物流异常', '客服升级与工单']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：物流五六天不动弹了，客服会找谁问，多久去核实？；校验问题：[]

## rag-016 / test / 物流异常
问题：页面写着已签收可我根本没拿到，你能保证直接退款吗？
- dense: ['七天无理由退款', '订单取消']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['七天无理由退款', '订单取消']；Recall=0.0，MRR=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['物流异常', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：页面显示已签收但我没收到，能否保证直接退款？；校验问题：[]

## rag-017 / dev / 物流时效
问题：预计周五送到就是保证周五能收到吧？偏远地区还要多等多久？
- dense: ['物流时效与轨迹', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['物流时效与轨迹', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['物流时效与轨迹', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：预计周五送到是否保证周五能收到？偏远地区还要多等多久？；校验问题：[]

## rag-018 / test / 复杂条件
问题：已经发出来的货想转寄到别的省，平台能直接改吗，费用谁说了算？
- dense: ['收货地址修改', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['收货地址修改', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['收货地址修改', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：已发出的货想转寄到别的省，平台能直接改吗，费用谁说了算？；校验问题：[]

## rag-019 / dev / 保修
问题：电子产品没摔没泡水自己坏了，有限保修通常多久，可以修吗？
- dense: ['商品保修', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['商品保修', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['商品保修', '特殊商品退换限制']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：电子产品没摔没泡水自己坏了，有限保修通常多久，可以修吗？；校验问题：[]

## rag-021 / dev / 维修
问题：东西要寄去修，申请需要什么资料，到售后后多久初检？
- dense: ['维修申请与进度', '商品保修']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['维修申请与进度', '发票服务']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['维修申请与进度', '发票服务']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：东西寄去修，申请需要什么资料，到售后后多久初检？；校验问题：[]

## rag-022 / test / 维修
问题：如果检查出要收费，可以不问我直接维修扣钱吗？
- dense: ['商品保修', '维修申请与进度']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['商品保修', '维修申请与进度']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['商品保修', '维修申请与进度']；Recall=1.0，MRR=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：如果检查出要收费，可以不问我直接维修扣钱吗？；校验问题：[]

## rag-023 / dev / 发票
问题：单位要报销，订单完成一个月还能补开票吗，要校验什么？
- dense: ['发票服务', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['发票服务', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['发票服务', '物流异常']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：单位报销，订单完成一个月还能补开票吗，要校验什么？；校验问题：[]

## rag-024 / test / 复杂条件
问题：增值税专票已经开了，税号错了能直接改吗？退货后发票怎么办？
- dense: ['发票服务', '换货与缺件补发']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['发票服务', '收货地址修改']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['发票服务', '收货地址修改']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：增值税专票已开，税号错了能直接改吗？退货后发票怎么办？；校验问题：[]

## rag-025 / dev / 支付
问题：付款提示没成功，银行卡却扣了，我要不要再付一次？
- dense: ['支付与重复扣款', '退款到账时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['支付与重复扣款', '退款到账时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['支付与重复扣款', '退款到账时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：付款提示未成功但银行卡已扣款，是否需要再次付款？；校验问题：['negation_added:未', 'negation_removed:不', 'negation_removed:没']

## rag-027 / dev / 优惠券
问题：取消了订单，用掉的券还能回来吗，需要等多久？
- dense: ['优惠券与促销', '订单取消']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['优惠券与促销', '订单取消']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['优惠券与促销', '订单取消']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：取消了订单，用掉的券还能回来吗，需要等多久？；校验问题：[]

## rag-028 / test / 优惠券
问题：用了满减后又退掉部分商品，为什么退款金额不是原价？
- dense: ['优惠券与促销', '退款到账时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['优惠券与促销', '退款到账时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['优惠券与促销', '退款到账时效']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：使用满减后部分商品退货，退款金额为何不是原价？；校验问题：[]

## rag-029 / dev / 隐私
问题：我不想让你们保留账户资料，要走什么手续？能直接删吗？
- dense: ['账户与隐私', '七天无理由退款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- hybrid: ['账户与隐私', '支付与重复扣款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['账户与隐私', '支付与重复扣款']；Recall=1.0，MRR=1.0；失败标记=['irrelevant_context']
- 重写：我不想让你们保留账户资料，要走什么手续？能直接删吗？；校验问题：[]

## rag-030 / test / 复杂条件
问题：物流工单一直没解决，重复提交能更快吗？目标响应时间是多少？
- dense: ['投诉与服务时效', '物流异常']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- hybrid: ['投诉与服务时效', '物流异常']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- rewrite_hybrid: ['投诉与服务时效', '物流异常']；Recall=0.5，MRR=1.0；失败标记=['missing_supporting_sections', 'irrelevant_context']
- 重写：物流工单一直没解决，重复提交能更快吗？目标响应时间是多少？；校验问题：[]

## rag-031 / dev / 库内缺失
问题：无理由退货的快递费具体由买家还是卖家承担？
- dense: ['七天无理由退款', '换货与缺件补发']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['七天无理由退款', '换货与缺件补发']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['七天无理由退款', '换货与缺件补发']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：无理由退货的快递费具体由买家还是卖家承担？；校验问题：[]

## rag-032 / test / 库内缺失
问题：请告诉我上海线下退货门店的详细地址和营业时间。
- dense: ['退款到账时效', '换货与缺件补发']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['退款到账时效', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['退款到账时效', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：上海线下退货门店详细地址和营业时间；校验问题：[]

## rag-033 / dev / 库内缺失
问题：订单完成一年后还可以申请电子发票吗？如果可以流程是什么？
- dense: ['发票服务', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['发票服务', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['发票服务', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：订单完成一年后还可以申请电子发票吗？如果可以流程是什么？；校验问题：[]

## rag-034 / test / 库内缺失
问题：会员每个月能领几张券？每张优惠券面额是多少？
- dense: ['优惠券与促销']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['优惠券与促销']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['优惠券与促销']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：会员每个月能领几张券？每张优惠券面额是多少？；校验问题：[]

## rag-035 / dev / 动态事实
问题：我的订单 ORD1001 今天下午具体几点送到？
- dense: ['物流时效与轨迹', '物流异常']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['物流时效与轨迹', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['物流时效与轨迹', '七天无理由退款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：我的订单 ORD1001 今天下午具体几点送到？；校验问题：[]

## rag-036 / test / 库内缺失
问题：苹果手机换电池的维修报价是多少元？
- dense: ['商品保修', '维修申请与进度']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['维修申请与进度', '商品保修']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['维修申请与进度', '商品保修']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：苹果手机换电池维修报价多少元；校验问题：[]

## rag-037 / dev / 库内缺失
问题：退到银行卡可以指定另外一个人的卡吗？银行会收多少手续费？
- dense: ['退款到账时效', '支付与重复扣款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['退款到账时效', '支付与重复扣款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['退款到账时效', '支付与重复扣款']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：退到银行卡可以指定另外一个人的卡吗？银行会收多少手续费？；校验问题：[]

## rag-038 / test / 库内缺失
问题：保修期内给我免费提供备用机吗？借用最长多少天？
- dense: ['商品保修', '维修申请与进度']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- hybrid: ['商品保修', '维修申请与进度']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- rewrite_hybrid: ['商品保修', '维修申请与进度']；Recall=None，MRR=None；失败标记=['unsupported_question_returned_context']
- 重写：保修期内免费提供备用机吗？借用最长多少天？；校验问题：[]
