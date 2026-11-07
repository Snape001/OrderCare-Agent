import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from customer_support.policy import POLICY_PATH, format_policy_hits, load_policy_sections
from customer_support.prompts import SYSTEM_PROMPT
from evaluation.generation import (
    EvidenceJudge,
    GenerationRunner,
    assemble_context,
    diagnose,
    generation_messages,
    generation_summary,
    judge_messages,
    score,
)
from evaluation.rag import load_dataset

FROZEN_POLICY = Path("data/evaluation/rag/three-way-comparison-v1/frozen-policy-v1.md")


def example():
    case = load_dataset(Path("data/evaluation/rag/dataset-v1.json"), FROZEN_POLICY, source_path=POLICY_PATH)["cases"][1]
    doc = case["relevant_documents"][0]
    hit = {
        "title": doc["section"],
        "source": doc["source"],
        "content": doc["evidence_quote"],
        "chunk_id": "test",
        "score": 0.9,
    }
    context = [dict(hit, evidence_id="E1")]
    answer = (
        "自签收次日起计算7个自然日。来源：data/policies/customer_service_policy.md 七天无理由退款"
    )
    support = {
        "supported": True,
        "evidence_id": "E1",
        "quote": "自签收次日起 7 个自然日内",
        "reason": "原文",
    }
    claim = {**support, "claim": "自签收次日起计算7个自然日"}
    verdict = EvidenceJudge(
        facts_correct=[True],
        fact_support=[dict(support, fact_index=0)],
        answer_claims=[claim],
        citations=[dict(claim, source=hit["source"], section=hit["title"])],
        abstained=False,
        reason="依据充分",
    )
    return case, hit, context, answer, verdict


def test_production_prompt_and_tool_result_are_reused_without_gold():
    case, hit, _, _, _ = example()
    body, evidence = assemble_context([hit])
    assert json.loads(body) == format_policy_hits([hit])
    messages = generation_messages(case["query"], body, "baseline")
    assert messages[0].content == SYSTEM_PROMPT
    assert messages[2].tool_calls[0]["name"] == "search_policy"
    assert messages[3].tool_call_id == messages[2].tool_calls[0]["id"]
    assert "expected_answer" not in body
    assert evidence[0]["evidence_id"] == "E1"


def test_context_modes_preserve_source_text_and_empty_context():
    _, hit, _, _, _ = example()
    body, evidence = assemble_context([hit], "structured")
    assert hit["content"] in body and hit["source"] in body and hit["title"] in body
    assert evidence[0]["content"] == hit["content"]
    assert json.loads(assemble_context([])[0])["references"] == []
    assert assemble_context([], "structured")[1] == []
    with pytest.raises(ValueError):
        assemble_context([], "unknown")


def test_perfect_answer_and_fact_level_support():
    case, _, context, answer, verdict = example()
    m = score(case, context, answer, verdict)
    for key in (
        "answer_correctness",
        "faithfulness",
        "citation_support_rate",
        "evidence_sufficiency",
        "abstention_accuracy",
    ):
        assert m[key] == 1
    assert m["missing_facts"] == []


def test_unanchored_evidence_is_unknown_not_supported():
    case, _, context, answer, verdict = example()
    verdict.fact_support[0].quote = "invented quote"
    m = score(case, context, answer, verdict)
    assert m["evidence_sufficiency"] is None
    assert m["fact_evidence_coverage"] is None


def test_missing_fact_is_insufficient_even_with_other_unknown_facts():
    case, _, context, answer, verdict = example()
    verdict.fact_support[0].supported = False
    verdict.fact_support[0].quote = ""
    assert score(case, context, answer, verdict)["evidence_sufficiency"] == 0


def test_missing_citation_does_not_become_perfect_score():
    case, _, context, answer, verdict = example()
    verdict.citations = []
    assert score(case, context, answer, verdict)["citation_support_rate"] == 0
    verdict.answer_claims = []
    assert score(case, context, answer, verdict)["faithfulness"] is None


def test_invented_citation_is_rejected():
    case, _, context, answer, verdict = example()
    verdict.citations[0].section = "不存在的章节"
    assert score(case, context, answer, verdict)["citation_support_rate"] == 0


def test_refusal_requires_visible_quote():
    case, _, context, answer, verdict = example()
    verdict.abstained = True
    verdict.abstention_quote = "答案没有这句话"
    assert score(case, context, answer, verdict)["abstention_accuracy"] is None


def test_no_answer_refusal_and_missing_evidence():
    case = load_dataset(Path("data/evaluation/rag/dataset-v1.json"), FROZEN_POLICY, source_path=POLICY_PATH)["cases"][30]
    answer = "没有退货运费承担规则，需要人工核实。"
    verdict = EvidenceJudge(
        facts_correct=[True],
        fact_support=[],
        answer_claims=[],
        citations=[],
        abstained=True,
        abstention_quote="需要人工核实",
        reason="知识缺失",
    )
    metrics = score(case, [], answer, verdict)
    assert metrics["evidence_sufficiency"] == 0
    assert metrics["abstention_accuracy"] == 1
    assert metrics["faithfulness"] is None
    assert diagnose(case, [], [], metrics, answer)["failure_types"] == ["Missing Evidence"]


def test_invalid_judge_schema_and_wrong_fact_count():
    with pytest.raises(ValidationError):
        EvidenceJudge.model_validate({"facts_correct": ["true"]})
    case, _, context, answer, verdict = example()
    verdict.facts_correct = []
    with pytest.raises(ValueError, match="length"):
        score(case, context, answer, verdict)


def test_fact_index_mismatch_is_not_silently_reordered():
    case, _, context, answer, verdict = example()
    verdict.fact_support[0].fact_index = 2
    with pytest.raises(ValueError, match="indexes"):
        score(case, context, answer, verdict)


def test_failure_types_are_layer_specific():
    case, hit, context, answer, _ = example()
    m = {"evidence_sufficiency": 1, "answer_correctness": 0, "citation_support_rate": 0}
    assert "Generation Failure" in diagnose(case, [hit], context, m, answer)["failure_types"]
    assert "Retrieval Miss" in diagnose(case, [], [], {}, answer)["failure_types"]
    assert "Context Assembly" in diagnose(case, [hit], [], {}, answer)["failure_types"]
    m = {"evidence_sufficiency": 0, "abstained": False, "answer_correctness": 0}
    assert "Abstention Failure" in diagnose(case, [], [], m, answer)["failure_types"]


def test_no_current_policy_section_is_fragmented():
    from customer_support.rag import load_policy_chunks

    chunks = load_policy_chunks()
    assert len(chunks) == len(load_policy_sections()) == 16
    assert all(len(d.page_content) <= 220 for d in chunks)


def test_judge_must_be_explicit_and_errors_keep_raw_output():
    runner = GenerationRunner.__new__(GenerationRunner)
    runner.policy_path = POLICY_PATH
    runner.judge_enabled = False
    with pytest.raises(ValueError, match="explicit"):
        runner.judge({}, {})
    runner.judge_enabled = True
    runner.judge_model = object()
    runner.call = lambda *args: {
        "raw_response": "invalid-json",
        "status": "ok",
        "latency_ms": 1,
        "response_metadata": {},
        "usage": {},
    }
    case, hit, context, answer, _ = example()
    result = runner.judge(
        case, {"generation": {"answer": answer}, "context": context, "hits": [hit]}
    )
    assert result["judge"]["status"] == "error"
    assert result["judge"]["raw_response"] == "invalid-json"
    assert result["metrics"]["faithfulness"] is None


def test_connection_failure_never_returns_mock_answer():
    runner = GenerationRunner.__new__(GenerationRunner)
    runner.generator = object()

    def fail(*args):
        raise ConnectionError("sensitive provider error")

    runner.call = fail
    case, _, _, _, _ = example()
    row = runner.generate(case, [], "baseline")
    assert row["generation"]["status"] == "error"
    assert "answer" not in row["generation"]
    assert "sensitive provider error" not in json.dumps(row)


def test_generation_and_judge_do_not_share_gold_inputs():
    case, _, context, answer, _ = example()
    case = copy.deepcopy(case)
    case["expected_facts"] = ["GOLD_ONLY_IN_JUDGE"]
    gen = generation_messages(case["query"], "context", "baseline")
    assert all("GOLD_ONLY_IN_JUDGE" not in m.content for m in gen)
    assert "GOLD_ONLY_IN_JUDGE" in judge_messages(case, context, answer)[1].content


def test_summary_reports_nulls_coverage_and_split():
    rows = [{"split": "dev", "generation": {"status": "error", "latency_ms": 2}}]
    summary = generation_summary(rows)
    assert summary["all"]["generated"] == 0
    assert summary["all"]["metrics"]["faithfulness"] == {"mean": None, "valid": 0}
    assert summary["test"]["total"] == 0


def test_configured_judge_receives_json_schema():
    runner = GenerationRunner.__new__(GenerationRunner)
    runner.policy_path = POLICY_PATH
    runner.model_info = {"provider": "configured"}
    runner.judge_enabled = True
    runner.judge_model = object()
    captured = []

    def call(model, messages):
        captured.extend(messages)
        return {"raw_response": "{}", "response_metadata": {}, "status": "ok"}

    runner.call = call
    case, hit, context, answer, _ = example()
    result = runner.judge(
        case, {"generation": {"answer": answer}, "context": context, "hits": [hit]}
    )
    assert "JSON schema:" in captured[0].content
    assert result["judge"]["status"] == "error"
