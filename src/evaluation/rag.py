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
            p.name.encode("utf-8") + b"\0" + p.read_bytes() + b"\0" for p in policy_files(path)
        )
        return hashlib.sha256(payload).hexdigest()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def document_id(hit: dict[str, Any]) -> str:
    return f"{hit['source']}#{hit.get('section', hit.get('title'))}"


def validate_v3_case_splits(cases: list[dict[str, Any]]) -> None:
    """Check the fixed size, style balance, and scenario-isolated v3 split."""
    if len(cases) != 40 or sum(case["should_abstain"] for case in cases) != 8:
        raise ValueError("v3 dataset must contain 40 cases and 8 no-answer cases")
    styles = Counter(case["query_style"] for case in cases)
    if styles != Counter({"formal": 20, "colloquial": 20}):
        raise ValueError("v3 dataset must contain 20 formal and 20 colloquial queries")
    splits = Counter(case["split"] for case in cases)
    if splits != Counter({"dev": 20, "test": 20}):
        raise ValueError("v3 dataset must contain 20 dev and 20 test cases")
    group_splits: dict[str, str] = {}
    for case in cases:
        group = case["scenario_group"]
        if group in group_splits and group_splits[group] != case["split"]:
            raise ValueError("Scenario group appears in both dev and test")
        group_splits[group] = case["split"]
    if Counter(case["split"] for case in cases if case["should_abstain"]) != Counter(
        {"dev": 4, "test": 4}
    ):
        raise ValueError("v3 dataset must contain 4 no-answer cases per split")
    pairs: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        if not case.get("pair_id"):
            raise ValueError("v3 case missing pair_id")
        pairs.setdefault(case["pair_id"], []).append(case)
    if len(pairs) != 20:
        raise ValueError("v3 dataset must contain 20 pairs")
    for pair in pairs.values():
        if len(pair) != 2 or {case["query_style"] for case in pair} != {
            "formal", "colloquial"
        }:
            raise ValueError("Each pair requires formal and colloquial queries")
        first, second = pair
        for key in (
            "split", "should_abstain", "expected_answer", "expected_facts",
            "relevant_documents", "relevance_scores", "relevant_chunks", "evidence_requirements",
        ):
            if first[key] != second[key]:
                raise ValueError(f"Paired queries disagree on {key}")
    for split in ("dev", "test"):
        in_split = [pair for pair in pairs.values() if pair[0]["split"] == split]
        if len(in_split) != 10 or sum(pair[0]["should_abstain"] for pair in in_split) != 2:
            raise ValueError("Each split requires 8 answerable and 2 no-answer pairs")


def validate_v4_case_splits(cases: list[dict[str, Any]]) -> None:
    """Validate the 40-question, answerable v4 challenge set."""
    if len(cases) != 40 or any(case["should_abstain"] for case in cases):
        raise ValueError("v4 requires 40 answerable cases")
    pairs: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        pairs.setdefault(case.get("pair_id", ""), []).append(case)
    if "" in pairs or len(pairs) != 20:
        raise ValueError("v4 requires 20 named pairs")
    if Counter(case["split"] for case in cases) != Counter({"dev": 20, "test": 20}):
        raise ValueError("v4 requires 20 questions per split")
    for pair in pairs.values():
        if len(pair) != 2 or {case.get("query_style") for case in pair} != {
            "formal", "colloquial"
        }:
            raise ValueError("v4 pairs require both query styles")
        first, second = pair
        for key in (
            "split", "should_abstain", "expected_answer", "expected_facts",
            "relevant_documents", "relevance_scores", "relevant_chunks", "evidence_requirements",
        ):
            if first[key] != second[key]:
                raise ValueError(f"v4 pair disagrees on {key}")
    if Counter(pair[0]["split"] for pair in pairs.values()) != Counter(
        {"dev": 10, "test": 10}
    ):
        raise ValueError("v4 requires ten pairs per split")
    sources = {doc["source"] for case in cases for doc in case["relevant_documents"]}
    if len(sources) < 12:
        raise ValueError("v4 requires Gold evidence from at least 12 policy files")
    required_categories = {
        "order", "return", "logistics", "payment", "refund", "warranty", "repair",
        "invoice", "promotion", "ticket", "privacy",
    }
    if not required_categories <= {case["category"] for case in cases}:
        raise ValueError("v4 is missing a required policy domain")
    if len({case["query"] for case in cases}) != len(cases):
        raise ValueError("v4 query texts must be unique")


def validate_v5_case_splits(cases: list[dict[str, Any]]) -> None:
    """Validate the 25 paired, answerable cases in the v5 challenge set."""
    if len(cases) != 50 or any(case["should_abstain"] for case in cases):
        raise ValueError("v5 requires 50 answerable cases")
    if len({case["query"] for case in cases}) != 50:
        raise ValueError("v5 queries must be unique")
    pairs: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        pairs.setdefault(case.get("pair_id", ""), []).append(case)
        if case.get("scenario_group") != case.get("pair_id"):
            raise ValueError("v5 scenario group must match pair ID")
    if set(pairs) != {f"pair-{index:02d}" for index in range(1, 26)}:
        raise ValueError("v5 requires pair-01 through pair-25")
    if Counter(case["query_style"] for case in cases) != Counter(
        {"formal": 25, "colloquial": 25}
    ):
        raise ValueError("v5 requires 25 queries per style")
    for pair_id, pair in pairs.items():
        if len(pair) != 2 or {case["query_style"] for case in pair} != {
            "formal", "colloquial"
        } or {case["id"] for case in pair} != {
            f"{pair_id}-formal", f"{pair_id}-colloquial"
        }:
            raise ValueError("v5 pairs require formal and colloquial queries")
        first, second = pair
        for key in (
            "split", "should_abstain", "expected_answer", "expected_facts",
            "relevant_documents", "relevance_scores", "relevant_chunks", "evidence_requirements",
        ):
            if first[key] != second[key]:
                raise ValueError(f"v5 pair disagrees on {key}")
        expected_split = "dev" if int(pair_id[-2:]) <= 23 else "test"
        if pair_id in {f"pair-{i:02d}" for i in range(21, 26)}:
            if first["split"] != expected_split or any(
                case.get("subset") != "rewrite_challenge" for case in pair
            ):
                raise ValueError("v5 new pairs require the declared split and challenge marker")
    if Counter(case["split"] for case in cases) != Counter({"dev": 26, "test": 24}):
        raise ValueError("v5 requires 26 dev and 24 test questions")


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
    chunk_lookup: dict[str, tuple[str, str, str, bool]] = {}
    if any("relevant_chunks" in case for case in dataset.get("cases", [])):
        from customer_support.rag import load_policy_chunks

        for chunk in load_policy_chunks(policy_path):
            chunk_lookup[str(chunk.metadata["chunk_id"])] = (
                str(chunk.metadata["source"]),
                str(chunk.metadata["title"]),
                chunk.page_content,
                bool(chunk.metadata["is_retrievable"]),
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
        if (
            dataset.get("version", "").startswith(("ordercare-rag-v3", "ordercare-rag-v4", "ordercare-rag-v5"))
            and not {
                "relevant_chunks",
                "evidence_requirements",
            }
            <= case.keys()
        ):
            raise ValueError("v3 cases require relevant_chunks and evidence_requirements")
        if "relevant_chunks" in case:
            labelled = case["relevant_chunks"]
            if len(labelled) != len({item["chunk_id"] for item in labelled}):
                raise ValueError("Relevant chunk labels must not contain duplicates")
            if {item["chunk_id"] for item in labelled} != set(
                case.get("evidence_requirements", {}).get("required_chunk_ids", [])
            ):
                raise ValueError("Evidence requirements and relevant chunks disagree")
            if {f"{item['source']}#{item['section']}" for item in labelled} != set(ids):
                raise ValueError("Relevant chunks and documents disagree")
            for item in labelled:
                found_chunk = chunk_lookup.get(item["chunk_id"])
                if (found_chunk is None or found_chunk[:2] != (item["source"], item["section"])
                    or not found_chunk[3]):
                    raise ValueError("Unknown or misplaced relevant chunk")
                quote = next(doc["evidence_quote"] for doc in docs if document_id(doc) ==
                             f"{item['source']}#{item['section']}")
                if quote not in found_chunk[2]:
                    raise ValueError("Gold evidence quote is absent from labelled chunk")
        if dataset.get("version", "").startswith("ordercare-rag-v3"):
            if case.get("query_style") not in {"colloquial", "formal"}:
                raise ValueError("v3 cases require a valid query_style")
            if not case.get("scenario_group"):
                raise ValueError("v3 cases require a scenario_group")
    if dataset.get("version", "").startswith("ordercare-rag-v3"):
        validate_v3_case_splits(cases)
    if dataset.get("version", "").startswith("ordercare-rag-v4"):
        validate_v4_case_splits(cases)
    if dataset.get("version", "").startswith("ordercare-rag-v5"):
        validate_v5_case_splits(cases)
        base_path = path.with_name("dataset-v4.json")
        if not base_path.exists() or dataset.get("base_dataset_sha256") != digest(base_path):
            raise ValueError("v5 base dataset checksum changed")
        base_cases = json.loads(base_path.read_text(encoding="utf-8"))["cases"]
        if cases[:40] != base_cases:
            raise ValueError("v5 must preserve all v4 cases and their order")
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
        recall = precision = mrr = ndcg = None
    else:
        recall = sum(g > 0 for g in gains) / len(grades)
        precision = sum(g > 0 for g in gains) / k
        mrr = next((1 / i for i, g in enumerate(gains, 1) if g > 0), 0.0)
        dcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(gains, 1))
        ideal = sorted(grades.values(), reverse=True)[:k]
        idcg = sum((2**g - 1) / math.log2(i + 1) for i, g in enumerate(ideal, 1))
        ndcg = dcg / idcg
    return {
        "recall": recall,
        "precision": precision,
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
            for metric in ("recall", "precision", "mrr", "ndcg", "context_relevance")
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
            for key in (
                "id",
                "query",
                "query_style",
                "category",
                "split",
                "should_abstain",
                "expected_answer",
            )
            if key in case
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
    result = {
        "method": method,
        "summary": summarize(rows, top_k),
        "splits": {
            split: summarize([r for r in rows if r["split"] == split], top_k)
            for split in ("dev", "test")
        },
        "cases": rows,
    }
    styles = sorted({str(case["query_style"]) for case in cases if case.get("query_style")})
    if styles:
        result["query_styles"] = {
            style: summarize([row for row in rows if row.get("query_style") == style], top_k)
            for style in styles
        }
    return result


def metadata(dataset_path: Path, configuration: dict[str, Any]) -> dict[str, Any]:
    configured_policy = configuration.get("policy")
    policy_path = Path(configured_policy) if isinstance(configured_policy, str) else POLICY_PATH
    files = [
        dataset_path,
        policy_path,
        Path("uv.lock"),
        Path("src/customer_support/rag.py"),
        Path("src/evaluation/rag.py"),
        Path("src/evaluation/llm.py"),
        Path("src/evaluation/three_way.py"),
        Path("scripts/evaluate_rag.py"),
        Path("scripts/evaluate_three_way_rag.py"),
        Path("scripts/build_rag_v3.py"),
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
        "Empty-context relevance is 0; no-answer queries are excluded from Recall/Precision/MRR/nDCG.",
        "",
        "| Method / split | Recall | Precision | MRR | nDCG | Context relevance | No-answer rejection | P95 ms | Errors |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def fmt(value: Any) -> str:
        return "N/A" if value is None else f"{value:.4f}"

    for run in report["runs"]:
        for split, s in {"all": run["summary"], **run["splits"]}.items():
            m = s[f"at_{k}"]
            values = [
                m["recall"],
                m["precision"],
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
