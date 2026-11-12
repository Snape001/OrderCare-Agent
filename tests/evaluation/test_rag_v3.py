"""The v3 corpus and query-style benchmark remain versioned and source-checked."""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

import pytest

from customer_support.policy import load_policy_sections
from customer_support.rag import load_policy_chunks
from evaluation.rag import evaluate, load_dataset, validate_v3_case_splits

CORPUS = Path("data/policies/v3")
DATASET = Path("data/evaluation/rag/dataset-v3.json")


def test_v3_corpus_and_dataset_are_normalized_and_frozen() -> None:
    data = load_dataset(DATASET, CORPUS)
    files = sorted(CORPUS.glob("*.md"))
    assert len(files) == 36
    assert len(data["cases"]) == 40
    assert sum(case["should_abstain"] for case in data["cases"]) == 8
    assert Counter(case["query_style"] for case in data["cases"]) == {
        "formal": 20,
        "colloquial": 20,
    }
    assert Counter(case["split"] for case in data["cases"]) == {"dev": 20, "test": 20}
    assert Counter(case["split"] for case in data["cases"] if case["should_abstain"]) == {
        "dev": 4,
        "test": 4,
    }
    for source in files:
        content = source.read_text(encoding="utf-8")
        assert "本文为 OrderCare-Agent 评测用模拟政策" not in content
        assert "## 适用范围" not in content
    assert load_policy_sections(CORPUS)
    chunks = load_policy_chunks(CORPUS)
    assert chunks
    assert not [chunk for chunk in chunks if len(chunk.page_content) < 40]
    assert all({"doc_type", "section_type", "source", "is_retrievable"} <= chunk.metadata.keys()
               for chunk in chunks)
    assert len({doc["source"] for case in data["cases"] for doc in case["relevant_documents"]}) >= 12
    assert len({case["pair_id"] for case in data["cases"]}) == 20


def test_v3_validation_rejects_mixed_scenario_split() -> None:
    data = load_dataset(DATASET, CORPUS)
    cases = copy.deepcopy(data["cases"])
    group = cases[0]["scenario_group"]
    other = next(case for case in cases[1:] if case["scenario_group"] == group)
    opposite = next(
        case
        for case in cases
        if case["split"] != cases[0]["split"]
        and case["scenario_group"] != group
        and not case["should_abstain"]
    )
    other["split"], opposite["split"] = opposite["split"], other["split"]
    with pytest.raises(ValueError, match="dev and test"):
        validate_v3_case_splits(cases)


def test_evaluation_reports_metrics_by_query_style() -> None:
    data = load_dataset(DATASET, CORPUS)
    report = evaluate(
        data["cases"],
        lambda _query, **_kwargs: [],
        method="dummy",
        top_k=2,
        repeats=1,
    )
    assert set(report["query_styles"]) == {"formal", "colloquial"}
    assert report["query_styles"]["formal"]["total"] == 20
    assert report["query_styles"]["colloquial"]["total"] == 20
    assert report["summary"]["at_2"]["precision"] == 0


def test_v3_rejects_pair_with_different_gold() -> None:
    data = load_dataset(DATASET, CORPUS)
    cases = copy.deepcopy(data["cases"])
    cases[1]["expected_answer"] = "不同的标准答案"
    with pytest.raises(ValueError, match="Paired queries disagree"):
        validate_v3_case_splits(cases)
