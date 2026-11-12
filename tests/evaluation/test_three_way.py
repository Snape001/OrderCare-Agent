"""The comparison must preserve frozen labels and reject obvious rewrite drift."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))
from evaluate_three_way_rag import latency_summary, rewrite_summary  # noqa: E402

from customer_support.policy import POLICY_PATH
from evaluation.three_way import (
    frozen_policy,
    read_rewrites,
    save_json,
    validate_rewrite,
    validated_dataset,
)


def test_frozen_policy_validates_without_changing_current_policy(tmp_path: Path) -> None:
    dataset_path = Path("data/evaluation/rag/dataset-v1.json")
    expected = json.loads(dataset_path.read_text(encoding="utf-8"))["policy_sha256"]
    snapshot = tmp_path / "policy.md"
    frozen_policy(snapshot, expected)
    assert len(validated_dataset(dataset_path, snapshot)["cases"]) == 40
    assert POLICY_PATH.read_bytes() != snapshot.read_bytes()
    snapshot.write_text("wrong", encoding="utf-8")
    with pytest.raises(ValueError, match="Policy checksum"):
        validated_dataset(dataset_path, snapshot)


def test_rewrite_constraint_validation_and_cache_manifest(tmp_path: Path) -> None:
    original = "订单 ORD1001 的耳机没到，不能按七天退吗？"
    assert validate_rewrite(original, original) == []
    issues = validate_rewrite(original, "订单 ORD1002 的手机可以退吗？")
    assert "identifier_removed" in issues
    assert "identifier_added" in issues
    assert "product_removed:耳机" in issues
    assert any(issue.startswith("negation_removed:") for issue in issues)
    path = tmp_path / "cache.json"
    assert read_rewrites(path, {"version": "v1"})["cases"] == {}
    path.write_text('{"manifest":{"version":"old"},"cases":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="manifest mismatch"):
        read_rewrites(path, {"version": "v1"})


def test_cache_save_retries_temporary_windows_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cache.json"
    path.write_text("old", encoding="utf-8")
    original_replace = Path.replace
    attempts = 0

    def replace(self: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("temporary lock")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("evaluation.three_way.time.sleep", lambda _: None)
    save_json(path, {"version": 2})
    assert attempts == 3
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 2}


def test_rewrite_usage_and_latency_accounting_preserves_missing_usage() -> None:
    summary = rewrite_summary([
        {"case_id": "one", "status": "ok", "validation_issues": [],
         "usage": {"input_tokens": 10, "output_tokens": 3}, "latency_ms": 100},
        {"case_id": "two", "status": "error", "validation_issues": [],
         "usage": None, "latency_ms": 250},
    ])
    assert summary["requests"] == 2
    assert summary["successful_requests"] == 1
    assert summary["api_errors"] == 1
    assert summary["input_tokens"] is None
    assert summary["output_tokens"] is None
    assert summary["usage_missing_cases"] == ["two"]
    assert summary["latency"] == {"total_ms": 350, "mean_ms": 175, "p95_ms": 250}
    assert latency_summary([100, 250])["total_ms"] == 350
