"""The second RAG experiment must keep its corpus and labels frozen."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.rag import digest, load_dataset

CORPUS = Path("data/policies/v2")
DATASET = Path("data/evaluation/rag/dataset-v2.json")


def test_v2_dataset_is_source_validated_and_split_by_scenario() -> None:
    data = load_dataset(DATASET, CORPUS)
    cases = data["cases"]
    assert len(cases) == 90
    assert sum(case["should_abstain"] for case in cases) == 17
    assert {case["split"] for case in cases} == {"dev", "test"}
    groups: dict[str, str] = {}
    for case in cases:
        group = case["scenario_group"]
        assert groups.setdefault(group, case["split"]) == case["split"]
        assert "relevant_chunks" in case
        assert "evidence_requirements" in case


def test_v2_policy_change_is_rejected(tmp_path: Path) -> None:
    corpus = tmp_path / "policies"
    corpus.mkdir()
    for source in CORPUS.glob("*.md"):
        (corpus / source.name).write_bytes(source.read_bytes())
    assert digest(corpus) == digest(CORPUS)
    (corpus / "returns.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Policy checksum changed"):
        load_dataset(DATASET, corpus)


def test_v2_wrong_chunk_label_is_rejected(tmp_path: Path) -> None:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    case = next(case for case in data["cases"] if case["relevant_chunks"])
    case["relevant_chunks"][0]["chunk_id"] = "nonexistent-chunk"
    case["evidence_requirements"]["required_chunk_ids"][0] = "nonexistent-chunk"
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown or misplaced relevant chunk"):
        load_dataset(path, CORPUS)
