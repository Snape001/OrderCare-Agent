"""Build v2 from frozen v1 labels and manually authored policy-grounded cases."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_support.policy import load_policy_sections  # noqa: E402
from customer_support.rag import load_policy_chunks  # noqa: E402
from evaluation.rag import digest, load_dataset  # noqa: E402

CORPUS = Path("data/policies/v2")
OLD = Path("data/evaluation/rag/dataset-v1.json")
OUTPUT = Path("data/evaluation/rag/dataset-v2.json")
BASE = "base-policy.md"

# Scenario groups, rather than adjacent question IDs, determine the holdout split.
GROUP_SPLIT = {
    "returns": "dev",
    "special": "test",
    "exchange": "test",
    "refund": "dev",
    "shipping": "test",
    "warranty": "dev",
    "repair": "test",
    "invoice": "dev",
    "payment": "test",
    "coupon": "dev",
    "ticket": "dev",
    "privacy": "dev",
    "unrelated_dev": "dev",
    "unrelated_test": "test",
}
OLD_GROUPS = {
    "returns": (1, 2, 3, 4, 14, 31),
    "special": (5, 6, 7),
    "exchange": (8, 9, 10),
    "refund": (11, 12, 13, 37),
    "shipping": (15, 16, 17, 18, 35),
    "warranty": (19, 20),
    "repair": (21, 22, 32, 36, 38),
    "invoice": (23, 24, 33),
    "payment": (25, 26),
    "coupon": (27, 28, 34),
    "privacy": (29,),
    "ticket": (30,),
    "unrelated_dev": (39,),
    "unrelated_test": (40,),
}

# Each tuple is (id number, scenario group, question, (file, section, grade) list,
# manually checked core facts). Empty source lists are intentional abstention cases.
NEW_CASES: list[tuple[int, str, str, list[tuple[str, str, int]], list[str]]] = [
    (41, "returns", "耳机刚签收，包装拆了但配件都在，点了退货申请就算通过了吗？", [(BASE, "七天无理由退款", 3), ("returns.md", "退货申请与审核材料", 3)], ["签收次日起7个自然日内可申请", "拆封普通商品完好且附件齐全可提交审核", "提交申请不等于审核通过"]),
    (42, "returns", "货还在路上，我想先按收到货的七天退，能把期限从今天算吗？", [(BASE, "七天无理由退款", 3), ("returns.md", "分批发货与签收状态", 2)], ["未签收商品不能作为已签收无理由退货", "期限从该包裹签收次日起算", "运输中先查询物流或尝试拦截"]),
    (43, "returns", "套装只想退里面一件，赠品我丢了，退款能按那件原价给吗？", [("returns.md", "套装、赠品与部分退货", 3)], ["先核对套装是否支持拆分，不支持时整体审核", "赠品无法退回可能扣除展示的分摊价值", "未核算前不能承诺固定退款金额"]),
    (44, "returns", "满减券买的两件只退一件，留下那件不够门槛，钱和券怎么算？", [("returns.md", "退换货与优惠分摊", 3), (BASE, "优惠券与促销", 2), ("finance.md", "优惠券返还与门槛", 2)], ["部分退货后不满足门槛需重算优惠分摊", "实际退款以审核明细为准", "取消订单的券返还与部分退货不同"]),
    (45, "returns", "换来的耳机又坏了，我还能重新按七天无理由退吗？", [("returns.md", "换货后再次申请", 3), (BASE, "七天无理由退款", 2)], ["换货不自动重置原订单无理由期限", "新质量问题可提交质量售后并提供证据", "无理由资格须核对原签收时间及商品状态"]),
    (46, "special", "刻了名字的杯子有裂纹，不能无理由退是不是连售后也没了？", [(BASE, "特殊商品退换限制", 3), ("returns.md", "质量问题退换路径", 3)], ["定制品不适用七天无理由", "质量问题仍可提交证据进入质量售后核验", "核验前不能承诺退款"]),
    (47, "special", "数字商品激活了但打不开，能因为质量问题申请处理吗？", [(BASE, "特殊商品退换限制", 3), ("returns.md", "质量问题退换路径", 3)], ["激活数字商品不适用无理由退货", "故障可进入质量售后核验", "应提供故障描述和必要证据"]),
    (48, "special", "贴身用品拆封后有破损，我还可以走质量问题流程吗？", [(BASE, "特殊商品退换限制", 3), ("returns.md", "质量问题退换路径", 3), ("shipping.md", "破损包裹与证据", 2)], ["拆封影响健康安全的贴身用品不适用无理由", "破损可按质量或物流售后核验", "应提交对应照片及故障证据"]),
    (49, "special", "定制杯子只是颜色不喜欢，签收两天还能无理由退吗？", [(BASE, "特殊商品退换限制", 3)], ["定制商品不适用七天无理由退货", "仅不喜欢不构成已核实质量问题"]),
    (50, "special", "定制礼物有故障但我没照片，客服可以直接保证退款吗？", [(BASE, "特殊商品退换限制", 2), ("returns.md", "质量问题退换路径", 3)], ["定制商品质量问题可进入售后核验", "须补故障描述和照片视频等证据", "不能直接承诺退款"]),
    (51, "exchange", "给我发错型号了，签收后一天要换货，得拍哪些地方？", [(BASE, "换货与缺件补发", 3), ("shipping.md", "破损包裹与证据", 2)], ["错发应在签收后48小时内提交", "上传外包装、商品和快递面单照片", "核验通过后可选择换货"]),
    (52, "exchange", "漏发的配件已经退款成功了，还能让你们再补一份吗？", [(BASE, "换货与缺件补发", 3), ("returns.md", "换货后再次申请", 2)], ["同一问题已完成退款不再重复补发", "不能同时完成退款和补发"]),
    (53, "exchange", "同一单两箱，只收到第一箱，我想退第二箱，七天从第一箱签收算吗？", [("returns.md", "分批发货与签收状态", 3), ("shipping.md", "多包裹与错投", 2)], ["每包裹按各自签收状态处理", "未收第二箱先查物流而非按已签收退货", "第二箱无理由期限不能按第一箱日期计算"]),
    (54, "exchange", "套装只退坏的一件又没法把赠品寄回，客服能先确定退款数吗？", [("returns.md", "套装、赠品与部分退货", 3), ("returns.md", "质量问题退换路径", 2)], ["先核对套装是否支持拆分及质量证据", "赠品无法退回可能扣分摊价值", "未核算前不能确定退款金额"]),
    (55, "exchange", "换货包裹刚到又是同样故障，应该重新补发还是能继续申请售后？", [("returns.md", "换货后再次申请", 3), (BASE, "换货与缺件补发", 2)], ["新故障可再次提交质量售后", "提供新物流单号与故障证据", "不能未经核验直接承诺再次补发"]),
    (56, "refund", "退货昨天才寄回去，第三方支付的钱今天应该到账了吗？", [("finance.md", "退款发起与渠道时效", 3), (BASE, "退款到账时效", 2)], ["退款以仓库验收通过后发起", "第三方支付通常1至3个工作日", "仅寄回不等于已发起退款"]),
    (57, "refund", "银行卡退款发起第4个工作日没到，是不是已经超时要建异常单？", [("finance.md", "退款发起与渠道时效", 3), (BASE, "退款到账时效", 2)], ["银行卡通常3至7个工作日", "第4个工作日不一定超出通常时效", "超过对应时效再凭订单号和流水号建异常工单"]),
    (58, "refund", "余额加第三方支付的订单只退回余额部分，算全额到账了吗？", [("finance.md", "多支付方式退款核对", 3), (BASE, "退款到账时效", 2)], ["组合支付应分别核对原渠道退款明细", "余额到账不代表第三方支付部分到账", "各渠道时效不同"]),
    (59, "refund", "我只提交了退货申请仓库还没验收，能从提交那天算银行卡7个工作日吗？", [("finance.md", "退款发起与渠道时效", 3), ("returns.md", "退货申请与审核材料", 2)], ["提交申请不等于审核通过", "退款时效从仓库验收通过后发起计算", "银行卡通常3至7个工作日"]),
    (60, "refund", "退款能转到我朋友的银行卡吗，具体改收款账户步骤是什么？", [], ["知识库没有转至他人银行卡的办理规则或步骤，应说明无法确认并转人工核实"]),
    (61, "shipping", "快递六天没新轨迹，异常工单12小时响应是不是12小时就能找到包裹？", [("shipping.md", "延迟与无轨迹核查", 3), ("tickets.md", "工单类别与响应时效", 3)], ["超过5天无新轨迹可建物流异常工单", "异常工单目标响应12小时", "24小时内联系承运商核查，响应不等于查清包裹"]),
    (62, "shipping", "页面签收了我没拿到，邻居代签的信息能直接告诉没验证订单的我吗？", [("shipping.md", "代签与签收争议", 3), (BASE, "账户与隐私", 3)], ["先核对代签及投递记录并走物流异常", "未核验订单身份不能披露代签人和地址电话", "显示签收不等于本人收到"]),
    (63, "shipping", "承运商确认包裹丢了而且有货，我能选择补发还是退款？", [("shipping.md", "丢件核实后的选择", 3)], ["承运商确认丢失且仍有货时可在重发和申请退款间选择", "退款仍需审核", "不能同一包裹同时完成补发和退款"]),
    (64, "shipping", "物流疑似丢件还没核实，客服可以马上保证退钱吗？", [(BASE, "物流异常", 3), ("shipping.md", "丢件核实后的选择", 3)], ["疑似丢失先创建物流异常工单并核实", "核实前不能直接承诺退款结果"]),
    (65, "shipping", "一单两个物流号，一箱签收一箱错投，能说整单到了并一起算退货期限吗？", [("shipping.md", "多包裹与错投", 3), ("returns.md", "分批发货与签收状态", 3)], ["每包裹分别核对轨迹和签收", "错投的包裹按对应物流号核查", "退货期限按各自签收次日起算"]),
    (66, "warranty", "耳机签收11个月没摔没进水坏了，有订单没发票一定免费修吗？", [("warranty.md", "保修起算与凭证", 3), ("warranty.md", "免费保修的例外", 3)], ["通用电子产品签收日起12个月有限保修且以商品页凭证为准", "可用订单核对购买记录", "非人为故障仍须检测，不能直接保证免费"]),
    (67, "warranty", "手机还没过一年但我把它泡水里了，通用保修包不包免费？", [(BASE, "商品保修", 3), ("warranty.md", "免费保修的例外", 3)], ["进水属于免费保修排除项", "是否可维修仍需检测及可能报价"]),
    (68, "warranty", "发票找不到但订单号和序列号都有，能先申请检测吗？", [("warranty.md", "保修起算与凭证", 3), (BASE, "维修申请与进度", 2)], ["缺发票可先核对订单", "提供序列号及故障描述申请检测", "不能未检测就承诺免费维修"]),
    (69, "warranty", "电池用久了续航变差，一年内是不是一定免费换新？", [("warranty.md", "免费保修的例外", 3)], ["正常磨损或耗材衰减是否覆盖以商品页和凭证为准", "不能仅凭通用一年保修承诺免费换新"]),
    (70, "warranty", "电池自然衰减需要付费换电池的话，具体收我多少钱？", [], ["知识库没有该商品电池更换价格；报价须经检测后展示，不能编造金额"]),
    (71, "repair", "设备寄修收到了，初检一般几天？如果要收钱能不问我就动手吗？", [(BASE, "维修申请与进度", 3), ("warranty.md", "初检、报价与用户选择", 3)], ["售后收货后通常3个工作日内初检", "付费维修先展示故障结论和报价并获确认", "未确认不能实施付费维修"]),
    (72, "repair", "报价太高我没同意，还会继续修吗？可以原样寄回来吗？", [("warranty.md", "初检、报价与用户选择", 3)], ["不同意报价时不实施付费维修", "可以申请按原状态寄回"]),
    (73, "repair", "修好寄回20天同一个毛病又犯了，还要再付同一项目的钱吗？", [("warranty.md", "维修后同故障复检", 3)], ["返还后30个自然日内同故障可凭维修记录复检", "复检确认原维修未解决时不重复收取同项目费用", "须先确认是否同一故障"]),
    (74, "repair", "刚修完又摔坏了，30天内能按同故障免费复检吗？", [("warranty.md", "维修后同故障复检", 3), ("warranty.md", "免费保修的例外", 2)], ["人为摔坏或新故障不属于原维修未解决", "仍需重新检测并按保修及报价规则处理"]),
    (75, "repair", "手机寄修期间你们能免费借我备用机吗，最多借几天？", [], ["知识库未规定维修期间备用机、费用或借用时长，应说明无法确认"]),
    (76, "invoice", "订单完成30天想开电子普票，抬头还要先核什么？", [(BASE, "发票服务", 3), ("finance.md", "发票、红冲与退款", 2)], ["订单完成45天内可申请电子普通发票", "提交前需校验抬头和税号格式"]),
    (77, "invoice", "专票税号写错已经开出，能直接在线改掉吗？", [(BASE, "发票服务", 3), ("finance.md", "发票、红冲与退款", 2)], ["已开增值税专用发票不能直接修改", "先申请红冲并经财务审核"]),
    (78, "invoice", "订单退了钱，之前开的专票肯定不用处理了吧？", [("finance.md", "发票、红冲与退款", 3), (BASE, "发票服务", 2)], ["退款后原发票可能需要作废或红冲", "发票处理与退款到账不是同一状态"]),
    (79, "invoice", "订单完成两个月了，现在补开专票走哪个入口、审核几天？", [], ["知识库只说明完成后45天内的申请规则，未提供两个月后的补开入口或审核时长"]),
    (80, "invoice", "专票红冲审核过了，是不是说明银行卡退款已经到账？", [("finance.md", "发票、红冲与退款", 3), ("finance.md", "退款发起与渠道时效", 3)], ["发票红冲不代表退款到账", "银行卡退款以仓库验收后发起，通常3至7个工作日"]),
    (81, "payment", "支付失败却扣钱，我再付一笔保险吗？", [("finance.md", "支付失败与重复扣款", 3), (BASE, "支付与重复扣款", 2)], ["先等待通常1个工作日的渠道对账", "不应立即重复支付"]),
    (82, "payment", "同一订单扣了两次，只给你一张流水截图够吗？能要我完整卡号吗？", [("finance.md", "支付失败与重复扣款", 3), (BASE, "账户与隐私", 3)], ["应保留两笔支付流水并建支付异常工单", "不得索要完整银行卡号、密码或验证码"]),
    (83, "payment", "余额和第三方一起付，余额退回了但微信没到，该按哪个时效查？", [("finance.md", "多支付方式退款核对", 3), ("finance.md", "退款发起与渠道时效", 3)], ["两个渠道分别核对原路退款", "第三方支付通常1至3个工作日", "仅余额到账不代表全额到账"]),
    (84, "payment", "礼品卡和券能叠加吗？礼品卡余额退回要多久？", [], ["知识库没有礼品卡叠加或余额退款时效规则，应拒答并建议人工核实"]),
    (85, "payment", "重复扣款明天一定全退吗？要是没退赔我多少违约金？", [], ["知识库只说明通常1个工作日对账，不承诺明日全退或违约金金额"]),
    (86, "ticket", "物流异常单说12小时响应，承运商联系却说24小时，哪个是找到包裹的时间？", [("tickets.md", "工单类别与响应时效", 3), ("shipping.md", "延迟与无轨迹核查", 3)], ["物流异常工单目标响应12小时", "24小时内联系承运商核查", "两者都不等于查清包裹的时间"]),
    (87, "ticket", "同一工单我补了新照片，重新点提交能给我新单号并优先吗？", [("tickets.md", "补充证据与升级", 3), ("tickets.md", "重复提交与幂等", 3)], ["同一问题应补充原工单", "同幂等键重复返回原工单编号", "重复建单不能提高优先级"]),
    (88, "ticket", "我只问了订单在哪，系统可以不问我就建售后工单吗？", [("tickets.md", "工单身份校验与确认", 3), (BASE, "账户与隐私", 2)], ["查询订单先验证订单号和手机号后四位", "仅查询不等于同意建单", "创建写入工单须展示摘要并明确确认"]),
    (89, "ticket", "客服处理结果不满意还涉及人身安全，继续重复建单还是马上升级？", [("tickets.md", "补充证据与升级", 3), (BASE, "投诉与服务时效", 2)], ["应在原工单补充证据并申请升级", "涉及人身安全应立即转人工", "不靠重复建单提高优先级"]),
    (90, "ticket", "投诉升级以后固定能赔我多少钱，按什么金额标准？", [], ["知识库没有投诉升级后的固定补偿金额或计算标准，应明确无法确认"]),
]


def main() -> int:
    if OUTPUT.exists():
        raise SystemExit("dataset-v2.json already exists; version the dataset instead of overwriting")
    old = json.loads(OLD.read_text(encoding="utf-8"))
    sections = {(s.source, s.title): s.content for s in load_policy_sections(CORPUS)}
    chunks: dict[tuple[str, str], list[str]] = {}
    for chunk in load_policy_chunks(CORPUS):
        key = (str(chunk.metadata["source"]), str(chunk.metadata["title"]))
        chunks.setdefault(key, []).append(str(chunk.metadata["chunk_id"]))
    if any(len(ids) != 1 for ids in chunks.values()):
        raise ValueError("v2 ground truth requires one chunk per section; re-label after re-chunking")
    old_group = {f"rag-{n:03}": group for group, nums in OLD_GROUPS.items() for n in nums}
    if len(old_group) != 40:
        raise ValueError("Every v1 case needs one scenario group")
    cases = []
    old_source = "data/policies/customer_service_policy.md"
    base_source = (CORPUS / BASE).as_posix()
    for original in old["cases"]:
        case = copy.deepcopy(original)
        group = old_group[case["id"]]
        case["split"] = GROUP_SPLIT[group]
        case["scenario_group"] = group
        case["annotation_origin"] = "v1_label_copied_without_fact_changes; source remapped to byte-identical base-policy.md"
        case["relevant_documents"] = [
            {**doc, "source": base_source} for doc in case["relevant_documents"]
        ]
        case["relevance_scores"] = {
            key.replace(old_source, base_source, 1): grade
            for key, grade in case["relevance_scores"].items()
        }
        case["relevant_chunks"] = [
            {"source": doc["source"], "section": doc["section"], "chunk_id": chunks[(doc["source"], doc["section"])][0]}
            for doc in case["relevant_documents"]
        ]
        case["evidence_requirements"] = {
            "all_expected_facts_required": True,
            "required_chunk_ids": [item["chunk_id"] for item in case["relevant_chunks"]],
        }
        cases.append(case)
    for number, group, question, sources, facts in NEW_CASES:
        docs = []
        relevant_chunks = []
        scores = {}
        for filename, section, grade in sources:
            source = (CORPUS / filename).as_posix()
            key = (source, section)
            if key not in sections:
                raise ValueError(f"Unknown manually labelled section: {key}")
            docs.append({"source": source, "section": section, "evidence_quote": sections[key]})
            relevant_chunks.append({"source": source, "section": section, "chunk_id": chunks[key][0]})
            scores[f"{source}#{section}"] = grade
        cases.append(
            {
                "id": f"rag-{number:03}",
                "query": question,
                "relevant_documents": docs,
                "relevance_scores": scores,
                "relevant_chunks": relevant_chunks,
                "expected_answer": "；".join(facts),
                "expected_facts": facts,
                "should_abstain": not sources,
                "category": group,
                "scenario_group": group,
                "split": GROUP_SPLIT[group],
                "evidence_requirements": {
                    "all_expected_facts_required": True,
                    "required_chunk_ids": [item["chunk_id"] for item in relevant_chunks],
                    "missing_information_requires_abstention": not sources,
                },
                "annotation_origin": "assistant_authored_against_policy_text; not_independently_human_reviewed",
            }
        )
    dataset = {
        "version": "ordercare-rag-v2.0",
        "policy_sha256": digest(CORPUS),
        "previous_version": old["version"],
        "previous_dataset_sha256": digest(OLD),
        "annotation_method": "新增50题由开发助手逐条对照模拟政策编写；未用待评测检索器或DeepSeek生成Ground Truth，尚未经独立人工复核。旧40题事实标签不变，仅将来源映射至字节相同的基础文档并按场景组重划split。",
        "split_rule": "按场景组划分dev/test；同一场景组只在一侧，避免近似问法跨集。",
        "relevance_scale": old["relevance_scale"],
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        load_dataset(OUTPUT, CORPUS)
    except Exception:
        OUTPUT.unlink()
        raise
    print(
        f"v2 dataset: {len(cases)} cases, {sum(c['should_abstain'] for c in cases)} no-answer; "
        f"policy_sha256={dataset['policy_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
