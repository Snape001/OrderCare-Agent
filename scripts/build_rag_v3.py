"""Build the versioned 36-document policy corpus and 40-case rewrite benchmark."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_support.policy import load_policy_sections  # noqa: E402
from customer_support.rag import load_policy_chunks  # noqa: E402
from evaluation.rag import digest, load_dataset  # noqa: E402

SOURCE = Path("data/policies/v2")
CORPUS = Path("data/policies/v3")
OUTPUT = Path("data/evaluation/rag/dataset-v3.json")

# Each new file is a focused policy document. All rules are simulated and should
# remain consistent with the original six policies in this corpus.
EXTRA_POLICIES: list[tuple[str, str, str, str, str, str]] = [
    (
        "order-edit",
        "订单信息修改政策",
        "已支付订单的商品、数量及备注变更。",
        "订单进入拣货前可提交修改申请；系统显示已拣货或已发货时不能保证修改成功。修改结果以订单页面更新为准。",
        "客服核对订单状态和拟修改字段，再提交变更请求；成功后向用户复述变更结果。",
        "促销资格、库存或价格已变化时，修改可能被拒绝；不得先承诺一定可以修改。",
    ),
    (
        "order-cancel",
        "订单取消政策",
        "订单取消申请及取消后状态确认。",
        "未支付订单可在订单页面取消；已支付订单须先核对履约状态。进入拣货或发货流程后，取消请求可能无法拦截。",
        "提交取消请求后等待页面状态更新；若包裹已发出，按物流拦截或签收后退货路径处理。",
        "取消申请不等于退款完成；是否退款及金额须根据支付和促销明细核算。",
    ),
    (
        "address-change",
        "收货信息变更政策",
        "订单配送前的地址和联系方式更正。",
        "仅在订单尚未交运且身份核验通过时受理地址更正。为保护隐私，客服不得向未经核验者披露现有完整收货信息。",
        "核对订单号及账户验证信息后提交修改；用户应在页面确认更新结果。",
        "已交运包裹由承运商配送，平台不能保证改址成功；不得承诺一定可以转寄。",
    ),
    (
        "return-eligibility",
        "退货资格核验细则",
        "普通商品及特殊商品的退货申请资格核验。",
        "无理由退货须同时满足适用期限、商品完好和附件齐全等要求。定制、已激活数字内容等特殊商品按基础政策限制处理。",
        "先核对商品类型、签收时间和商品状态，再提交对应申请；核验结果以售后页面为准。",
        "质量问题按质量售后流程核验，不因无理由退货限制而自动排除；核验前不承诺退款。",
    ),
    (
        "return-packing",
        "退货寄回与包装政策",
        "退货审核通过后的寄回准备及包裹保护。",
        "按审核页面提供的地址和要求寄回商品、配件及应退赠品；寄出前建议拍摄商品状态、配件和包裹照片。",
        "保存寄件凭证和物流单号，并在售后页面补充物流信息；包裹送达后等待仓库验收。",
        "不得寄送审核范围外的个人物品；寄回包裹尚未验收不代表退款已经发起。",
    ),
    (
        "return-inspection",
        "退货验收政策",
        "仓库收到退货后的商品核验及结果通知。",
        "仓库按商品、配件、赠品和售后申请记录核对退回内容；验收通过后才进入相应退款流程。",
        "用户可在售后页面查看验收状态；状态异常时提供订单号和寄件凭证申请查询。",
        "验收不通过时按页面说明补充材料或申请人工复核；不能仅凭物流显示签收认定验收通过。",
    ),
    (
        "shipping-tracking",
        "物流轨迹查询政策",
        "已发货订单的物流状态查询和信息核对。",
        "用户可通过订单页查看承运商和物流单号；轨迹长时间未更新时，客服按物流异常规则登记核查。",
        "核对订单与包裹对应关系后说明最近一条可确认轨迹，并告知后续核查方式。",
        "预计送达信息用于参考，不代表保证到达时间或自动退款条件。",
    ),
    (
        "shipping-exception",
        "配送异常受理政策",
        "延迟、无轨迹、疑似丢件等配送异常。",
        "超过政策规定的无轨迹或预计送达节点时，可提交物流异常工单；是否丢件须由承运商核实。",
        "记录包裹单号、已知轨迹和用户描述，创建异常核查并同步受理状态。",
        "核查期间不得将疑似丢件表述为已确认丢件，也不得预先承诺赔付或退款。",
    ),
    (
        "delivery-proof",
        "签收凭证与代收核对政策",
        "显示签收但用户未实际收到包裹的核查。",
        "先核对对应包裹的签收记录、投递位置及是否由他人代收；多包裹订单须逐件确认。",
        "通过身份核验后收集包裹单号和用户描述，再按物流异常流程联系承运商核查。",
        "未经核验不得披露代收人身份或完整地址；显示签收本身不等于争议已经解决。",
    ),
    (
        "payment-status",
        "支付状态核对政策",
        "支付结果未同步、付款处理中等状态查询。",
        "页面显示未支付但账户出现扣款时，先核对订单支付状态和渠道流水；状态未确认前不得引导用户重复支付。",
        "提交订单号、支付时间和渠道名称核查；核对完成后再说明订单或款项状态。",
        "核查结果以支付渠道和订单记录为准，不承诺未确认款项的固定到账时间。",
    ),
    (
        "duplicate-charge",
        "重复扣款核查政策",
        "同一订单疑似重复扣款的处理。",
        "同一订单出现多笔扣款记录时，先逐笔核对支付流水和订单状态；系统对账结果未出前不认定重复收费。",
        "用户提供订单号、扣款时间及支付渠道，由客服登记支付异常核查并反馈状态。",
        "核查时效不等同于退款到账时效；未核实前不得承诺全额退款、违约金或赔偿金额。",
    ),
    (
        "refund-status",
        "退款状态查询政策",
        "已通过退款申请的处理状态查询。",
        "退款是否已发起以订单和售后页面状态为准；仓库验收、退款审批与支付渠道到账是不同环节。",
        "核对退款申请时间、状态和原支付渠道；超过对应处理节点时提交人工查询。",
        "仅凭寄回物流或审核申请不能判断退款已经到账；不同支付渠道进度可能不同。",
    ),
    (
        "damage-evidence",
        "商品破损与质量证据政策",
        "商品破损、故障和质量售后的证据要求。",
        "描述问题发生时间、商品状态和可复现现象；按问题类型提交商品、包装或故障照片视频。必要时可要求检测。",
        "客服核对证据是否对应订单商品，材料不足时请用户补充，再提交质量售后核验。",
        "提交证据不等于确认责任；核验前不承诺退款、换货或免费维修。",
    ),
    (
        "missing-items",
        "缺件与错发核验政策",
        "包裹缺少商品、配件或收到错误商品的核验。",
        "按基础政策规定的时限反馈，并提供外包装、包裹标签、实际收到商品及缺失内容的照片。",
        "核对订单明细与包裹信息，确认问题后按补发或换货路径提交处理。",
        "缺件或错发尚未核验时不直接承诺补发；已完成退款的问题不重复获得同一补偿。",
    ),
    (
        "exchange-fulfillment",
        "换货与补发履约政策",
        "审核通过后的换货或缺件补发执行。",
        "换货和补发须以审核结果、商品库存及履约信息为准；同一问题不得重复完成退款与补发。",
        "确认处理方式、收件信息和物流状态后创建履约记录，并在页面更新结果。",
        "提交申请不等于库存锁定或已发出；不得承诺未经确认的发货日期。",
    ),
    (
        "warranty-scope",
        "保修范围核验政策",
        "保修期内商品的保修资格和责任核验。",
        "依据商品类别、购买凭证、故障描述及商品状态核对保修资格；人为损坏、进液等情况需单独判断。",
        "用户提交订单或凭证及故障材料，客服按商品规则核验后说明可选处理路径。",
        "保修期内不代表所有故障均免费；核验结果未出前不能确认费用或维修结论。",
    ),
    (
        "repair-intake",
        "维修申请受理政策",
        "商品送修、检测和维修申请材料。",
        "受理时记录订单或购买凭证、商品型号、故障现象和联系方式；涉及寄修时按页面指引准备商品。",
        "材料齐全后登记维修申请；用户可按受理页面查询状态或补充信息。",
        "受理不表示检测完成或维修已批准；不得编造服务网点地址、费用或固定完成日期。",
    ),
    (
        "repair-review",
        "维修检测与复核政策",
        "维修检测结论、费用确认和争议复核。",
        "检测机构根据实际故障判断维修方案及是否产生费用；收费项目须在用户确认后继续执行。",
        "客服向用户说明检测状态和可选方案；对结论有异议时可补充材料申请复核。",
        "未确认的检测结果、报价和完成时间不得作为确定承诺。",
    ),
    (
        "invoice-request",
        "发票申请政策",
        "订单发票申请及抬头、类型信息核对。",
        "用户按订单页面可选类型填写抬头、税号等必要信息；专用发票所需资料以页面提示为准。",
        "提交前核对订单、发票类型和接收信息；开具状态以页面记录为准。",
        "订单状态或适用条件不满足时可能无法申请；政策未明确的历史订单期限须人工核实。",
    ),
    (
        "invoice-change",
        "发票信息更正政策",
        "发票开具前后信息错误的更正申请。",
        "开具前可按页面流程修改信息；已开具发票需先核对发票状态，再申请作废或更正。",
        "提交订单号、发票号码及需更正字段，由客服核验后告知可用流程。",
        "不得自行修改已开具发票；是否可更正取决于票据状态及适用规则。",
    ),
    (
        "invoice-status",
        "发票状态查询政策",
        "发票申请、开具和发送状态查询。",
        "订单页显示的申请状态、开具状态和发送状态分别核对；电子发票按页面提供的入口获取。",
        "用户提供订单号和发票申请信息，客服检查当前状态并反馈下一步操作。",
        "申请已提交不等于发票已开具；政策未列明的历史补开期限不作推定。",
    ),
    (
        "coupon-eligibility",
        "优惠券适用条件政策",
        "优惠券的使用门槛、商品范围及有效状态。",
        "结算时以优惠券页面显示的有效期、门槛、适用商品和可用范围为准；优惠不可用时核对具体限制。",
        "用户提供券名称或页面提示，客服按券规则解释适用条件。",
        "未展示的券面金额、发放数量或未来活动安排不作承诺。",
    ),
    (
        "promotion-stacking",
        "促销叠加与优惠计算政策",
        "多项促销同时使用及结算优惠展示。",
        "促销能否叠加以结算页面实际展示为准；订单优惠按活动规则分摊到商品明细。",
        "下单前查看结算明细；发生部分退货时按保留商品和活动门槛重新核算。",
        "不同活动不可默认叠加；页面未显示的优惠金额不得口头保证。",
    ),
    (
        "promotion-refund",
        "促销订单退款核算政策",
        "促销订单取消或部分退款后的优惠调整。",
        "部分退款时按实际支付金额和活动条件核算；退货后不再满足门槛的订单可能重新分摊优惠。",
        "退款审批明细列出核算结果；对金额有疑问时可申请人工复核。",
        "取消未支付订单、整单退款和部分退货的优惠处理可能不同，不统一推定券返还结果。",
    ),
    (
        "ticket-intake",
        "客服工单创建政策",
        "售后问题转工单时的信息、确认和去重要求。",
        "创建工单前核验必要订单信息并向用户展示工单摘要；需要写入或提交时须取得明确确认。",
        "记录问题类型、订单或包裹标识及已提供证据；重复提交同一问题时关联已有工单。",
        "仅查询订单不代表同意创建工单；重复建单不提升处理优先级。",
    ),
    (
        "ticket-followup",
        "工单补充材料与进度政策",
        "已有工单的材料补充和进度查询。",
        "用户可在原工单补充照片、物流信息或说明；客服将材料关联至同一问题记录。",
        "查询进度时提供原工单编号；处理节点按工单页面状态反馈。",
        "补充材料不自动缩短处理时间，也不等于工单已解决。",
    ),
    (
        "complaint-escalation",
        "投诉升级与人工介入政策",
        "投诉复核、升级和紧急人工介入。",
        "对处理结果有异议可补充事实和证据申请升级；涉及人身安全或紧急风险时转人工优先处理。",
        "客服记录用户诉求、原工单及证据，说明升级受理状态和后续联系渠道。",
        "升级只表示复核流程，不代表固定处理结论、补偿金额或完成时限。",
    ),
    (
        "privacy-access",
        "个人信息查询与更正政策",
        "账户个人信息的查询、更正申请及身份核验。",
        "用户完成账户身份核验后可申请查询或更正本人信息；客服仅收集完成该事项所需的资料。",
        "核对账户主体和需处理字段，提交申请并通过页面或已验证渠道反馈进度。",
        "不得向未核验者披露完整联系方式、地址或其他账户资料。",
    ),
    (
        "privacy-deletion",
        "账户注销与信息删除政策",
        "账户注销及个人信息删除申请。",
        "用户可通过账户页面发起注销或删除申请；存在未完成订单、售后或依法需保留记录时，申请可能暂缓或受限。",
        "完成身份核验后提交申请，先处理页面列出的未完成事项，再查看申请状态。",
        "提交申请不等于立即删除所有记录；依法需保留的信息按适用规则处理。",
    ),
    (
        "account-security",
        "账户安全与异常登录政策",
        "账户异常登录、凭证保护和安全核验。",
        "发现异常登录应尽快通过官方账户入口修改凭证并检查订单；客服不会索要密码、支付验证码或完整银行卡信息。",
        "通过已验证渠道联系支持人员，描述异常时间和影响范围；涉及订单风险时同步核验订单状态。",
        "不得通过聊天发送密码或验证码；未经核验的身份请求不执行账户敏感操作。",
    ),
]

PAIRS = [
    # slug, split, formal, colloquial
    ("order-edit", "dev", "已支付订单尚未拣货，商品数量如何申请修改？", "单付过钱还没拣货，想改件数咋办？"),
    ("return-packing", "dev", "退货审核通过后，寄回商品及配件应如何准备？", "退货过审了，东西和配件怎么寄回去？"),
    ("shipping-exception", "dev", "包裹超过预计送达时间仍未到，应如何申请物流异常核查？", "快递过了预计时间还没到，咋让你们查？"),
    ("payment-status", "dev", "订单显示未支付但账户已扣款，应如何核对支付状态？", "钱扣了订单还说没付，这要怎么查？"),
    ("warranty-scope", "dev", "保修期内商品出现故障，如何核验保修资格？", "东西还在保修期里坏了，怎么知道能不能保？"),
    ("repair-intake", "dev", "申请商品维修时需提交哪些受理材料？", "东西要拿去修，得先给你们啥资料？"),
    ("invoice-change", "dev", "已开具的发票信息有误，应如何申请更正？", "票开好了才发现信息错了，怎么改啊？"),
    ("coupon-eligibility", "dev", "结算时优惠券显示不可用，应核对哪些适用条件？", "结账时券用不了，得看哪几个条件？"),
    ("address-change", "test", "订单尚未交运，如何申请修改收货地址？", "包裹还没交给快递，收货地址咋改？"),
    ("return-inspection", "test", "退货包裹送达仓库，是否就代表已验收通过？", "退回去的包裹到仓库了，就算验过了吗？"),
    ("delivery-proof", "test", "物流显示签收但本人未收到，应核查哪些签收信息？", "快递写着签收了我没拿到，要查啥？"),
    ("duplicate-charge", "test", "同一订单出现两笔扣款记录，应如何处理？", "同一单扣了两次钱，咋处理？"),
    ("exchange-fulfillment", "test", "换货申请审核通过后，还需根据哪些条件执行换货？", "换货过审了，还得看啥才能换？"),
    ("complaint-escalation", "test", "对原工单处理结果有异议，应如何申请投诉升级？", "原工单处理我不认可，怎么往上反映？"),
    ("promotion-refund", "test", "促销订单部分退货后，优惠和退款金额如何核算？", "活动单退一部分，优惠和退款钱怎么算？"),
    ("privacy-deletion", "test", "账户仍有未完成售后时，如何申请删除个人信息？", "售后还没完，我想删账号资料咋办？"),
]

NO_ANSWER_PAIRS = [
    ("dev", "物流异常工单受理后，固定赔偿金额是多少？", "快递出问题立了单，固定赔我多少钱？", "政策未规定物流异常的固定赔偿金额。"),
    ("dev", "维修申请受理后，保证几天内完成维修？", "修东西收下了，包几天修好？", "政策未规定保证完成维修的天数。"),
    ("test", "优惠券活动下个月固定发放多少张？", "下个月优惠券肯定发几张啊？", "政策未规定下个月优惠券发放数量。"),
    ("test", "账户删除申请提交后，固定几小时内完成全部删除？", "点了删账号，包几个小时全删完？", "政策未规定完成全部删除的固定小时数。"),
]


def normalized_legacy(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    title = next((line for line in raw.splitlines() if line.startswith("# ")), f"# {path.stem}")
    sections = load_policy_sections(path)
    useful = [section for section in sections if section.title not in {"规则", "免责声明", "目录"}]
    return f"{title}\n\n" + "\n\n".join(
        f"## {section.title}\n\n{section.content}" for section in useful
    ) + "\n"


def write_corpus() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    for source in sorted(SOURCE.glob("*.md")):
        (CORPUS / source.name).write_text(normalized_legacy(source), encoding="utf-8")
    for slug, title, scope, rule, flow, exceptions in EXTRA_POLICIES:
        # Keep distinct business boundaries with their rule; repeated generic
        # disclaimers and navigation-only scope paragraphs do not form chunks.
        useful_boundaries = {
            "order-edit", "order-cancel", "address-change", "return-eligibility",
            "return-inspection", "delivery-proof", "payment-status", "duplicate-charge",
            "refund-status", "missing-items", "warranty-scope", "repair-review",
            "invoice-change", "promotion-refund", "privacy-deletion",
        }
        core = f"{rule} {exceptions}" if slug in useful_boundaries else rule
        text = f"# {title}\n\n## 核心规则\n\n{core}\n\n{flow}\n"
        (CORPUS / f"{slug}.md").write_text(text, encoding="utf-8")


def build_dataset() -> dict[str, Any]:
    policies = {slug: (rule, title) for slug, title, _scope, rule, _flow, _exceptions in EXTRA_POLICIES}
    chunks = load_policy_chunks(CORPUS)
    cases: list[dict[str, Any]] = []

    def add_pair(pair_id: str, split: str, formal: str, colloquial: str,
                 slug: str | None, answer: str) -> None:
        source = (CORPUS / f"{slug}.md").as_posix() if slug else None
        evidence = [
            chunk for chunk in chunks
            if chunk.metadata["source"] == source
            and chunk.metadata["title"] == "核心规则"
            and answer in chunk.page_content
        ] if source else []
        if source and len(evidence) != 1:
            raise ValueError(f"Gold evidence must fit exactly one chunk: {slug}")
        docs = [{"source": source, "section": "核心规则", "evidence_quote": answer}] if source else []
        labels = [{"source": source, "section": "核心规则",
                   "chunk_id": evidence[0].metadata["chunk_id"]}] if source else []
        for style, query in (("formal", formal), ("colloquial", colloquial)):
            cases.append({
                "id": f"{pair_id}-{style}", "pair_id": pair_id, "query": query,
                "query_style": style, "scenario_group": pair_id, "split": split,
                "category": slug or "unsupported", "should_abstain": source is None,
                "expected_answer": answer, "expected_facts": [answer],
                "relevant_documents": docs,
                "relevance_scores": {f"{source}#核心规则": 3} if source else {},
                "relevant_chunks": labels,
                "evidence_requirements": {
                    "all_expected_facts_required": True,
                    "required_chunk_ids": [item["chunk_id"] for item in labels],
                    "missing_information_requires_abstention": source is None,
                },
            })

    for index, (slug, split, formal, colloquial) in enumerate(PAIRS, 1):
        add_pair(f"pair-{index:02}", split, formal, colloquial, slug, policies[slug][0])
    for index, (split, formal, colloquial, answer) in enumerate(NO_ANSWER_PAIRS, 17):
        add_pair(f"pair-{index:02}", split, formal, colloquial, None, answer)
    if len(cases) != 40 or len({c["relevant_documents"][0]["source"] for c in cases
                              if c["relevant_documents"]}) < 12:
        raise ValueError("v3 pairs must cover at least 12 detailed policy documents")
    return {
        "version": "ordercare-rag-v3.0",
        "policy_sha256": digest(CORPUS),
        "annotation_method": "20 hand-authored paired intents; formal and colloquial variants share answers and exact policy chunks. Independent human review is recommended.",
        "split_rule": "Pairs stay within a split; each split has 8 answerable and 2 no-answer pairs.",
        "relevance_scale": {"3": "直接回答主要诉求", "2": "补充事实", "1": "背景", "0": "不支持"},
        "query_style_values": {"formal": "规范直问", "colloquial": "自然口语或轻度省略"},
        "cases": cases,
    }


def main() -> int:
    write_corpus()
    files = sorted(CORPUS.glob("*.md"))
    if len(files) != 36:
        raise ValueError(f"Expected 36 policy files, found {len(files)}")
    data = build_dataset()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        load_dataset(OUTPUT, CORPUS)
    except Exception:
        OUTPUT.unlink(missing_ok=True)
        raise
    print(
        f"v3 corpus: {len(files)} policies; dataset: {len(data['cases'])} cases, "
        f"{sum(case['should_abstain'] for case in data['cases'])} no-answer; "
        f"policy_sha256={data['policy_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
