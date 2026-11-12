"""Frozen v4 ancestry and evidence invariants for the v5 challenge set."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from evaluation.rag import digest, load_dataset, validate_v5_case_splits


def test_v5_preserves_v4_and_validates_new_evidence() -> None:
    policy = Path("data/policies/v3")
    old_path = Path("data/evaluation/rag/dataset-v4.json")
    new = load_dataset(Path("data/evaluation/rag/dataset-v5.json"), policy)
    old = load_dataset(old_path, policy)
    assert new["base_dataset_sha256"] == digest(old_path)
    assert new["cases"][:40] == old["cases"]
    assert len(new["cases"]) == 50
    assert Counter(c["query_style"] for c in new["cases"]) == {
        "formal": 25, "colloquial": 25,
    }
    assert Counter(c["split"] for c in new["cases"][40:]) == {
        "dev": 6, "test": 4,
    }
    old_sources = {d["source"] for c in old["cases"] for d in c["relevant_documents"]}
    assert all(c["relevant_documents"][0]["source"] not in old_sources
               for c in new["cases"][40:])
    assert all(c["subset"] == "rewrite_challenge" for c in new["cases"][40:])
    assert all(not c["should_abstain"] for c in new["cases"])


def test_v5_rejects_split_or_evidence_drift() -> None:
    path = Path("data/evaluation/rag/dataset-v5.json")
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    altered = [dict(case) for case in cases]
    altered[-1]["split"] = "dev"
    with pytest.raises(ValueError, match="pair disagrees"):
        validate_v5_case_splits(altered)
