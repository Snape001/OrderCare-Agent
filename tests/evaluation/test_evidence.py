import copy
import json

import pytest
from pydantic import ValidationError

from evaluation.evidence import (
    AuditedFact,
    EvidenceAudit,
    audit_metrics,
    context_digest,
    evidence_messages,
    reviewed_metrics,
)
from evaluation.generation import section_covered
from evaluation.generation_report import compare_generation, prepare_report


def evidence_case():
    return {
        "query": "退款多久到账？",
        "expected_facts": ["仓库验收通过后发起退款", "银行卡3至7个工作日"],
    }


def test_independent_evidence_has_no_generated_answer():
    messages = evidence_messages(evidence_case(), [])
    data = json.loads(messages[1].content)
    assert set(data) == {"query", "expected_facts", "context"}
    assert "answer" not in data


def test_partial_evidence_is_not_fully_sufficient():
    context = [{"evidence_id": "E1", "content": "银行卡3至7个工作日"}]
    audit = EvidenceAudit(
        facts=[
            AuditedFact(
                reason="缺少验收条件", fact_index=0, evidence_id="", quote="", verdict="missing"
            ),
            AuditedFact(
                reason="明确到账时效",
                fact_index=1,
                evidence_id="E1",
                quote="银行卡3至7个工作日",
                verdict="sufficient",
            ),
        ],
        reason="只有到账时效",
    )
    metrics = audit_metrics(evidence_case(), context, audit)
    assert metrics["evidence_sufficiency"] == 0
    assert metrics["fact_evidence_coverage"] == 0.5
    assert metrics["missing_facts"] == ["仓库验收通过后发起退款"]
    audit.facts[1].quote = "编造证据"
    assert audit_metrics(evidence_case(), context, audit)["fact_evidence_coverage"] is None


def test_evidence_missing_indexes_and_invalid_verdict_fail():
    with pytest.raises(ValueError, match="indexes"):
        audit_metrics(evidence_case(), [], EvidenceAudit(facts=[], reason=""))
    with pytest.raises(ValidationError):
        AuditedFact(reason="", fact_index=0, evidence_id="", quote="", verdict="probably")


def test_review_distinguishes_judge_omission_from_missing_citation():
    row = {
        "generation": {"answer": "银行卡3至7个工作日，来源：policy.md 退款"},
        "context": [{"source": "policy.md", "title": "退款"}],
        "judge": {"parsed": {"answer_claims": [{"claim": "银行卡3至7个工作日"}], "citations": []}},
        "metrics": {"citation_support_rate": 0, "answer_correctness": 1, "faithfulness": 1},
    }
    metrics, warnings = reviewed_metrics(row)
    assert metrics["citation_support_rate"] is None and warnings
    row["generation"]["answer"] = "银行卡3至7个工作日"
    assert reviewed_metrics(row)[0]["citation_support_rate"] == 0
    row["judge"]["parsed"]["answer_claims"][0]["claim"] = "系统已完成退款"
    metrics, warnings = reviewed_metrics(row)
    assert metrics["answer_correctness"] is None
    assert metrics["faithfulness"] is None
    assert warnings


def test_context_hash_ignores_ranking_scores_but_not_content():
    context = [{"evidence_id": "E1", "source": "p", "title": "t", "content": "abc", "score": 0.9}]
    revised = copy.deepcopy(context)
    revised[0]["score"] = 0.7
    assert context_digest(context) == context_digest(revised)
    revised[0]["content"] = "abd"
    assert context_digest(context) != context_digest(revised)


def test_chunk_coverage_handles_overlapping_chunks():
    assert section_covered("abcdef", ["abcd", "cdef"])
    assert not section_covered("abcdef", ["abc", "ef"])
    assert not section_covered("", [])


def test_audit_cannot_be_reused_with_different_context():
    row = {
        "id": "a",
        "context": [{"evidence_id": "E1", "source": "p", "title": "t", "content": "new"}],
    }
    report = {"generation_manifest": {"dataset_sha256": "gold"}, "runs": [{"cases": [row]}]}
    audit = {"dataset_sha256": "gold", "cases": [{"id": "a", "context_sha256": "old"}]}
    with pytest.raises(ValueError, match="context differs"):
        prepare_report(report, audit, {})
    audit["dataset_sha256"] = "changed"
    with pytest.raises(ValueError, match="dataset mismatch"):
        prepare_report(report, audit, {})


def test_comparison_rejects_different_model_and_pairs_only_known_scores():
    manifest = dict.fromkeys(
        (
            "dataset_sha256",
            "input_sha256",
            "prompt_version",
            "production_prompt",
            "judge_version",
            "provider",
            "model",
            "case_ids",
            "implementation_sha256",
        ),
        "same",
    )
    row = {"id": "a", "hits": [], "split": "test", "metrics": {"answer_correctness": 0.5}}
    baseline = {
        "generation_manifest": manifest,
        "model_info": {"temperature": 0},
        "runs": [{"cases": [row]}],
        "generation_summary": dict.fromkeys(("all", "dev", "test"), {}),
        "retrieval_summary": dict.fromkeys(("all", "dev", "test"), {}),
    }
    candidate = copy.deepcopy(baseline)
    candidate["model_info"]["temperature"] = 1
    with pytest.raises(ValueError, match="model"):
        compare_generation(baseline, candidate)
    candidate["model_info"]["temperature"] = 0
    candidate["runs"][0]["cases"][0]["metrics"]["answer_correctness"] = None
    metric = compare_generation(baseline, candidate)["splits"]["test"]["paired_metrics"][
        "answer_correctness"
    ]
    assert metric == {"paired_n": 0, "baseline": None, "candidate": None, "delta": None}
