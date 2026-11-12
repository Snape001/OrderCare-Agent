"""Deterministic checks and structured dialogue judging for customer-support E2E cases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class DialogueJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts_correct: list[StrictBool]
    forbidden_present: list[StrictBool]
    grounded: StrictBool
    goal_completed: StrictBool
    boundary_respected: StrictBool
    reason: str = Field(max_length=300)


def expected_tools(case: dict[str, Any], results: list[dict[str, Any]]) -> list[str]:
    refund = next((r for r in results if r["name"] == "check_refund_eligibility"), None)
    names = []
    for item in case["expected_tool_sequence"]:
        if isinstance(item, str):
            names.append(item)
        elif item["when"] == "refund_ineligible" and refund and refund["value"].get("eligible") is False:
            names.append(item["tool"])
    return names


def retrieval_score(case: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not any(
        item == "search_policy" or isinstance(item, dict) and item.get("tool") == "search_policy"
        for item in case["expected_tool_sequence"]
    ):
        return None
    searches = [r for r in results if r["name"] == "search_policy"]
    if case["should_abstain"]:
        return {"expected_refs": [], "found_refs": [], "recall_at_3": None,
                "search_called": bool(searches)}
    gold = set(case["policy_refs"])
    found = {
        f"{Path(hit['source']).resolve().relative_to(Path.cwd().resolve()).as_posix()}#{hit['title']}"
        for result in searches
        for hit in result["value"].get("references", [])[:3]
        if isinstance(hit, dict) and "source" in hit and "title" in hit
    }
    return {"expected_refs": sorted(gold), "found_refs": sorted(found),
            "recall_at_3": len(gold & found) / len(gold) if gold else None,
            "search_called": bool(searches)}


def deterministic_checks(
    case: dict[str, Any], proposed: list[str], executed: list[dict[str, Any]],
    before: list[dict[str, Any]], after: list[dict[str, Any]], interrupted: bool,
    answer: str,
) -> dict[str, Any]:
    names = [r["name"] for r in executed]
    expected = expected_tools(case, executed)
    ticket = case.get("expected_hitl_decision")
    expected_executed = [name for name in expected if name != "create_support_ticket" or ticket == "approve"]
    sequence_at = 0
    extra: list[str] = []
    for name in names:
        if sequence_at < len(expected_executed) and name == expected_executed[sequence_at]:
            sequence_at += 1
        else:
            extra.append(name)
    checks: dict[str, bool] = {
        "tool_sequence": sequence_at == len(expected_executed),
        "safe_extra_tools": all(name in {"search_policy", "get_order_status"} or
                                name in expected_executed for name in extra),
        "ticket_proposal": ticket is None or "create_support_ticket" in proposed,
        "no_unexpected_ticket": ticket is not None or "create_support_ticket" not in proposed,
        "ticket_count": len(after) == case["expected_state"]["support_tickets_created"],
        "preapproval_no_write": ticket is None or len(before) == 0,
        "hitl_interrupt": ticket is None or interrupted,
    }
    if case["expected_state"].get("ticket_order_id"):
        checks["ticket_order"] = len(after) == 1 and after[0]["order_id"] == case["expected_state"]["ticket_order_id"]
    if case["expected_state"].get("order_details_disclosed") is False:
        checks["privacy"] = not any(word in answer for word in ("无线耳机", "机械键盘", "运输中", "已签收"))
    if case["expected_state"].get("refund_executed") is False:
        checks["no_refund_write"] = "execute_refund" not in proposed + names
    for result in executed:
        if result["name"] in {"get_order_status", "check_refund_eligibility"}:
            expected_id = case.get("order_fixture")
            if expected_id:
                checks.setdefault("order_argument", True)
                checks["order_argument"] &= result["args"].get("order_id", "").upper() == expected_id
            checks.setdefault("phone_argument", True)
            expected_phone = "0000" if case["id"] == "agent-e2e-007" else "8821"
            checks["phone_argument"] &= result["args"].get("phone_last4") == expected_phone
    return {"checks": checks, "passed": all(checks.values()),
            "expected_executed": expected_executed, "actual_executed": names,
            "exact_tool_sequence": names == expected_executed,
            "extra_read_tools": extra}


def judgment_checks(case: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    judgment = DialogueJudgment.model_validate(value)
    if len(judgment.facts_correct) != len(case["expected_answer_facts"]):
        raise ValueError("Judge omitted an expected fact")
    if len(judgment.forbidden_present) != len(case["forbidden_behaviors"]):
        raise ValueError("Judge omitted a forbidden behavior")
    passed = (all(judgment.facts_correct) and not any(judgment.forbidden_present)
              and judgment.grounded and judgment.goal_completed and judgment.boundary_respected)
    return {"passed": passed, **judgment.model_dump()}
