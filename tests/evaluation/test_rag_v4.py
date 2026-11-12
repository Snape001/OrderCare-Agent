"""Evidence and configuration invariants for the v4 challenge set."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from customer_support.rag import DEFAULT_SERVING_POLICY_PATH, get_policy_knowledge_base
from evaluation.rag import load_dataset, validate_v4_case_splits


def test_v4_pairs_gold_and_coverage() -> None:
    dataset = load_dataset(
        Path("data/evaluation/rag/dataset-v4.json"), Path("data/policies/v3")
    )
    cases = dataset["cases"]
    assert len(cases) == 40
    assert len({case["pair_id"] for case in cases}) == 20
    assert Counter(case["split"] for case in cases) == {"dev": 20, "test": 20}
    assert len({d["source"] for case in cases for d in case["relevant_documents"]}) >= 12
    assert next(case for case in cases if case["id"] == "pair-01-colloquial")["query"] == (
        "保修缺少凭证怎么处理？"
    )
    altered = [dict(case) for case in cases]
    altered[0]["split"] = "test"
    altered[20]["split"] = "dev"
    with pytest.raises(ValueError, match="pair disagrees"):
        validate_v4_case_splits(altered)


def test_experiment_paths_are_isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    get_policy_knowledge_base.cache_clear()
    monkeypatch.delenv("ORDERCARE_EVAL_POLICY_PATH", raising=False)
    monkeypatch.delenv("ORDERCARE_EVAL_CHROMA_PATH", raising=False)
    assert get_policy_knowledge_base().policy_path == DEFAULT_SERVING_POLICY_PATH
    get_policy_knowledge_base.cache_clear()
    monkeypatch.setenv("ORDERCARE_EVAL_POLICY_PATH", "data/policies/v3")
    with pytest.raises(ValueError, match="set together"):
        get_policy_knowledge_base()
    monkeypatch.setenv("ORDERCARE_EVAL_CHROMA_PATH", str(tmp_path / "index"))
    get_policy_knowledge_base.cache_clear()
    kb = get_policy_knowledge_base()
    assert kb.policy_path == Path("data/policies/v3")
    assert kb.persist_directory == tmp_path / "index"
    get_policy_knowledge_base.cache_clear()
