# 逐题检索差异与失败案例

## pair-01-formal / dev / warranty
问题：申请保修时缺少购买凭证，应如何处理？
- dense: ['核心规则', '维修与质量退换衔接', '核心规则']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['核心规则', '保修起算与凭证', '维修与质量退换衔接']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '保修起算与凭证', '维修与质量退换衔接']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：申请保修时缺少购买凭证，应如何处理？；校验问题：[]

## pair-01-colloquial / dev / warranty
问题：保修缺少凭证怎么处理？
- dense: ['核心规则', '维修与质量退换衔接', '免费保修的例外']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['免费保修的例外', '核心规则', '保修起算与凭证']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['免费保修的例外', '核心规则', '保修起算与凭证']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：保修缺少凭证怎么处理？；校验问题：[]

## pair-02-formal / dev / invoice
问题：电子发票发送失败时，应如何核对状态并获取发票？
- dense: ['核心规则', '核心规则', '发票服务']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '核心规则', '发票服务']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '核心规则', '发票服务']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：电子发票发送失败时，应如何核对状态并获取发票？；校验问题：[]

## pair-02-colloquial / dev / invoice
问题：电子发票没发到，页面上去哪儿拿？
- dense: ['核心规则', '核心规则', '发票、红冲与退款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '发票、红冲与退款', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '发票、红冲与退款', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：电子发票未收到，页面上在哪里获取？；校验问题：['negation_added:未', 'negation_removed:没']

## pair-03-formal / dev / ticket
问题：同一工单请求重复提交时，会创建新工单吗？
- dense: ['重复提交与幂等', '补充证据与升级', '客服升级与工单']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['重复提交与幂等', '客服升级与工单', '补充证据与升级']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['重复提交与幂等', '客服升级与工单', '补充证据与升级']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：同一工单请求重复提交时，会创建新工单吗？；校验问题：[]

## pair-03-colloquial / dev / ticket
问题：同一个工单点了两次提交怎么办？
- dense: ['补充证据与升级', '投诉与服务时效', '客服升级与工单']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['客服升级与工单', '补充证据与升级', '重复提交与幂等']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['客服升级与工单', '重复提交与幂等', '补充证据与升级']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：同一个售后工单重复提交怎么办？；校验问题：[]

## pair-04-formal / dev / order
问题：订单尚未拣货时，如何申请修改商品数量？
- dense: ['核心规则', '收货地址修改', '换货与缺件补发']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '收货地址修改', '换货与缺件补发']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '收货地址修改', '换货与缺件补发']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：订单尚未拣货时，如何申请修改商品数量？；校验问题：[]

## pair-04-colloquial / dev / order
问题：还没拣货，件数想改咋办？
- dense: ['核心规则', '收货地址修改', '换货后再次申请']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['收货地址修改', '核心规则', '订单取消']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['收货地址修改', '核心规则', '订单取消']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：订单状态为未拣货，想修改件数，怎么办？；校验问题：['negation_added:未', 'negation_removed:没']

## pair-05-formal / dev / order
问题：已支付订单进入拣货后，取消请求是否一定成功？
- dense: ['核心规则', '订单取消', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '订单取消', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '订单取消', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：已支付订单进入拣货后，取消请求是否一定成功？；校验问题：[]

## pair-05-colloquial / dev / order
问题：钱付了也开始拣货了，还能撤单吗？
- dense: ['订单取消', '退换货与优惠分摊', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['订单取消', '核心规则', '退换货与优惠分摊']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '订单取消', '支付与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：订单已支付且开始拣货，还能撤单吗？；校验问题：[]

## pair-06-formal / dev / order
问题：包裹交运后，平台能否保证收货地址更正成功？
- dense: ['核心规则', '收货地址修改', '物流异常']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '收货地址修改', '物流异常']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '收货地址修改', '物流异常']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：包裹交运后，平台能否保证收货地址更正成功？；校验问题：[]

## pair-06-colloquial / dev / order
问题：包裹上路了地址填错，还能保证改成吗？
- dense: ['核心规则', '收货地址修改', '丢件核实后的选择']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '分批发货与签收状态', '收货地址修改']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['收货地址修改', '核心规则', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：包裹已发货，收货地址填错，能否修改地址？；校验问题：[]

## pair-07-formal / dev / logistics
问题：多个包裹中仅一个显示签收，是否需逐件核对？
- dense: ['核心规则', '多包裹与错投', '代签与签收争议']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '多包裹与错投', '分批发货与签收状态']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '多包裹与错投', '分批发货与签收状态']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：多个包裹中仅一个显示签收，是否需逐件核对？；校验问题：[]

## pair-07-colloquial / dev / logistics
问题：好几个包裹只一个显示签收，咋核？
- dense: ['核心规则', '代签与签收争议', '多包裹与错投']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['代签与签收争议', '多包裹与错投', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['多包裹与错投', '核心规则', '分批发货与签收状态']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：多个包裹中仅一个显示签收，如何核实物流轨迹？；校验问题：[]

## pair-08-formal / dev / logistics
问题：物流轨迹多日未更新，能否提交异常工单？
- dense: ['延迟与无轨迹核查', '核心规则', '物流异常']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['延迟与无轨迹核查', '核心规则', '工单类别与响应时效']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['延迟与无轨迹核查', '核心规则', '工单类别与响应时效']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：物流轨迹多日未更新，能否提交异常工单？；校验问题：[]

## pair-08-colloquial / dev / logistics
问题：快递好多天没有新轨迹，能报物流异常吗？
- dense: ['延迟与无轨迹核查', '物流异常', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['延迟与无轨迹核查', '物流异常', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['延迟与无轨迹核查', '物流异常', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：快递好多天没有新物流轨迹，能报物流异常吗？；校验问题：[]

## pair-09-formal / dev / payment
问题：同一订单出现两笔扣款，对账前能否认定重复收费？
- dense: ['核心规则', '支付失败与重复扣款', '支付与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['支付失败与重复扣款', '核心规则', '支付与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['支付失败与重复扣款', '核心规则', '支付与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：同一订单出现两笔扣款，对账前能否认定重复收费？；校验问题：[]

## pair-09-colloquial / dev / payment
问题：一单扣了两回钱，能直接算重复收费吗？
- dense: ['支付与重复扣款', '支付失败与重复扣款', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['支付与重复扣款', '核心规则', '支付失败与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['支付与重复扣款', '核心规则', '支付失败与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：一单扣了两回钱，能直接算重复收费吗？；校验问题：[]

## pair-10-formal / dev / payment
问题：订单显示未支付但账户已扣款，是否应再次支付？
- dense: ['核心规则', '支付失败与重复扣款', '支付与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '支付与重复扣款', '支付失败与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '支付与重复扣款', '支付失败与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：订单状态显示未支付但账户已扣款，是否应再次支付？；校验问题：[]

## pair-10-colloquial / dev / payment
问题：钱扣了单子还写没付，要不要再付一次？
- dense: ['支付失败与重复扣款', '支付与重复扣款', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['支付失败与重复扣款', '支付与重复扣款', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['支付失败与重复扣款', '支付与重复扣款', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：钱扣了订单状态显示未支付，是否需要再次支付；校验问题：['negation_added:未', 'negation_removed:不', 'negation_removed:没']

## pair-11-formal / test / refund
问题：仅凭退货物流显示寄回，能判断退款已到账吗？
- dense: ['核心规则', '核心规则', '代签与签收争议']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '核心规则', '多支付方式退款核对']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '核心规则', '多支付方式退款核对']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：仅凭退货物流显示寄回，能判断退款已到账吗？；校验问题：[]

## pair-11-colloquial / test / refund
问题：东西寄回去了，钱就算到了吗？
- dense: ['核心规则', '核心规则', '代签与签收争议']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['核心规则', '核心规则', '退款到账时效']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '核心规则', '退款到账时效']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：东西寄回去了，钱就算到了吗？；校验问题：[]

## pair-12-formal / test / promotion
问题：部分退款后不再满足活动门槛，优惠如何核算？
- dense: ['核心规则', '优惠券与促销', '退换货与优惠分摊']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '退换货与优惠分摊', '优惠券与促销']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '退换货与优惠分摊', '优惠券与促销']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：部分退款后不再满足活动门槛，优惠如何核算？；校验问题：[]

## pair-12-colloquial / test / promotion
问题：退一件后凑不够满减了，钱咋算？
- dense: ['退换货与优惠分摊', '核心规则', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['退换货与优惠分摊', '套装、赠品与部分退货', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['退换货与优惠分摊', '套装、赠品与部分退货', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：退一件后凑不够满减了，钱咋算？；校验问题：[]

## pair-13-formal / test / promotion
问题：优惠券在结算时不可用，应核对哪些限制？
- dense: ['核心规则', '优惠券与促销', '优惠券返还与门槛']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '优惠券与促销', '优惠券返还与门槛']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '优惠券与促销', '优惠券返还与门槛']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：优惠券在结算时不可用，应核对哪些限制？；校验问题：[]

## pair-13-colloquial / test / promotion
问题：券到结账页用不了，要看啥条件？
- dense: ['核心规则', '核心规则', '支付失败与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '优惠券与促销', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '优惠券与促销', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：券在结账页无法使用，需要查看哪些条件？；校验问题：['negation_added:无', 'negation_removed:不']

## pair-14-formal / test / invoice
问题：发票已开具但信息错误，可否自行修改？
- dense: ['核心规则', '发票、红冲与退款', '发票服务']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '发票服务', '发票、红冲与退款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '发票服务', '发票、红冲与退款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：发票已开具但信息错误，可否自行修改？；校验问题：[]

## pair-14-colloquial / test / invoice
问题：票开出来信息错了，我能自己改吗？
- dense: ['核心规则', '发票、红冲与退款', '发票服务']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '多包裹与错投', '发票、红冲与退款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '发票、红冲与退款', '发票服务']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：发票信息错误，我能自己改吗？；校验问题：[]

## pair-15-formal / test / return
问题：退回包裹物流已签收，是否表示仓库验收通过？
- dense: ['核心规则', '代签与签收争议', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '代签与签收争议', '分批发货与签收状态']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '代签与签收争议', '分批发货与签收状态']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：退回包裹物流已签收，是否表示仓库验收通过？；校验问题：[]

## pair-15-colloquial / test / return
问题：退货快递显示签收，是不是仓库已经验过？
- dense: ['核心规则', '核心规则', '代签与签收争议']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['代签与签收争议', '核心规则', '分批发货与签收状态']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['代签与签收争议', '核心规则', '分批发货与签收状态']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：退货快递显示签收，是不是仓库已经验过？；校验问题：[]

## pair-16-formal / test / return
问题：退货审核通过后，应寄回哪些物品？
- dense: ['核心规则', '核心规则', '换货与缺件补发']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '退货申请与审核材料', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '退货申请与审核材料', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：退货审核通过后，应寄回哪些物品？；校验问题：[]

## pair-16-colloquial / test / return
问题：退货过审了，配件赠品也要寄吗？
- dense: ['核心规则', '七天无理由退款', '退货申请与审核材料']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '退货申请与审核材料', '套装、赠品与部分退货']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '退货申请与审核材料', '套装、赠品与部分退货']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：退货过审了，配件赠品也要寄吗？；校验问题：[]

## pair-17-formal / test / return
问题：缺件尚未核验时，能否直接承诺补发？
- dense: ['核心规则', '破损包裹与证据', '换货与缺件补发']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '换货与缺件补发', '破损包裹与证据']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '换货与缺件补发', '破损包裹与证据']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：缺件尚未核验时，能否直接承诺补发？；校验问题：[]

## pair-17-colloquial / test / return
问题：箱里少一件，还没查清就能给补吗？
- dense: ['核心规则', '破损包裹与证据', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '多包裹与错投', '破损包裹与证据']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '多包裹与错投', '换货与缺件补发']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：订单少一件，还没查清就能给补吗？；校验问题：[]

## pair-18-formal / test / repair
问题：申请寄修时，需要提供哪些商品和故障资料？
- dense: ['核心规则', '维修申请与进度', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '核心规则', '退货申请与审核材料']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '核心规则', '退货申请与审核材料']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：申请寄修时，需要提供哪些商品和故障资料？；校验问题：[]

## pair-18-colloquial / test / repair
问题：东西坏了要寄修，先提供哪些商品和故障信息？
- dense: ['核心规则', '核心规则', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['核心规则', '核心规则', '特殊商品退换限制']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '核心规则', '维修后同故障复检']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：商品损坏寄修前需提供哪些商品信息和故障信息；校验问题：[]

## pair-19-formal / test / ticket
问题：对投诉处理结果有异议，如何申请升级？
- dense: ['核心规则', '补充证据与升级', '投诉与服务时效']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '投诉与服务时效', '补充证据与升级']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '投诉与服务时效', '补充证据与升级']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：对投诉处理结果有异议，如何申请升级？；校验问题：[]

## pair-19-colloquial / test / ticket
问题：投诉处理我不服，咋往上提？
- dense: ['补充证据与升级', '核心规则', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['补充证据与升级', '投诉与服务时效', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '补充证据与升级', '投诉与服务时效']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：投诉处理结果不服，如何向上级申诉？；校验问题：[]

## pair-20-formal / test / privacy
问题：存在未完成售后时，删除个人信息申请会立即完成吗？
- dense: ['核心规则', '核心规则', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '核心规则', '代签与签收争议']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '核心规则', '代签与签收争议']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：存在未完成售后工单时，删除个人信息申请会立即完成吗？；校验问题：[]

## pair-20-colloquial / test / privacy
问题：售后还没完，申请删账号资料能立马没吗？
- dense: ['核心规则', '退货申请与审核材料', '七天无理由退款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '退货申请与审核材料', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '退货申请与审核材料', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：售后工单未完结时申请删除账户信息能否立即生效；校验问题：['negation_added:未', 'negation_removed:没']

## pair-21-formal / dev / privacy
问题：账户疑似被他人登录，应先采取什么措施？
- dense: ['核心规则', '账户与隐私', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '账户与隐私', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '账户与隐私', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：账户疑似被他人登录，应先采取什么措施？；校验问题：[]

## pair-21-colloquial / dev / privacy
问题：有人偷偷上我号，咋办？
- dense: []；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['answerable_question_rejected']
- hybrid: ['补充证据与升级', '核心规则', '核心规则']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '核心规则', '账户与隐私']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：账户信息被他人登录，怎么办？；校验问题：[]

## pair-22-formal / dev / repair
问题：维修产生费用前是否需要用户同意？
- dense: ['初检、报价与用户选择', '核心规则', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['初检、报价与用户选择', '维修与质量退换衔接', '核心规则']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['初检、报价与用户选择', '核心规则', '维修后同故障复检']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：维修报价产生费用前是否需要用户同意？；校验问题：[]

## pair-22-colloquial / dev / repair
问题：修东西要加钱，得先问我吗？
- dense: ['补充证据与升级', '核心规则', '初检、报价与用户选择']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['补充证据与升级', '客服升级与工单', '核心规则']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['初检、报价与用户选择', '维修后同故障复检', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.3333333333333333，nDCG=0.5；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：维修报价增加费用前是否需要先征得我同意；校验问题：[]

## pair-23-formal / dev / privacy
问题：账户本人信息有误时，如何申请更正？
- dense: ['核心规则', '核心规则', '支付失败与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- hybrid: ['核心规则', '核心规则', '支付失败与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- rewrite_hybrid: ['核心规则', '核心规则', '支付失败与重复扣款']；Recall=1.0，Precision=0.3333333333333333，MRR=1.0，nDCG=1.0；失败标记=['irrelevant_context']
- 重写：账户本人信息有误时，如何申请更正？；校验问题：[]

## pair-23-colloquial / dev / privacy
问题：账号资料填错，咋改？
- dense: ['核心规则', '补充证据与升级', '核心规则']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['核心规则', '发票、红冲与退款', '补充证据与升级']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '发票、红冲与退款', '补充证据与升级']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：账号资料填错，咋改？；校验问题：[]

## pair-24-formal / test / return
问题：商品破损申请售后，须提交哪些材料？
- dense: ['核心规则', '破损包裹与证据', '七天无理由退款']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- hybrid: ['核心规则', '退货申请与审核材料', '破损包裹与证据']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['核心规则', '退货申请与审核材料', '破损包裹与证据']；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['missing_supporting_sections', 'irrelevant_top1', 'irrelevant_context']
- 重写：商品破损申请售后，须提交哪些材料？；校验问题：[]

## pair-24-colloquial / test / return
问题：东西碎了，拍啥？
- dense: []；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['answerable_question_rejected']
- hybrid: []；Recall=0.0，Precision=0.0，MRR=0.0，nDCG=0.0；失败标记=['answerable_question_rejected']
- rewrite_hybrid: ['破损包裹与证据', '核心规则', '质量问题退换路径']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：商品破损 需要拍摄什么质量证据；校验问题：[]

## pair-25-formal / test / ticket
问题：已受理工单新增照片时，应如何补充材料？
- dense: ['补充证据与升级', '核心规则', '核心规则']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['补充证据与升级', '核心规则', '破损包裹与证据']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['补充证据与升级', '核心规则', '破损包裹与证据']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：已受理工单新增照片时，应如何补充材料？；校验问题：[]

## pair-25-colloquial / test / ticket
问题：原单补图怎么弄？
- dense: ['补充证据与升级', '核心规则', '重复提交与幂等']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- hybrid: ['补充证据与升级', '核心规则', '重复提交与幂等']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- rewrite_hybrid: ['补充证据与升级', '核心规则', '重复提交与幂等']；Recall=1.0，Precision=0.3333333333333333，MRR=0.5，nDCG=0.6309297535714575；失败标记=['irrelevant_top1', 'irrelevant_context']
- 重写：原单补图怎么弄？；校验问题：[]
