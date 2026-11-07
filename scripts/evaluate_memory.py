"""Reproducible offline Memory A/B with the project's cached real BGE embedding.

No LLM Provider is contacted. Task completion remains unscored without a real
end-to-end model run; fact retention is an explicitly labelled string proxy.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from evaluate_compaction_candidate import evaluate as evaluate_compaction
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from agents.customer_support_agent import SYSTEM_PROMPT
from core.settings import settings
from customer_support.rag import get_policy_knowledge_base
from memory.context_manager import ContextManager, TokenBudget, count_tokens
from memory.episodic import EpisodicMemory, completed_episode
from memory.layers import LayeredMemory, MemoryUnavailable

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/evaluation/memory/dataset-v1.json"
OUTPUT = ROOT / "data/evaluation/memory/results-v1/results.json"


class IsolatedRedis:
    """Offline adapter for the real LayeredMemory API; not a Redis benchmark."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.fail = False

    async def ping(self) -> bool:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        return True

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        self.data[key] = value
        self.ttl[key] = ex

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.data.pop(key, None)

    async def aclose(self) -> None:
        return None


def validate_dataset(dataset: dict[str, Any]) -> None:
    events = dataset["events"]
    cases = dataset["cases"]
    by_id = {event["id"]: event for event in events}
    if len(events) != len(by_id) or len(cases) != len({case["id"] for case in cases}):
        raise ValueError("Duplicate event or case ID")
    if not 30 <= len(cases) <= 50:
        raise ValueError("Memory dataset must contain 30-50 cases")
    for case in cases:
        relevant = case["relevant_memory_ids"]
        if len(relevant) != len(set(relevant)):
            raise ValueError(f"Duplicate labels in {case['id']}")
        if any(identifier not in by_id for identifier in relevant):
            raise ValueError(f"Unknown relevant episode in {case['id']}")
        if any(by_id[identifier]["customer_id"] != case["customer_id"] for identifier in relevant):
            raise ValueError(f"Cross-customer Ground Truth in {case['id']}")
        if any(identifier not in by_id for identifier in case.get("forbidden_memory_ids", [])):
            raise ValueError(f"Unknown forbidden episode in {case['id']}")


def retrieval_metrics(ranked: list[str], relevant: list[str], k: int) -> dict[str, float] | None:
    if not relevant:
        return None
    top = ranked[:k]
    hits = len(set(top) & set(relevant))
    first = next((index + 1 for index, identifier in enumerate(top)
                  if identifier in relevant), None)
    return {
        "recall_at_k": round(hits / len(relevant), 4),
        "precision_at_k": round(hits / k, 4),
        "mrr": round(1 / first if first else 0.0, 4),
    }


def _mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    return round(sum(values) / len(values), 4) if values else None


async def evaluate(dataset_path: Path = DATASET, *, top_k: int = 4) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    validate_dataset(dataset)
    as_of = datetime.fromisoformat(dataset["as_of"])
    embedding = get_policy_knowledge_base().embedding
    budget = TokenBudget(
        total=settings.CONTEXT_TOKEN_BUDGET, system=settings.CONTEXT_SYSTEM_BUDGET,
        history=settings.CONTEXT_HISTORY_BUDGET, memory=settings.CONTEXT_MEMORY_BUDGET,
        rag=settings.CONTEXT_RAG_BUDGET, tools=settings.CONTEXT_TOOLS_BUDGET,
    )
    prior_compaction = await evaluate_compaction()
    compaction_rows = {row["id"]: row for row in prior_compaction["cases"]}
    rows: list[dict[str, Any]] = []
    # Chroma holds Windows index files open until process exit. Rebuild in a
    # dedicated ignored directory rather than deleting it while the client lives.
    work_root = ROOT / "data/evaluation/memory/results-v1/_work"
    work_root.mkdir(parents=True, exist_ok=True)
    with nullcontext(str(work_root)) as directory:
        work = Path(directory)
        episodes = EpisodicMemory(persist_directory=work / "chroma", embedding=embedding,
                                  similarity_threshold=settings.EPISODIC_SIMILARITY_THRESHOLD,
                                  recency_weight=settings.EPISODIC_RECENCY_WEIGHT)
        episodes.store.delete_collection()
        episodes = EpisodicMemory(persist_directory=work / "chroma", embedding=embedding,
                                  similarity_threshold=settings.EPISODIC_SIMILARITY_THRESHOLD,
                                  recency_weight=settings.EPISODIC_RECENCY_WEIGHT)
        memory = LayeredMemory("redis://offline-adapter", work / "profiles.db", ttl=120)
        redis = IsolatedRedis()
        memory.redis = redis  # type: ignore[assignment]
        await memory.setup()
        for customer, channel in dataset["profile_seeds"].items():
            await memory.delete_profile(customer)
            await memory.upsert_profile(customer, channel)
        ids: dict[str, str] = {}
        for event in dataset["events"]:
            route = {"intents": [event["event_type"]],
                     "entities": {"product_name": event["product"]}}
            episode = completed_episode({"route": route, "task_trace": [
                {"action": event["action"], "status": "done"}
            ]})
            if episode is None or episode[0] != event["event_type"]:
                raise ValueError(f"Could not extract event {event['id']}")
            ids[event["id"]] = await episodes.upsert(
                customer_id=event["customer_id"], event_type=episode[0],
                summary=episode[1], source_session=event["source_session"],
                created_at=as_of - timedelta(days=event["age_days"]),
            )
        reverse_ids = {value: key for key, value in ids.items()}
        system = SystemMessage(content=SYSTEM_PROMPT)
        for case in dataset["cases"]:
            started = perf_counter()
            customer = case["customer_id"]
            query = case["query"]
            baseline_messages: list[AnyMessage] = [HumanMessage(content=query)]
            baseline_tokens = count_tokens([system, *baseline_messages])
            status = "ok"
            recovered = False
            hits: list[dict[str, Any]] = []
            profile = None
            if case.get("inject_failure") == "redis":
                redis.fail = True
                try:
                    await memory.session("eval-owner", case["id"])
                except MemoryUnavailable:
                    status = "redis_failed_closed"
                finally:
                    redis.fail = False
                recovered = await memory.session("eval-owner", case["id"]) == {}
            if case.get("inject_failure") == "chroma":
                original = episodes.store.similarity_search_with_score

                def fail_search(*args: Any, **kwargs: Any) -> Any:
                    raise RuntimeError("injected Chroma failure")

                episodes.store.similarity_search_with_score = fail_search  # type: ignore[method-assign]
                try:
                    await episodes.search(customer_id=customer, query=query, k=top_k, now=as_of)
                except MemoryUnavailable:
                    status = "chroma_failed_closed"
                finally:
                    episodes.store.similarity_search_with_score = original  # type: ignore[method-assign]
                recovered = bool(await episodes.search(
                    customer_id=customer, query=query, k=top_k, now=as_of
                ))
            if customer and status == "ok":
                hits = await episodes.search(customer_id=customer, query=query,
                                             k=top_k, now=as_of)
                if case.get("profile_update"):
                    await memory.upsert_profile(customer, case["profile_update"])
                profile = await memory.get_profile(customer)
            working = case.get("working") or {}
            if working:
                await memory.save_session("eval-owner", case["id"], {"working": working})
                working = (await memory.session("eval-owner", case["id"]))["working"]
            notes = [*hits]
            if customer and status == "ok":
                note = await memory.profile_note(customer)
                if note:
                    notes.insert(0, note)
            view, view_system = ContextManager(budget).assemble(
                messages=baseline_messages, system=system, state={},
                memory={"working": working, "notes": notes},
            )
            visible = str(view_system.content if view_system else "") + "\n" + "\n".join(
                str(message.content) for message in view
            )
            ranked = [reverse_ids[hit["memory_id"]] for hit in hits]
            relevant = case["relevant_memory_ids"]
            baseline = retrieval_metrics([], relevant, top_k)
            candidate = retrieval_metrics(ranked, relevant, top_k)
            case_result: dict[str, Any] = {
                "id": case["id"], "category": case["category"], "query": query,
                "customer_id": customer, "ground_truth_memory_ids": relevant,
                "status": status, "failure_recovered": recovered,
                "A": {"ranked_memory_ids": [], "retrieval": baseline,
                      "profile": None, "context_tokens": baseline_tokens},
                "B": {"ranked_memory_ids": ranked, "retrieval": candidate,
                      "profile": profile["communication_channel"] if profile else None,
                      "context_tokens": count_tokens(view + ([view_system] if view_system else [])),
                      "injected_memory_ids": [reverse_ids[hit["memory_id"]] for hit in hits
                                              if hit["value"] in visible],
                      "retrieval_hits": [
                          {"id": reverse_ids[hit["memory_id"]], "similarity": hit["similarity"],
                           "score": hit["score"], "source_session": hit["source_session"],
                           "summary": hit["value"]} for hit in hits
                      ]},
                "elapsed_ms": round((perf_counter() - started) * 1000, 2),
                "isolation_ok": not any(identifier in ranked for identifier in
                                        case.get("forbidden_memory_ids", [])),
                "profile_ok": (profile is not None and profile["communication_channel"]
                               == case["expected_profile"])
                              if "expected_profile" in case else None,
            }
            if case.get("required_facts") and case["category"] == "same_session":
                case_result["fact_checks"] = {
                    "A": {fact: fact in query for fact in case["required_facts"]},
                    "B": {fact: fact in visible for fact in case["required_facts"]},
                }
            if case.get("history_case"):
                comparison = compaction_rows[case["history_case"]]
                case_result["compaction"] = comparison
                # The A arm sees only the last request of the frozen conversation.
                source = next(item for item in json.loads(
                    (ROOT / "data/evaluation/context-compaction-v2/dataset-v1.json")
                    .read_text(encoding="utf-8"))["cases"]
                    if item["id"] == case["history_case"])
                last_request = next(item["content"] for item in reversed(source["messages"])
                                    if item["role"] == "user")
                case_result["fact_checks"] = {
                    "A": {fact: fact in last_request or fact in source["system"]
                          for fact in case["required_facts"]},
                    "B": comparison["fact_checks"]["replacement"],
                }
            rows.append(case_result)
    positives = [row for row in rows if row["ground_truth_memory_ids"]
                 and row["status"] == "ok"]
    cross = [row for row in positives if row["category"] == "cross_session"]
    profiles = [row for row in rows if row["profile_ok"] is not None
                and row["status"] == "ok"]
    isolated = [row for row in rows if row["category"] in {"isolation", "unverified"}]
    recency_cases = [row for row in rows if row["category"] == "recency"]
    facts = [row for row in rows if "fact_checks" in row]
    def retention(arm: str) -> float | None:
        checks = [passed for row in facts for passed in row["fact_checks"][arm].values()]
        return round(sum(checks) / len(checks), 4) if checks else None
    def arm_metrics(arm: str) -> dict[str, Any]:
        return {
            "memory_recall_at_k": _mean([row[arm]["retrieval"] or {} for row in positives],
                                        "recall_at_k"),
            "memory_precision_at_k": _mean([row[arm]["retrieval"] or {} for row in positives],
                                           "precision_at_k"),
            "mrr": _mean([row[arm]["retrieval"] or {} for row in positives], "mrr"),
            "cross_session_recall": _mean([row[arm]["retrieval"] or {} for row in cross],
                                          "recall_at_k"),
            "memory_injection_recall": round(
                sum(len(set(row[arm].get("injected_memory_ids", [])) &
                        set(row["ground_truth_memory_ids"])) for row in positives)
                / sum(len(row["ground_truth_memory_ids"]) for row in positives), 4
            ),
            "profile_accuracy": round(sum(row["profile_ok"] if arm == "B" else False
                                          for row in profiles) / len(profiles), 4),
            "fact_retention": retention(arm),
            "user_isolation": round(sum(row["isolation_ok"] for row in isolated)
                                    / len(isolated), 4),
            "recency_order_accuracy": round(sum(
                [identifier for identifier in row[arm]["ranked_memory_ids"]
                 if identifier in row["ground_truth_memory_ids"]]
                == row["ground_truth_memory_ids"] for row in recency_cases
            ) / len(recency_cases), 4),
            "task_completion_rate": None,
        }
    long_rows = [row["compaction"] for row in rows if "compaction" in row]
    raw_total = sum(row["raw_estimated_tokens"] for row in long_rows)
    replacement_total = sum(row["replacement_estimated_tokens"] for row in long_rows)
    failures = [
        {"id": row["id"], "category": row["category"],
         "missing_memory_ids": sorted(set(row["ground_truth_memory_ids"])
                                      - set(row["B"]["ranked_memory_ids"])),
         "not_injected": sorted(set(row["ground_truth_memory_ids"])
                                - set(row["B"]["injected_memory_ids"])),
         "status": row["status"]}
        for row in rows if row["status"] != "ok" or
        (row["ground_truth_memory_ids"] and
         not set(row["ground_truth_memory_ids"]).issubset(
             row["B"]["injected_memory_ids"])) or row["profile_ok"] is False
    ]
    ranking_failures = [
        {"id": row["id"], "category": row["category"],
         "expected": row["ground_truth_memory_ids"],
         "ranked": row["B"]["ranked_memory_ids"],
         "reason": "Top-1 event differs from manually labelled event; inspect negation or event ambiguity"}
        for row in positives if row["B"]["ranked_memory_ids"]
        and row["B"]["ranked_memory_ids"][0] not in row["ground_truth_memory_ids"]
    ]
    return {
        "dataset": str(dataset_path.relative_to(ROOT)).replace("\\", "/"),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "annotation_status": dataset["annotation_status"],
        "configuration": {
            "as_of": dataset["as_of"], "top_k": top_k,
            "embedding": getattr(embedding, "model_name", type(embedding).__name__),
            "embedding_dimensions": len(embedding.embed_query("耳机维修")),
            "similarity_threshold": settings.EPISODIC_SIMILARITY_THRESHOLD,
            "recency_weight": settings.EPISODIC_RECENCY_WEIGHT,
            "context_budget": vars(budget), "compaction_summary_budget": 320,
            "compaction_forced_trigger_budget": 350, "api_calls": 0,
            "redis_mode": "isolated in-process adapter; production LayeredMemory API",
        },
        "case_count": len(rows), "positive_retrieval_count": len(positives),
        "metrics": {"A": arm_metrics("A"), "B": arm_metrics("B"),
                    "context_token_reduction_vs_full_history":
                    round((raw_total - replacement_total) / raw_total, 4),
                    "long_context_raw_tokens": raw_total,
                    "long_context_compacted_tokens": replacement_total,
                    "avg_case_latency_ms_B": _mean(rows, "elapsed_ms")},
        "failures": failures, "ranking_failures": ranking_failures, "cases": rows,
        "limitations": [
            "Synthetic author-labelled events, no independent manual review or real customer data",
            "A has no Memory; same-session Checkpoint history is intentionally excluded",
            "No real model was called; task completion rate is null, not inferred from fact checks",
            "Long-dialogue compaction reuses two prior short synthetic cases with forced trigger",
            "Offline Redis adapter is not a real Redis throughput or outage benchmark",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")
    report = asyncio.run(evaluate(args.dataset.resolve(), top_k=args.top_k))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"case_count": report["case_count"],
                      "metrics": report["metrics"], "failures": len(report["failures"])},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
