"""Source-labelled retrieval metrics and reproducible experiment reporting."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import platform
import statistics
import subprocess
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from customer_support.policy import POLICY_PATH, load_policy_sections, policy_files

GENERATION_METRICS = (
    "answer_correctness",
    "faithfulness",
    "citation_support_rate",
    "abstention_accuracy",
)


def digest(path: Path) -> str:
    if path.is_dir():
        payload = b"".join(
            p.name.encode("utf-8") + b"\0" + p.read_bytes() + b"\0"
            for p in policy_files(path)
        )
        return hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def document_id(hit: dict[str, Any]) -> str:
    return f"{hit['source']}#{hit.get('section', hit.get('title'))}"


def load_dataset(
    path: Path, policy_path: Path = POLICY_PATH, *, source_path: Path | None = None
) -> dict[str, Any]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    if dataset.get("policy_sha256") != digest(policy_path):
        raise ValueError("Policy checksum changed: re-review labels and version the dataset")
    source = (source_path or policy_path).as_posix()
    sections = {
        f"{s.source if policy_path.is_dir() else source}#{s.title}": s.content
        for s in load_policy_sections(policy_path)
    }
    chunk_lookup: dict[str, tuple[str, str, str]] = {}
    if any("relevant_chunks" in case for case in dataset.get("cases", [])):
        from customer_support.rag import load_policy_chunks

        for chunk in load_policy_chunks(policy_path):
            chunk_lookup[str(chunk.metadata["chunk_id"])] = (
                str(chunk.metadata["source"]),
                str(chunk.metadata["title"]),
                chunk.page_content,
            )
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases or not dataset.get("version"):
        raise ValueError("Dataset requires a version and nonempty cases")
    seen: set[str] = set()
    for case in cases:
        required = {
            "id",
            "query",
            "relevant_documents",
            "relevance_scores",
            "expected_answer",
            "expected_facts",
            "should_abstain",
            "category",
            "split",
        }
        if not required <= case.keys():
            raise ValueError("Missing dataset fields")
        if case["id"] in seen or not case["query"].strip():
            raise ValueError("Duplicate ID or empty query")
        seen.add(case["id"])
        if case["split"] not in {"dev", "test"} or type(case["should_abstain"]) is not bool:
            raise ValueError("Invalid split or abstention label")
        if not case["expected_answer"] or not case["expected_facts"]:
            raise ValueError("Expected answer and facts must be nonempty")
        docs = case["relevant_documents"]
        scores = case["relevance_scores"]
        ids = [document_id(d) for d in docs]
        if len(set(ids)) != len(ids) or set(ids) != set(scores):
            raise ValueError("Document IDs and grades must agree without duplicates")
        if case["should_abstain"] != (not docs):
            raise ValueError("Abstention cases must have no supporting documents")
        for doc in docs:
            key = document_id(doc)
            grade = scores[key]
            if type(grade) is not int or not 1 <= grade <= 3:
                raise ValueError("Relevance grade must be 1, 2 or 3")
            if key not in sections or not doc.get("evidence_quote"):
                raise ValueError("Unknown source section or missing evidence quote")
            if doc["evidence_quote"] not in sections[key]:
                raise ValueError("Evidence quote not found in source")
        if "relevant_chunks" in case:
            labelled = case["relevant_chunks"]
            if {item["chunk_id"] for item in labelled} != set(
                case.get("evidence_requirements", {}).get("required_chunk_ids", [])
            ):
                raise ValueError("Evidence requirements and relevant chunks disagree")
            if {f"{item['source']}#{item['section']}" for item in labelled} != set(ids):
                raise ValueError("Relevant chunks and documents disagree")
            for item in labelled:
                found_chunk = chunk_lookup.get(item["chunk_id"])
                if found_chunk is None or found_chunk[:2] != (item["source"], item["section"]):
                    raise ValueError("Unknown or misplaced relevant chunk")
    return dataset


def unique_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Section is the evaluation unit; repeated chunks never earn extra credit."""
    result = []
    seen = set()
    for hit in hits:
        key = document_id(hit)
        if key not in seen:
            seen.add(key)
            result.append(hit)
    return result


def retrieval_metrics(case: dict[str, Any], hits: list[dict[str, Any]], k: int) -> dict[str, Any]:
    if k < 1:
        raise ValueError("k must be positive")
    # Truncate raw chunk positions before deduplication: duplicate chunks consume context slots.
    ranked = unique_hits(hits[:k])
    grades = case["relevance_scores"]
    gains = [grades.get(document_id(hit), 0) for hit in ranked]
    if case["should_abstain"]:
        recall = mrr = ndcg = None
    else:
        recall = sum(g > 0 for g in gains) / len(grades)
        mrr = next((1 / i for i, g in enumerate(gains, 1) if g > 0), 0.0)
        dcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(gains, 1))
        ideal = sorted(grades.values(), reverse=True)[:k]
        idcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(ideal, 1))
        ndcg = dcg / idcg
    return {
        "recall": recall,
        "mrr": mrr,
        "ndcg": ndcg,
        "context_relevance": statistics.mean(g / 3 for g in gains) if gains else 0.0,
        "retrieval_abstention_correct": (not hits) == case["should_abstain"],
    }


def failure_reasons(case: dict[str, Any], hits: list[dict[str, Any]]) -> list[str]:
    if case["should_abstain"]:
        return ["unsupported_question_returned_context"] if hits else []
    if not hits:
        return ["answerable_question_rejected"]
    expected = set(case["relevance_scores"])
    found = {document_id(h) for h in hits}
    result = []
    if expected - found:
        result.append("missing_supporting_sections")
    if document_id(hits[0]) not in expected:
        result.append("irrelevant_top1")
    if found - expected:
        result.append("irrelevant_context")
    return result


def mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def summarize(rows: list[dict[str, Any]], k: int) -> dict[str, Any]:
    good = [r for r in rows if r["status"] == "ok"]
    summary: dict[str, Any] = {
        "total": len(rows),
        "evaluated": len(good),
        "errors": len(rows) - len(good),
    }
    for cutoff in sorted({1, k}):
        label = str(cutoff)
        summary[f"at_{cutoff}"] = {
            metric: mean(
                [
                    r["retrieval"][label][metric]
                    for r in good
                    if r["retrieval"][label][metric] is not None
                ]
            )
            for metric in ("recall", "mrr", "ndcg", "context_relevance")
        }
    summary["retrieval_abstention_accuracy"] = mean(
        [float(r["retrieval"][str(k)]["retrieval_abstention_correct"]) for r in good]
    )
    summary["no_answer_rejection_rate"] = mean(
        [float(not r["hits"]) for r in good if r["should_abstain"]]
    )
    summary["answerable_false_rejection_rate"] = mean(
        [float(not r["hits"]) for r in good if not r["should_abstain"]]
    )
    times = sorted(t for r in good for t in r["retrieval_latency_ms"])
    summary["latency_ms"] = {
        "mean": mean(times),
        "p50": statistics.median(times) if times else None,
        "p95": times[math.ceil(len(times) * 0.95) - 1] if times else None,
    }
    summary["generation"] = {
        metric: mean(
            [r["generation"][metric] for r in good if r["generation"].get(metric) is not None]
        )
        for metric in GENERATION_METRICS
    }
    summary["generation"]["evaluated"] = sum(r["generation"]["status"] == "ok" for r in good)
    summary["generation"]["errors"] = sum(r["generation"]["status"] == "error" for r in good)
    for phase in ("generation", "judge"):
        summary["generation"][f"{phase}_latency_ms"] = mean(
            [
                r["generation"][f"{phase}_latency_ms"]
                for r in good
                if r["generation"].get(f"{phase}_latency_ms") is not None
            ]
        )
    summary["failure_reasons"] = dict(Counter(reason for r in rows for reason in r["failures"]))
    return summary


def evaluate(
    cases: list[dict[str, Any]],
    search: Callable[..., list[dict[str, Any]]],
    *,
    method: str,
    top_k: int = 2,
    repeats: int = 3,
    generate: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not cases or top_k < 1 or repeats < 1:
        raise ValueError("Nonempty cases and positive top_k/repeats required")
    rows = []
    for case in cases:
        row: dict[str, Any] = {
            key: case[key]
            for key in ("id", "query", "category", "split", "should_abstain", "expected_answer")
        }
        row.update(
            status="ok",
            hits=[],
            retrieval_latency_ms=[],
            retrieval={},
            failures=[],
            generation={
                "status": "not_run",
                **dict.fromkeys(GENERATION_METRICS),
                "generation_latency_ms": None,
                "judge_latency_ms": None,
            },
        )
        try:
            signatures = []
            for _ in range(repeats):
                started = time.perf_counter()
                hits = search(case["query"], top_k=top_k, method=method)
                row["retrieval_latency_ms"].append((time.perf_counter() - started) * 1000)
                signatures.append([h["chunk_id"] for h in hits])
                if len(signatures) == 1:
                    row["hits"] = [dict(h, rank=i) for i, h in enumerate(hits, 1)]
            row["ranking_stable"] = all(s == signatures[0] for s in signatures)
            row["retrieval"] = {
                str(k): retrieval_metrics(case, row["hits"], k) for k in sorted({1, top_k})
            }
            row["failures"] = failure_reasons(case, row["hits"])
            if generate is not None:
                try:
                    row["generation"] = generate(case, row["hits"])
                except Exception as exc:
                    row["generation"].update(status="error", error_type=type(exc).__name__)
                if row["generation"]["status"] == "error":
                    row["failures"].append("generation_or_judge_error")
        except Exception as exc:
            row["status"] = "error"
            row["error_type"] = type(exc).__name__
            row["failures"] = ["retrieval_or_evaluation_error"]
        rows.append(row)
    return {
        "method": method,
        "summary": summarize(rows, top_k),
        "splits": {
            split: summarize([r for r in rows if r["split"] == split], top_k)
            for split in ("dev", "test")
        },
        "cases": rows,
    }


def metadata(dataset_path: Path, configuration: dict[str, Any]) -> dict[str, Any]:
    files = [
        dataset_path,
        POLICY_PATH,
        Path("uv.lock"),
        Path("src/customer_support/rag.py"),
        Path("src/evaluation/rag.py"),
        Path("src/evaluation/llm.py"),
        Path("scripts/evaluate_rag.py"),
        Path("src/evaluation/experiments.py"),
    ]
    model_files = sorted(Path("data/models").rglob("*.onnx"))
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    return {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "git_head": commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "configuration": configuration,
        "sha256": {p.as_posix(): digest(p) for p in files + model_files if p.exists()},
        "packages": {
            p: importlib.metadata.version(p)
            for p in ("fastembed", "chromadb", "langchain-chroma", "onnxruntime", "numpy")
        },
    }


def markdown(report: dict[str, Any]) -> str:
    k = report["metadata"]["configuration"]["top_k"]
    lines = [
        "# RAG evaluation",
        "",
        f"Dataset: `{report['dataset_version']}`; K={k}.",
        "",
        "Retrieval metrics use source + section labels; generation metrics are separate.",
        "Empty-context relevance is 0; no-answer queries are excluded from Recall/MRR/nDCG.",
        "",
        "| Method / split | Recall | MRR | nDCG | Context relevance | No-answer rejection | P95 ms | Errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def fmt(value: Any) -> str:
        return "N/A" if value is None else f"{value:.4f}"

    for run in report["runs"]:
        for split, s in {"all": run["summary"], **run["splits"]}.items():
            m = s[f"at_{k}"]
            values = [
                m["recall"],
                m["mrr"],
                m["ndcg"],
                m["context_relevance"],
                s["no_answer_rejection_rate"],
                s["latency_ms"]["p95"],
            ]
            lines.append(
                f"| {run['method']} / {split} | "
                + " | ".join(map(fmt, values))
                + f" | {s['errors']} |"
            )
        lines += [
            "",
            f"## {run['method']}: generation / judge",
            "",
            "```json",
            json.dumps(run["summary"]["generation"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## Failure diagnostics",
            "",
        ]
        for row in run["cases"]:
            if row["failures"]:
                titles = ", ".join(h["title"] for h in row["hits"]) or "(empty)"
                lines.append(
                    f"- {row['id']} [{row['split']}] {row['query']} → {titles}; "
                    + ", ".join(row["failures"])
                )
    lines += [
        "",
        "Failure reasons describe label mismatches, not an LLM-inferred root cause.",
        "Generation null means not measured (never substituted with retrieval scores).",
        "",
    ]
    return "\n".join(lines)
