"""Append five evidence-first query pairs to the frozen v4 challenge set."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_support.rag import load_policy_chunks  # noqa: E402
from evaluation.rag import digest, load_dataset  # noqa: E402

POLICY = Path("data/policies/v3")
BASE = Path("data/evaluation/rag/dataset-v4.json")
OUTPUT = Path("data/evaluation/rag/dataset-v5.json")

# Evidence and intent are fixed before ranking comparison. Last two entries are
# formal and colloquial phrasings of the same question.
PAIRS = [
    ("account-security", "核心规则", "发现异常登录应尽快通过官方账户入口修改凭证并检查订单；客服不会索要密码、支付验证码或完整银行卡信息。", "发现异常登录后，应通过官方账户入口修改凭证并检查订单。", "账户疑似被他人登录，应先采取什么措施？", "有人偷偷上我号，咋办？", "privacy"),
    ("repair-review", "核心规则", "收费项目须在用户确认后继续执行。", "维修收费项目须在用户确认后才继续执行。", "维修产生费用前是否需要用户同意？", "修东西要加钱，得先问我吗？", "repair"),
    ("privacy-access", "核心规则", "用户完成账户身份核验后可申请查询或更正本人信息；客服仅收集完成该事项所需的资料。", "完成账户身份核验后，可以申请更正本人信息。", "账户本人信息有误时，如何申请更正？", "账号资料填错，咋改？", "privacy"),
    ("damage-evidence", "核心规则", "按问题类型提交商品、包装或故障照片视频。", "按问题类型提交商品、包装或故障的照片或视频。", "商品破损申请售后，须提交哪些材料？", "东西碎了，拍啥？", "return"),
    ("ticket-followup", "核心规则", "用户可在原工单补充照片、物流信息或说明；客服将材料关联至同一问题记录。", "可在原工单补充照片，客服会关联到同一问题记录。", "已受理工单新增照片时，应如何补充材料？", "原单补图怎么弄？", "ticket"),
]


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Versioned dataset already exists: {OUTPUT}")
    base = load_dataset(BASE, POLICY)
    chunks = load_policy_chunks(POLICY)
    old_sources = {
        doc["source"] for case in base["cases"] for doc in case["relevant_documents"]
    }
    cases = list(base["cases"])
    for index, (file, section, quote, answer, formal, colloquial, category) in enumerate(PAIRS, 21):
        source = (POLICY / f"{file}.md").as_posix()
        if source in old_sources:
            raise ValueError(f"Gold source already used by v4: {source}")
        matches = [
            chunk for chunk in chunks if chunk.metadata["source"] == source
            and chunk.metadata["title"] == section and quote in chunk.page_content
            and chunk.metadata["is_retrievable"]
        ]
        if len(matches) != 1:
            raise ValueError(f"Gold must identify one retrievable chunk: {source}#{section}")
        chunk_id = str(matches[0].metadata["chunk_id"])
        gold = {"source": source, "section": section, "evidence_quote": quote}
        for style, query in (("formal", formal), ("colloquial", colloquial)):
            cases.append({
                "id": f"pair-{index:02d}-{style}", "pair_id": f"pair-{index:02d}",
                "query": query, "query_style": style, "scenario_group": f"pair-{index:02d}",
                "split": "dev" if index <= 23 else "test", "category": category,
                "subset": "rewrite_challenge", "should_abstain": False,
                "expected_answer": answer, "expected_facts": [answer],
                "relevant_documents": [gold],
                "relevance_scores": {f"{source}#{section}": 3},
                "relevant_chunks": [{"source": source, "section": section, "chunk_id": chunk_id}],
                "evidence_requirements": {
                    "all_expected_facts_required": True, "required_chunk_ids": [chunk_id],
                    "missing_information_requires_abstention": False,
                },
            })
    dataset = {
        "version": "ordercare-rag-v5.0", "policy_sha256": digest(POLICY),
        "base_dataset_sha256": digest(BASE),
        "annotation_method": "Evidence-first paired challenge set; new query variants screened against retrieval results.",
        "split_rule": "v4 first 40 frozen; three new pairs in dev, two in test. New pairs are performance-screened, not an unbiased holdout.",
        "cases": cases,
    }
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load_dataset(OUTPUT, POLICY)
    if json.loads(OUTPUT.read_text(encoding="utf-8"))["cases"][:40] != base["cases"]:
        raise AssertionError("v4 cases changed")
    print(f"Built {len(cases)} cases from 25 pairs; v4 cases preserved")


if __name__ == "__main__":
    main()
