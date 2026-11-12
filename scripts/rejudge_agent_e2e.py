"""Re-score saved Agent runs without invoking the Agent or changing their original results."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_agent_e2e import judge_prompt, report  # noqa: E402

from core import settings  # noqa: E402
from core.llm import get_model  # noqa: E402
from evaluation.agent_e2e import (  # noqa: E402
    deterministic_checks,
    judgment_checks,
    retrieval_score,
)
from evaluation.llm import parse_json  # noqa: E402
from evaluation.rag import digest  # noqa: E402
from schema.models import DeepseekModelName  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--allow-paid-api", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid_api:
        parser.error("DeepSeek Judge requires --allow-paid-api")
    dataset_path = ROOT / "data/evaluation/agent-e2e-cases-v1.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    previous = json.loads((args.source / "summary.json").read_text(encoding="utf-8"))
    if previous["dataset_sha256"] != digest(dataset_path):
        raise ValueError("Case data changed since the source run")
    output = args.source.parent / (args.source.name + "-rejudge-" +
                                   datetime.now(UTC).strftime("%H%M%S"))
    output.mkdir(parents=True, exist_ok=False)
    judge_model = get_model(DeepseekModelName.DEEPSEEK_CHAT).model_copy(update={"temperature": 0})
    rows = []
    for case in dataset["cases"]:
        source = args.source / case["id"] / "result.json"
        row = json.loads(source.read_text(encoding="utf-8"))
        if "executed_tools" not in row:
            row["passed"] = False
            rows.append(row)
            continue
        executed = row["executed_tools"]
        row["deterministic"] = deterministic_checks(
            case, row["proposed_tools"], executed, row["tickets_before"],
            row["tickets_after"], row["interrupted"], row["answer"])
        row["retrieval"] = retrieval_score(case, executed)
        started = time.perf_counter()
        try:
            response = await asyncio.wait_for(judge_model.ainvoke(judge_prompt(
                case, row["answer"], executed, row["tickets_before"],
                row["tickets_after"], row["interrupt_value"])), timeout=180)
            row["judge"] = judgment_checks(case, parse_json(response.content))
            row["judge_usage"] = response.usage_metadata or {}
        except Exception as exc:
            row["judge"] = {"status": "error", "error_type": type(exc).__name__,
                            "error": str(exc)[:300]}
        row["judge_latency_ms"] = round((time.perf_counter()-started)*1000, 1)
        row["passed"] = row["deterministic"]["passed"] and row["judge"].get("passed") is True
        target = output / case["id"]
        target.mkdir()
        (target / "result.json").write_text(json.dumps(row, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
        rows.append(row)
        print(f"{case['id']}: {'PASS' if row['passed'] else 'FAIL'}", flush=True)
    summary = report(rows, previous["dataset_sha256"], previous["policy_sha256"],
                     settings.DEEPSEEK_MODEL)
    summary.update(source_run=str(args.source), declared_policy_sha256=previous["declared_policy_sha256"],
                   corpus_drift_accepted=previous["corpus_drift_accepted"],
                   completed_at=datetime.now(UTC).isoformat())
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Results: {output}")
    return 0 if summary["passed"] == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
