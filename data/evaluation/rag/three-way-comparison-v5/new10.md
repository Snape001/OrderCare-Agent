# v5 新增 10 题逐题排名

排名项为 `政策文件#章节`；`—` 表示无检索结果。

## pair-21-formal

问题：账户疑似被他人登录，应先采取什么措施？

- dense: ['account-security.md#核心规则', 'base-policy.md#账户与隐私', 'privacy-access.md#核心规则']；Recall=1.0000，Precision=0.3333，MRR=1.0000，nDCG=1.0000
- hybrid: ['account-security.md#核心规则', 'base-policy.md#账户与隐私', 'privacy-access.md#核心规则']；Recall=1.0000，Precision=0.3333，MRR=1.0000，nDCG=1.0000
- rewrite_hybrid: ['account-security.md#核心规则', 'base-policy.md#账户与隐私', 'privacy-access.md#核心规则']；Recall=1.0000，Precision=0.3333，MRR=1.0000，nDCG=1.0000
- 重写：账户疑似被他人登录，应先采取什么措施？；校验问题：[]

## pair-21-colloquial

问题：有人偷偷上我号，咋办？

- dense: —；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- hybrid: ['tickets.md#补充证据与升级', 'shipping-exception.md#核心规则', 'shipping-tracking.md#核心规则']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- rewrite_hybrid: ['privacy-access.md#核心规则', 'account-security.md#核心规则', 'base-policy.md#账户与隐私']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- 重写：账户信息被他人登录，怎么办？；校验问题：[]

## pair-22-formal

问题：维修产生费用前是否需要用户同意？

- dense: ['warranty.md#初检、报价与用户选择', 'warranty-scope.md#核心规则', 'repair-review.md#核心规则']；Recall=1.0000，Precision=0.3333，MRR=0.3333，nDCG=0.5000
- hybrid: ['warranty.md#初检、报价与用户选择', 'warranty.md#维修与质量退换衔接', 'warranty-scope.md#核心规则']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- rewrite_hybrid: ['warranty.md#初检、报价与用户选择', 'repair-review.md#核心规则', 'warranty.md#维修后同故障复检']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- 重写：维修报价产生费用前是否需要用户同意？；校验问题：[]

## pair-22-colloquial

问题：修东西要加钱，得先问我吗？

- dense: ['tickets.md#补充证据与升级', 'warranty-scope.md#核心规则', 'warranty.md#初检、报价与用户选择']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- hybrid: ['tickets.md#补充证据与升级', 'base-policy.md#客服升级与工单', 'warranty-scope.md#核心规则']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- rewrite_hybrid: ['warranty.md#初检、报价与用户选择', 'warranty.md#维修后同故障复检', 'repair-review.md#核心规则']；Recall=1.0000，Precision=0.3333，MRR=0.3333，nDCG=0.5000
- 重写：维修报价增加费用前是否需要先征得我同意；校验问题：[]

## pair-23-formal

问题：账户本人信息有误时，如何申请更正？

- dense: ['privacy-access.md#核心规则', 'invoice-change.md#核心规则', 'finance.md#支付失败与重复扣款']；Recall=1.0000，Precision=0.3333，MRR=1.0000，nDCG=1.0000
- hybrid: ['privacy-access.md#核心规则', 'invoice-change.md#核心规则', 'finance.md#支付失败与重复扣款']；Recall=1.0000，Precision=0.3333，MRR=1.0000，nDCG=1.0000
- rewrite_hybrid: ['privacy-access.md#核心规则', 'invoice-change.md#核心规则', 'finance.md#支付失败与重复扣款']；Recall=1.0000，Precision=0.3333，MRR=1.0000，nDCG=1.0000
- 重写：账户本人信息有误时，如何申请更正？；校验问题：[]

## pair-23-colloquial

问题：账号资料填错，咋改？

- dense: ['invoice-change.md#核心规则', 'tickets.md#补充证据与升级', 'order-edit.md#核心规则']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- hybrid: ['invoice-change.md#核心规则', 'finance.md#发票、红冲与退款', 'tickets.md#补充证据与升级']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- rewrite_hybrid: ['invoice-change.md#核心规则', 'finance.md#发票、红冲与退款', 'tickets.md#补充证据与升级']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- 重写：账号资料填错，咋改？；校验问题：[]

## pair-24-formal

问题：商品破损申请售后，须提交哪些材料？

- dense: ['repair-intake.md#核心规则', 'shipping.md#破损包裹与证据', 'base-policy.md#七天无理由退款']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- hybrid: ['repair-intake.md#核心规则', 'returns.md#退货申请与审核材料', 'shipping.md#破损包裹与证据']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- rewrite_hybrid: ['repair-intake.md#核心规则', 'returns.md#退货申请与审核材料', 'shipping.md#破损包裹与证据']；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- 重写：商品破损申请售后，须提交哪些材料？；校验问题：[]

## pair-24-colloquial

问题：东西碎了，拍啥？

- dense: —；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- hybrid: —；Recall=0.0000，Precision=0.0000，MRR=0.0000，nDCG=0.0000
- rewrite_hybrid: ['shipping.md#破损包裹与证据', 'damage-evidence.md#核心规则', 'returns.md#质量问题退换路径']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- 重写：商品破损 需要拍摄什么质量证据；校验问题：[]

## pair-25-formal

问题：已受理工单新增照片时，应如何补充材料？

- dense: ['tickets.md#补充证据与升级', 'ticket-followup.md#核心规则', 'missing-items.md#核心规则']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- hybrid: ['tickets.md#补充证据与升级', 'ticket-followup.md#核心规则', 'shipping.md#破损包裹与证据']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- rewrite_hybrid: ['tickets.md#补充证据与升级', 'ticket-followup.md#核心规则', 'shipping.md#破损包裹与证据']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- 重写：已受理工单新增照片时，应如何补充材料？；校验问题：[]

## pair-25-colloquial

问题：原单补图怎么弄？

- dense: ['tickets.md#补充证据与升级', 'ticket-followup.md#核心规则', 'tickets.md#重复提交与幂等']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- hybrid: ['tickets.md#补充证据与升级', 'ticket-followup.md#核心规则', 'tickets.md#重复提交与幂等']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- rewrite_hybrid: ['tickets.md#补充证据与升级', 'ticket-followup.md#核心规则', 'tickets.md#重复提交与幂等']；Recall=1.0000，Precision=0.3333，MRR=0.5000，nDCG=0.6309
- 重写：原单补图怎么弄？；校验问题：[]
