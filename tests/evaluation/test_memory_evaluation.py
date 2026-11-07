"""Deterministic metric and label checks; real BGE runs in the evaluation command."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def evaluator():
    import sys

    scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    sys.path.insert(0, scripts)
    try:
        yield importlib.import_module("evaluate_memory")
    finally:
        sys.path.remove(scripts)


def test_retrieval_metrics_and_no_answer(evaluator):
    assert evaluator.retrieval_metrics(["wrong", "right"], ["right"], 4) == {
        "recall_at_k": 1.0, "precision_at_k": 0.25, "mrr": 0.5,
    }
    assert evaluator.retrieval_metrics([], ["right"], 4) == {
        "recall_at_k": 0.0, "precision_at_k": 0.0, "mrr": 0.0,
    }
    assert evaluator.retrieval_metrics([], [], 4) is None


def test_dataset_integrity_rejects_cross_customer_label(evaluator):
    import json

    data = json.loads(evaluator.DATASET.read_text(encoding="utf-8"))
    evaluator.validate_dataset(data)
    data["cases"][0]["relevant_memory_ids"] = ["m15"]
    with pytest.raises(ValueError, match="Cross-customer"):
        evaluator.validate_dataset(data)
