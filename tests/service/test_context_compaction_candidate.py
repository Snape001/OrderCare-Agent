"""Candidate assembly checks; production middleware selects it only by flag."""

import json

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from memory.compaction import _fingerprint
from memory.context_compaction_candidate import (
    CandidateBudget,
    CompactedContextAssembler,
)
from memory.context_manager import TokenBudget, count_tokens


def assembler(total=900, summary=320, recent=2):
    return CompactedContextAssembler(
        TokenBudget(total=total, system=250, history=350, memory=300, rag=300, tools=250),
        CandidateBudget(summary=summary, recent_turns=recent),
    )


def record(prefix, summary):
    last = prefix[-1]
    return {"cursor": f"{len(prefix) - 1}:{_fingerprint(last)}", "summary": summary}


def test_cursor_replaces_old_history_and_keeps_two_recent_turns():
    old = [HumanMessage(content="订单 ORD1001 不要创建工单"), AIMessage(content="收到")]
    recent = [
        HumanMessage(content="请先核验退款资格"), AIMessage(content="需要查询订单"),
        HumanMessage(content="如果不能退再维修"), AIMessage(content="明白"),
        HumanMessage(content="现在下一步呢？"),
    ]
    result = assembler().assemble(
        messages=[*old, *recent], system=SystemMessage(content="订单状态以业务库为准"),
        state={}, memory={}, compaction_record=record(old, {
            "constraints": ["不要创建工单"], "entities": ["ORD1001"],
            "citations": ["policy.md#维修"],
        }),
    )
    assert result.metrics["cursor_valid"] is True
    assert result.metrics["covered_messages"] == 2
    assert result.metrics["summary_injected"] is True
    assert result.metrics["recent_turns_preserved"] is True
    assert all(any(item is original for item in result.messages) for original in recent)
    assert all(item not in result.messages for item in old)
    assert result.system is not None and "ORD1001" in result.system.content
    assert "不要创建工单" in result.system.content
    assert "动态订单状态须重新核验" in result.system.content
    assert count_tokens(result.messages + [result.system]) <= 900


def test_bad_cursor_fails_closed_without_dropping_history():
    old = HumanMessage(content="重要的旧限制")
    current = HumanMessage(content="请继续")
    result = assembler().assemble(
        messages=[old, current], system=None, state={}, memory={},
        compaction_record={"cursor": "0:deadbeef", "summary": {"goals": ["伪摘要"]}},
    )
    assert result.metrics["cursor_valid"] is False
    assert old in result.messages and current in result.messages
    assert result.system is None or "伪摘要" not in result.system.content


def test_cursor_covering_required_recent_turn_falls_back():
    old = HumanMessage(content="很早的目标")
    recent_user = HumanMessage(content="需要人工审批")
    recent_answer = AIMessage(content="等待确认")
    current = HumanMessage(content="现在继续")
    prefix = [old, recent_user, recent_answer]
    result = assembler(recent=2).assemble(
        messages=[*prefix, current], system=None, state={}, memory={},
        compaction_record=record(prefix, {"goals": ["摘要"]}),
    )
    assert result.metrics["summary_injected"] is False
    assert result.metrics["reason"] == "recent_turns_not_preserved"
    assert recent_user in result.messages


def test_cursor_cannot_split_tool_call_pair():
    user = HumanMessage(content="查询订单")
    call = AIMessage(content="", tool_calls=[{"name": "get_order_status", "args": {}, "id": "a"}])
    tool = ToolMessage(content="真实结果", name="get_order_status", tool_call_id="a")
    current = HumanMessage(content="继续")
    result = assembler().assemble(
        messages=[user, call, tool, current], system=None, state={}, memory={},
        compaction_record={"cursor": f"1:{_fingerprint(call)}",
                           "summary": {"goals": ["旧目标"]}},
    )
    assert result.metrics["cursor_valid"] is False
    assert result.metrics["summary_injected"] is False


def test_current_tool_pair_rag_budget_and_approval_state_survive():
    old = [HumanMessage(content="订单 ORD2002，先核验退款"), AIMessage(content="收到")]
    current = HumanMessage(content="现在查维修政策")
    call = AIMessage(content="", tool_calls=[{"name": "search_policy", "args": {}, "id": "p"}])
    tool = ToolMessage(content="维修证据", name="search_policy", tool_call_id="p")
    result = assembler(recent=1).assemble(
        messages=[*old, current, call, tool], system=SystemMessage(content="禁止未经确认建工单"),
        state={"approval": {"status": "pending", "action": "create_support_ticket"},
               "plan": {"steps": [{"action": "search_policy"}]}},
        memory={"working": {"verified": True, "current_order": "ORD2002"}},
        compaction_record=record(old, {"entities": ["ORD2002"],
                                       "constraints": ["先核验退款"]}),
    )
    assert result.messages[-3:] == [current, call, tool]
    assert result.system is not None
    assert "pending" in result.system.content
    assert "create_support_ticket" in result.system.content
    assert "verified" in result.system.content
    assert "ORD2002" in result.system.content
    assert "动态订单状态须重新核验" in result.system.content


def test_summary_budget_prioritizes_facts_and_removes_exact_duplicates():
    old = [HumanMessage(content="订单 ORD1001，不要创建工单"), AIMessage(content="收到")]
    recent = [HumanMessage(content="我希望文字客服"), AIMessage(content="明白"),
              HumanMessage(content="下一步？")]
    summary = {
        "constraints": ["不要创建工单", "不要创建工单"],
        "entities": ["ORD1001"], "preferences": ["我希望文字客服"],
        "goals": ["维修耳机"],
    }
    result = assembler(summary=150, recent=1).assemble(
        messages=[*old, *recent], system=SystemMessage(content="规则"), state={},
        memory={"notes": [{"kind": "support_summary", "value": "无关发票记录"}]},
        compaction_record=record(old, summary),
    )
    assert result.metrics["cursor_valid"] is True
    assert result.metrics["summary_injected"] is True
    assert result.metrics["post_assembly_duplicate_facts"] == 0
    assert result.metrics["source_duplicate_facts"] >= 2
    assert result.system is not None and "无关发票记录" not in result.system.content
    assert "不要创建工单" in result.system.content
    assert "我希望文字客服" not in result.system.content.split("压缩历史")[-1]
    assert json.dumps(summary, ensure_ascii=False) not in result.system.content


def test_insufficient_budget_for_key_fact_keeps_original_history():
    old = [HumanMessage(content="订单 ORD1001 不要创建工单"), AIMessage(content="收到")]
    current = HumanMessage(content="现在怎么办")
    result = assembler(summary=1, recent=1).assemble(
        messages=[*old, current], system=None, state={}, memory={},
        compaction_record=record(old, {"constraints": ["不要创建工单"],
                                       "entities": ["ORD1001"]}),
    )
    assert result.metrics["summary_injected"] is False
    assert result.metrics["reason"] == "summary_budget_insufficient"
    assert old[0] in result.messages


def test_session_and_long_term_memory_follow_compacted_summary():
    old = [HumanMessage(content="耳机维修订单 ORD1001"), AIMessage(content="收到")]
    current = HumanMessage(content="耳机维修下一步")
    result = assembler(recent=1).assemble(
        messages=[*old, current], system=SystemMessage(content="规则"), state={},
        memory={"summary": "耳机维修偏好文字沟通", "notes": [
            {"kind": "preference", "value": "耳机维修希望文字客服", "updated_at": "2026-11-06"}
        ]},
        compaction_record=record(old, {"entities": ["ORD1001"]}),
    )
    assert result.system is not None
    text = str(result.system.content)
    assert text.index("压缩历史") < text.index("耳机维修偏好文字沟通")
    assert "耳机维修希望文字客服" in text


def test_legacy_cursor_uses_earliest_match_and_never_skips_new_history():
    repeated = AIMessage(content="收到")
    old = [HumanMessage(content="旧目标"), repeated]
    newer = [HumanMessage(content="新约束"), AIMessage(content="收到"),
             HumanMessage(content="当前问题")]
    result = assembler().assemble(
        messages=[*old, *newer], system=None, state={}, memory={},
        compaction_record={"cursor": _fingerprint(repeated),
                           "summary": {"goals": ["旧目标"]}},
    )
    assert result.metrics["cursor_valid"] is True
    assert result.metrics["covered_messages"] == 2
    assert any(item is newer[0] for item in result.messages)
