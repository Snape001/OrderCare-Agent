import copy
import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.experiments import expand_query
from evaluation.llm import Answer, JudgeResult, LLMEvaluator, make_model, parse_json, score_judgment
from evaluation.rag import evaluate, load_dataset, retrieval_metrics


def hit(section):
    return {
        "source": "policy.md",
        "title": section,
        "chunk_id": section,
        "content": "evidence",
        "score": 0.8,
    }


def case(abstain=False):
    return {
        "id": "one",
        "query": "question",
        "category": "test",
        "split": "dev",
        "should_abstain": abstain,
        "expected_answer": "fact",
        "expected_facts": ["fact"],
        "relevance_scores": {} if abstain else {"policy.md#A": 3, "policy.md#B": 2},
    }


def test_known_graded_metrics():
    m = retrieval_metrics(case(), [hit("X"), hit("B")], 2)
    assert m["recall"] == 0.5
    assert m["mrr"] == 0.5
    assert m["ndcg"] == pytest.approx((3 / math.log2(3)) / (7 + 3 / math.log2(3)))
    assert m["context_relevance"] == pytest.approx(1 / 3)


def test_perfect_ranking_and_duplicate_chunks():
    assert retrieval_metrics(case(), [hit("A"), hit("B")], 2)["ndcg"] == 1
    assert retrieval_metrics(case(), [hit("A"), hit("A"), hit("B")], 2)["recall"] == 0.5
    assert retrieval_metrics(case(), [dict(hit("A"), source="wrong.md")], 1)["recall"] == 0


def test_empty_answerable_and_unanswerable_results():
    positive = retrieval_metrics(case(), [], 2)
    assert positive["recall"] == positive["mrr"] == positive["ndcg"] == 0
    assert positive["retrieval_abstention_correct"] is False
    negative = retrieval_metrics(case(True), [], 2)
    assert negative["recall"] is None
    assert negative["retrieval_abstention_correct"] is True
    assert negative["context_relevance"] == 0
    assert retrieval_metrics(case(True), [hit("A")], 2)["retrieval_abstention_correct"] is False


def test_evaluation_errors_are_not_silently_scored_as_success():
    def broken(*args, **kwargs):
        raise ConnectionError("private error data")

    run = evaluate([case()], broken, method="hybrid")
    assert run["summary"]["errors"] == 1
    assert run["summary"]["at_2"]["recall"] is None
    assert "private error data" not in json.dumps(run)


def test_metrics_remain_separate_from_generation_and_negative_denominator():
    run = evaluate([case(True)], lambda *a, **kw: [], method="hybrid")
    assert run["summary"]["no_answer_rejection_rate"] == 1
    assert run["summary"]["at_2"]["recall"] is None
    assert run["summary"]["generation"]["answer_correctness"] is None
    assert run["summary"]["generation"]["evaluated"] == 0
    assert len(run["cases"][0]["retrieval_latency_ms"]) == 3


@pytest.mark.parametrize("k,repeats", [(0, 1), (1, 0), (-1, 1)])
def test_invalid_experiment_parameters(k, repeats):
    with pytest.raises(ValueError):
        evaluate([case()], lambda *a, **kw: [], method="hybrid", top_k=k, repeats=repeats)


def test_empty_dataset_rejected():
    with pytest.raises(ValueError):
        evaluate([], lambda *a, **kw: [], method="hybrid")


def test_frozen_dataset_is_source_validated():
    dataset = load_dataset(Path("data/evaluation/rag/dataset-v1.json"))
    assert len(dataset["cases"]) == 40
    assert sum(c["should_abstain"] for c in dataset["cases"]) == 10
    assert sum(c["split"] == "dev" for c in dataset["cases"]) == 20


@pytest.mark.parametrize(
    "change", ["checksum", "section", "grade", "quote", "abstain", "duplicate"]
)
def test_invalid_labels_fail_closed(tmp_path, change):
    data = load_dataset(Path("data/evaluation/rag/dataset-v1.json"))
    c = data["cases"][0]
    if change == "checksum":
        data["policy_sha256"] = "wrong"
    elif change == "section":
        c["relevant_documents"][0]["section"] = "absent"
    elif change == "grade":
        c["relevance_scores"][next(iter(c["relevance_scores"]))] = 4
    elif change == "quote":
        c["relevant_documents"][0]["evidence_quote"] = "invented evidence"
    elif change == "abstain":
        c["should_abstain"] = True
    else:
        data["cases"].append(copy.deepcopy(c))
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(path)


def test_expansion_preserves_question_and_noop():
    q = "验货后才能退钱吗？"
    assert expand_query(q).startswith(q)
    assert "仓库验收" in expand_query(q)
    assert expand_query("请问天气") == "请问天气"


def test_paid_provider_requires_explicit_opt_in():
    with pytest.raises(ValueError, match="allow-paid-api"):
        make_model("configured", "unused", False)


@pytest.mark.parametrize("content", ["not-json", "[]", {"answer": "not text"}])
def test_malformed_model_output(content):
    with pytest.raises((ValueError, TypeError)):
        parse_json(content)


def test_citations_require_support_and_source_not_just_count():
    answer = Answer(
        answer="fact",
        abstained=False,
        citations=[{"claim": "fact", "source": "wrong.md", "section": "A"}],
    )
    judge = JudgeResult(
        facts_correct=[True],
        answer_claims=[{"claim": "fact", "supported": True, "reason": "quote"}],
        citation_supported=[True],
        reason="test",
    )
    assert score_judgment(case(), [hit("A")], answer, judge)["citation_support_rate"] == 0
    judge.facts_correct = []
    with pytest.raises(ValueError):
        score_judgment(case(), [], answer, judge)


def test_judge_invalid_boolean_is_not_coerced():
    with pytest.raises(ValidationError):
        Answer(answer="fact", abstained="false", citations=[])


def test_generation_exception_recorded_without_fabricated_scores():
    class Broken:
        async def ainvoke(self, prompt):
            raise ConnectionError("secret-provider-message")

    evaluator = LLMEvaluator(Broken(), Broken())
    try:
        result = evaluator(case(), [])
    finally:
        evaluator.close()
    assert result["status"] == "error"
    assert result["answer_correctness"] is None
    assert result["generation_latency_ms"] >= 0
    assert "secret-provider-message" not in json.dumps(result)


def test_generator_never_receives_gold_answer():
    prompts = []

    class Generator:
        async def ainvoke(self, prompt):
            prompts.append(prompt)
            return type(
                "Message",
                (),
                {"content": json.dumps({"answer": "fact", "abstained": False, "citations": []})},
            )()

    class Judge:
        async def ainvoke(self, prompt):
            return type(
                "Message",
                (),
                {
                    "content": json.dumps(
                        {
                            "facts_correct": [True],
                            "answer_claims": [
                                {"claim": "fact", "supported": True, "reason": "evidence"}
                            ],
                            "citation_supported": [],
                            "reason": "ok",
                        }
                    )
                },
            )()

    c = case()
    c["expected_facts"] = ["SECRET_GOLD_NOT_FOR_GENERATOR"]
    evaluator = LLMEvaluator(Generator(), Judge())
    try:
        result = evaluator(c, [hit("A")])
    finally:
        evaluator.close()
    assert result["status"] == "ok"
    assert "SECRET_GOLD_NOT_FOR_GENERATOR" not in prompts[0]
    assert result["citation_support_rate"] == 0


def test_comparison_rejects_changed_ground_truth_and_k():
    from evaluation.comparison import compare_reports

    baseline = json.loads(
        Path("data/evaluation/rag/baseline-v1/results.json").read_text(encoding="utf-8")
    )
    candidate = copy.deepcopy(baseline)
    candidate["metadata"]["configuration"]["top_k"] = 3
    with pytest.raises(ValueError, match="top_k"):
        compare_reports(baseline, candidate)
    candidate = copy.deepcopy(baseline)
    candidate["metadata"]["sha256"]["data/evaluation/rag/dataset-v1.json"] = "changed"
    with pytest.raises(ValueError, match="checksum"):
        compare_reports(baseline, candidate)
    unchanged = compare_reports(baseline, baseline)
    assert unchanged["splits"]["test"]["retrieval"]["recall"]["delta"] == 0
    assert unchanged["splits"]["test"]["generation"]["answer_correctness"]["delta"] is None


def test_generation_failure_does_not_erase_retrieval_metrics():
    def broken_generation(*args):
        raise TimeoutError("judge unavailable")

    run = evaluate(
        [case()], lambda *a, **kw: [hit("A"), hit("B")], method="hybrid", generate=broken_generation
    )
    assert run["summary"]["at_2"]["recall"] == 1
    assert run["summary"]["errors"] == 0
    assert run["summary"]["generation"]["errors"] == 1
    assert run["summary"]["generation"]["answer_correctness"] is None
