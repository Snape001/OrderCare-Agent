from evaluation.agent_e2e import deterministic_checks, judgment_checks, retrieval_score


def case(**overrides):
    value = {
        "id": "agent-e2e-001", "expected_tool_sequence": ["search_policy"],
        "expected_state": {"support_tickets_created": 0}, "policy_refs": ["p.md#退货"],
        "should_abstain": False, "expected_answer_facts": ["可申请"],
        "forbidden_behaviors": ["保证通过"],
    }
    return value | overrides


def test_retrieval_uses_sections_only_for_expected_search():
    result = [{"name": "search_policy", "value": {"references": [
        {"source": "p.md", "title": "退货"}]}}]
    assert retrieval_score(case(), result)["recall_at_3"] == 1
    assert retrieval_score(case(expected_tool_sequence=[]), result) is None
    assert retrieval_score(case(should_abstain=True, policy_refs=[]), result)["recall_at_3"] is None


def test_rejected_ticket_requires_proposal_and_no_write():
    ticket = case(expected_tool_sequence=["create_support_ticket"],
                  expected_hitl_decision="reject", policy_refs=[])
    good = deterministic_checks(ticket, ["create_support_ticket"], [], [], [], True, "未创建")
    assert good["passed"]
    identity = [{"name": "get_order_status", "args": {"order_id": "ORD1001",
                 "phone_last4": "8821"}, "value": {"ok": True}}]
    assert deterministic_checks(ticket | {"order_fixture": "ORD1001"},
                                ["get_order_status", "create_support_ticket"],
                                identity, [], [], True, "未创建")["passed"]
    assert not deterministic_checks(ticket, ["create_support_ticket"], [],
                                    [{"id": "T1"}], [], True, "未创建")["passed"]


def test_conditional_sequence_and_identity():
    conditional = case(id="agent-e2e-014", order_fixture="ORD1003",
                       expected_tool_sequence=["get_order_status", "check_refund_eligibility",
                                               {"tool": "search_policy", "when": "refund_ineligible"}])
    results = [{"name": "get_order_status", "args": {"order_id": "ORD1003", "phone_last4": "8821"}, "value": {"ok": True}},
               {"name": "check_refund_eligibility", "args": {"order_id": "ORD1003", "phone_last4": "8821"},
                "value": {"ok": True, "eligible": False}},
               {"name": "search_policy", "args": {}, "value": {"references": []}}]
    assert deterministic_checks(conditional, [r["name"] for r in results], results,
                                [], [], False, "答复")["passed"]
    results[0]["args"]["phone_last4"] = "0000"
    assert not deterministic_checks(conditional, [], results, [], [], False, "答复")["passed"]


def test_judge_must_cover_every_fact_and_forbidden_behavior():
    value = {"facts_correct": [True], "forbidden_present": [False], "grounded": True,
             "goal_completed": True, "boundary_respected": True, "reason": "符合"}
    assert judgment_checks(case(), value)["passed"]
    assert not judgment_checks(case(), value | {"forbidden_present": [True]})["passed"]
