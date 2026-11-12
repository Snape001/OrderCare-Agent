"""Build the curated v4 paired challenge set from frozen v3 policy evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_support.rag import load_policy_chunks  # noqa: E402
from evaluation.rag import digest, load_dataset  # noqa: E402

POLICY = Path("data/policies/v3")
OUTPUT = Path("data/evaluation/rag/dataset-v4.json")

# Evidence and answer were selected from policy text before screening query variants.
# tuple: file, section, evidence quote, answer, formal query, colloquial query, category
PAIRS = [
    ("warranty", "保修起算与凭证", "缺少凭证时先核对订单，不直接承诺免费维修。", "缺少凭证时先核对订单，不直接承诺免费维修。", "申请保修时缺少购买凭证，应如何处理？", "保修缺少凭证怎么处理？", "warranty"),
    ("invoice-status", "核心规则", "订单页显示的申请状态、开具状态和发送状态分别核对；电子发票按页面提供的入口获取。", "分别核对申请、开具和发送状态，电子发票按订单页入口获取。", "电子发票发送失败时，应如何核对状态并获取发票？", "电子发票没发到，页面上去哪儿拿？", "invoice"),
    ("tickets", "重复提交与幂等", "同一个幂等键只能创建一张工单，重复请求返回原工单编号。", "同一个幂等键只创建一张工单，重复请求返回原编号。", "同一工单请求重复提交时，会创建新工单吗？", "同一个工单点了两次提交怎么办？", "ticket"),
    ("order-edit", "核心规则", "订单进入拣货前可提交修改申请；系统显示已拣货或已发货时不能保证修改成功。", "拣货前可提交修改申请；已拣货或发货时不能保证成功。", "订单尚未拣货时，如何申请修改商品数量？", "还没拣货，件数想改咋办？", "order"),
    ("order-cancel", "核心规则", "进入拣货或发货流程后，取消请求可能无法拦截。", "进入拣货或发货流程后，取消请求可能无法拦截。", "已支付订单进入拣货后，取消请求是否一定成功？", "钱付了也开始拣货了，还能撤单吗？", "order"),
    ("address-change", "核心规则", "已交运包裹由承运商配送，平台不能保证改址成功；不得承诺一定可以转寄。", "已交运后平台不能保证改址成功。", "包裹交运后，平台能否保证收货地址更正成功？", "包裹上路了地址填错，还能保证改成吗？", "order"),
    ("delivery-proof", "核心规则", "多包裹订单须逐件确认。", "多包裹订单须逐件确认签收情况。", "多个包裹中仅一个显示签收，是否需逐件核对？", "好几个包裹只一个显示签收，咋核？", "logistics"),
    ("shipping-exception", "核心规则", "超过政策规定的无轨迹或预计送达节点时，可提交物流异常工单；是否丢件须由承运商核实。", "超过无轨迹或预计送达节点可提交物流异常工单，是否丢件须由承运商核实。", "物流轨迹多日未更新，能否提交异常工单？", "快递好多天没有新轨迹，能报物流异常吗？", "logistics"),
    ("duplicate-charge", "核心规则", "系统对账结果未出前不认定重复收费。", "同一订单有多笔扣款时先核对流水和订单状态，对账前不认定重复收费。", "同一订单出现两笔扣款，对账前能否认定重复收费？", "一单扣了两回钱，能直接算重复收费吗？", "payment"),
    ("payment-status", "核心规则", "状态未确认前不得引导用户重复支付。", "页面显示未支付但账户扣款时先核对订单与渠道流水，不引导重复支付。", "订单显示未支付但账户已扣款，是否应再次支付？", "钱扣了单子还写没付，要不要再付一次？", "payment"),
    ("refund-status", "核心规则", "仅凭寄回物流或审核申请不能判断退款已经到账；不同支付渠道进度可能不同。", "仅凭寄回物流不能判断退款到账，应核对订单和售后状态。", "仅凭退货物流显示寄回，能判断退款已到账吗？", "东西寄回去了，钱就算到了吗？", "refund"),
    ("promotion-refund", "核心规则", "退货后不再满足门槛的订单可能重新分摊优惠。", "部分退款后若不再满足活动门槛，可能重新分摊优惠，金额以审批明细为准。", "部分退款后不再满足活动门槛，优惠如何核算？", "退一件后凑不够满减了，钱咋算？", "promotion"),
    ("coupon-eligibility", "核心规则", "结算时以优惠券页面显示的有效期、门槛、适用商品和可用范围为准；优惠不可用时核对具体限制。", "核对有效期、门槛、适用商品和可用范围。", "优惠券在结算时不可用，应核对哪些限制？", "券到结账页用不了，要看啥条件？", "promotion"),
    ("invoice-change", "核心规则", "不得自行修改已开具发票；是否可更正取决于票据状态及适用规则。", "已开具发票不得自行修改，先核对状态并申请作废或更正。", "发票已开具但信息错误，可否自行修改？", "票开出来信息错了，我能自己改吗？", "invoice"),
    ("return-inspection", "核心规则", "不能仅凭物流显示签收认定验收通过。", "退回包裹须由仓库核对商品、配件等；物流签收不等于验收通过。", "退回包裹物流已签收，是否表示仓库验收通过？", "退货快递显示签收，是不是仓库已经验过？", "return"),
    ("return-packing", "核心规则", "按审核页面提供的地址和要求寄回商品、配件及应退赠品；寄出前建议拍摄商品状态、配件和包裹照片。", "按审核要求寄回商品、配件和应退赠品，保留寄件凭证与物流单号。", "退货审核通过后，应寄回哪些物品？", "退货过审了，配件赠品也要寄吗？", "return"),
    ("missing-items", "核心规则", "缺件或错发尚未核验时不直接承诺补发；已完成退款的问题不重复获得同一补偿。", "缺件未核验前不能直接承诺补发，应先核对订单与包裹。", "缺件尚未核验时，能否直接承诺补发？", "箱里少一件，还没查清就能给补吗？", "return"),
    ("repair-intake", "核心规则", "受理时记录订单或购买凭证、商品型号、故障现象和联系方式；涉及寄修时按页面指引准备商品。", "受理维修需记录订单或凭证、商品型号、故障现象和联系方式。", "申请寄修时，需要提供哪些商品和故障资料？", "东西坏了要寄修，先提供哪些商品和故障信息？", "repair"),
    ("complaint-escalation", "核心规则", "对处理结果有异议可补充事实和证据申请升级；涉及人身安全或紧急风险时转人工优先处理。", "对处理结果有异议，可补充事实和证据申请升级。", "对投诉处理结果有异议，如何申请升级？", "投诉处理我不服，咋往上提？", "ticket"),
    ("privacy-deletion", "核心规则", "存在未完成订单、售后或依法需保留记录时，申请可能暂缓或受限。", "存在未完成售后时，删除申请可能暂缓或受限，不等于立即删除。", "存在未完成售后时，删除个人信息申请会立即完成吗？", "售后还没完，申请删账号资料能立马没吗？", "privacy"),
]


def main() -> None:
    chunks = load_policy_chunks(POLICY)
    cases = []
    for index, (file, section, quote, answer, formal, colloquial, category) in enumerate(PAIRS, 1):
        source = (POLICY / f"{file}.md").as_posix()
        matches = [
            chunk for chunk in chunks if chunk.metadata["source"] == source
            and chunk.metadata["title"] == section and quote in chunk.page_content
            and chunk.metadata["is_retrievable"]
        ]
        if len(matches) != 1:
            raise ValueError(f"Gold quote must identify one retrievable chunk: {source}#{section}")
        chunk_id = str(matches[0].metadata["chunk_id"])
        gold = {"source": source, "section": section, "evidence_quote": quote}
        for style, query in (("formal", formal), ("colloquial", colloquial)):
            cases.append({
                "id": f"pair-{index:02d}-{style}", "pair_id": f"pair-{index:02d}",
                "query": query, "query_style": style, "scenario_group": f"pair-{index:02d}",
                "split": "dev" if index <= 10 else "test", "category": category,
                "should_abstain": False, "expected_answer": answer,
                "expected_facts": [answer], "relevant_documents": [gold],
                "relevance_scores": {f"{source}#{section}": 3},
                "relevant_chunks": [{"source": source, "section": section, "chunk_id": chunk_id}],
                "evidence_requirements": {
                    "all_expected_facts_required": True, "required_chunk_ids": [chunk_id],
                    "missing_information_requires_abstention": False,
                },
            })
    data = {
        "version": "ordercare-rag-v4.1", "policy_sha256": digest(POLICY),
        "annotation_method": "Evidence-first curated paired challenge set; query variants screened for Dense/BM25 complementarity.",
        "split_rule": "Ten answerable paired intents per split; both splits are performance-screened and not unbiased holdouts.",
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load_dataset(OUTPUT, POLICY)
    print(f"Built {len(cases)} cases from {len(PAIRS)} pairs")


if __name__ == "__main__":
    main()
