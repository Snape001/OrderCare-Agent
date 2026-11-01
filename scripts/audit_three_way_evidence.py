"""Answer-blind DeepSeek evidence audit with one call per unique case/context."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core import settings  # noqa: E402
from evaluation.evidence import (  # noqa: E402
    AUDIT_VERSION,
    EvidenceAudit,
    audit_metrics,
    context_digest,
    evidence_messages,
)
from evaluation.generation import GenerationRunner  # noqa: E402
from evaluation.llm import parse_json  # noqa: E402
from evaluation.rag import digest, load_dataset  # noqa: E402
from evaluation.three_way import save_json, validated_dataset  # noqa: E402
from schema.models import DeepseekModelName  # noqa: E402

OUTPUT = Path("data/evaluation/rag/three-way-comparison-v1")


def context_for_audit(hits: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "evidence_id": f"E{i}",
            "source": h["source"],
            "title": h["title"],
            "content": h["content"],
        }
        for i, h in enumerate(hits, 1)
    ]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-paid-api", action="store_true")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not args.allow_paid_api:
        parser.error("DeepSeek evidence audit requires explicit --allow-paid-api")
    retrieval_path = args.output / "results.json"
    retrieval = json.loads(retrieval_path.read_text(encoding="utf-8"))
    if retrieval["status"] != "retrieval_complete":
        parser.error("Complete retrieval results required")
    configuration = retrieval["metadata"]["configuration"]
    dataset_path = Path(configuration.get("dataset", "data/evaluation/rag/dataset-v1.json"))
    policy_path = Path(configuration.get("policy", "data/policies/customer_service_policy.md"))
    labels = {
        c["id"]: c
        for c in (
            load_dataset(dataset_path, policy_path)
            if policy_path.is_dir()
            else validated_dataset(dataset_path, args.output / "frozen-policy-v1.md")
        )["cases"]
    }
    manifest = {
        "retrieval_sha256": digest(retrieval_path),
        "dataset_sha256": digest(dataset_path),
        "policy_sha256": digest(policy_path),
        "audit_version": AUDIT_VERSION,
        "implementation_sha256": digest(Path("src/evaluation/evidence.py")),
        "model": settings.DEEPSEEK_MODEL,
        "temperature": 0,
        "max_tokens": 1000,
    }
    path = args.output / "evidence-results.json"
    if path.exists():
        cache = json.loads(path.read_text(encoding="utf-8"))
        if cache["manifest"] != manifest:
            parser.error("Evidence cache manifest mismatch")
    else:
        cache = {"manifest": manifest, "cases": {}, "mapping": {}}
    pending: list[tuple[str, dict[str, Any], list[dict[str, str]]]] = []
    for run in retrieval["runs"]:
        for row in run["cases"]:
            case = labels[row["id"]]
            context = context_for_audit(row["hits"])
            key = f"{row['id']}:{context_digest(context)}"
            cache["mapping"][f"{run['method']}:{row['id']}"] = key
            if key not in cache["cases"] and key not in {p[0] for p in pending}:
                pending.append((key, case, context))
    save_json(path, cache)
    if not pending:
        print("Evidence audit reused; no API calls", flush=True)
        return 0
    runner = GenerationRunner(
        "configured", settings.DEEPSEEK_MODEL, True, True,
        configured_model=DeepseekModelName.DEEPSEEK_CHAT,
    )
    runner.judge_model = runner.judge_model.model_copy(
        update={"temperature": 0, "max_tokens": 1000, "streaming": False}
    )
    try:
        for key, case, context in pending:
            entry: dict[str, Any] = {
                "id": case["id"],
                "context_sha256": context_digest(context),
                "metrics": {"evidence_sufficiency": None, "fact_evidence_coverage": None},
            }
            if case["should_abstain"]:
                entry.update(
                    status="ok",
                    origin="frozen_no_answer_label",
                    metrics={"evidence_sufficiency": 0.0, "fact_evidence_coverage": None},
                )
            else:
                messages = evidence_messages(case, context)
                messages[0].content += "\nJSON schema: " + json.dumps(
                    EvidenceAudit.model_json_schema()
                )
                try:
                    raw = runner.call(runner.judge_model, messages)
                except Exception as exc:
                    entry.update(status="api_error", error_type=type(exc).__name__)
                    cache["cases"][key] = entry
                    save_json(path, cache)
                    raise RuntimeError("DeepSeek evidence API failed; no fallback") from exc
                entry["raw"] = raw
                try:
                    if raw["response_metadata"].get("done_reason") == "length":
                        raise ValueError("Evidence judge output truncated")
                    verdict = EvidenceAudit.model_validate(parse_json(raw["raw_response"]))
                    entry.update(
                        status="ok",
                        origin="answer_blind_deepseek_judge",
                        parsed=verdict.model_dump(),
                        metrics=audit_metrics(case, context, verdict),
                    )
                except Exception as exc:
                    entry.update(status="invalid_judge", error_type=type(exc).__name__)
            cache["cases"][key] = entry
            save_json(path, cache)
            print(f"{case['id']} evidence={entry['status']}", flush=True)
    finally:
        runner.close()
        save_json(path, cache)
    return int(any(e["status"] != "ok" for e in cache["cases"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
