"""Compare paired frozen runs without collapsing retrieval and generation quality."""

from __future__ import annotations

from typing import Any

from evaluation.rag import GENERATION_METRICS


def compare_reports(
    baseline: dict[str, Any], candidate: dict[str, Any], method: str = "hybrid"
) -> dict[str, Any]:
    bc = baseline["metadata"]["configuration"]
    cc = candidate["metadata"]["configuration"]
    for field in ("top_k", "embedding", "chunk_size", "chunk_overlap", "split"):
        if bc[field] != cc[field]:
            raise ValueError(f"Not comparable: {field} differs")
    bs = baseline["metadata"]["sha256"]
    cs = candidate["metadata"]["sha256"]
    if sorted(v for p, v in bs.items() if p.endswith(".json")) != sorted(
        v for p, v in cs.items() if p.endswith(".json")
    ):
        raise ValueError("Not comparable: dataset checksum differs")
    if bc.get("generation") and cc.get("generation") and bc["generation"] != cc["generation"]:
        raise ValueError("Not comparable: generation/judge configurations differ")
    for path, value in bs.items():
        if path.endswith(("dataset-v1.json", "customer_service_policy.md", ".onnx")):
            if cs.get(path) != value:
                raise ValueError(f"Not comparable: data/model checksum differs: {path}")
    if baseline["dataset_version"] != candidate["dataset_version"]:
        raise ValueError("Not comparable: dataset versions differ")
    b = next(r for r in baseline["runs"] if r["method"] == method)
    c = next(r for r in candidate["runs"] if r["method"] == method)
    if [r["id"] for r in b["cases"]] != [r["id"] for r in c["cases"]]:
        raise ValueError("Not comparable: case IDs/order differ")
    if b["summary"]["errors"] or c["summary"]["errors"]:
        raise ValueError("Cannot claim improvement from incomplete retrieval runs")
    k = bc["top_k"]
    result: dict[str, Any] = {"method": method, "top_k": k, "splits": {}, "case_changes": []}

    def triple(old: Any, new: Any) -> dict[str, Any]:
        return {
            "baseline": old,
            "candidate": new,
            "delta": None if old is None or new is None else new - old,
        }

    for split in ("all", "dev", "test"):
        before = b["summary"] if split == "all" else b["splits"][split]
        after = c["summary"] if split == "all" else c["splits"][split]
        result["splits"][split] = {
            "retrieval": {
                metric: triple(before[f"at_{k}"][metric], after[f"at_{k}"][metric])
                for metric in ("recall", "mrr", "ndcg", "context_relevance")
            },
            "generation": {
                metric: triple(before["generation"][metric], after["generation"][metric])
                for metric in GENERATION_METRICS
            },
            "no_answer_rejection_rate": triple(
                before["no_answer_rejection_rate"], after["no_answer_rejection_rate"]
            ),
            "p95_retrieval_ms": triple(before["latency_ms"]["p95"], after["latency_ms"]["p95"]),
        }
    for before, after in zip(b["cases"], c["cases"], strict=True):
        if [h["chunk_id"] for h in before["hits"]] != [h["chunk_id"] for h in after["hits"]]:
            result["case_changes"].append(
                {
                    "id": before["id"],
                    "split": before["split"],
                    "query": before["query"],
                    "baseline": before["retrieval"],
                    "candidate": after["retrieval"],
                    "before_failures": before["failures"],
                    "after_failures": after["failures"],
                }
            )
    return result
