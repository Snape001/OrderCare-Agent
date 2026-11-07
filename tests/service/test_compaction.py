import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from memory.compaction import AutomaticCompactor
from memory.context_manager import ContextManager, TokenBudget, count_tokens
from memory.layers import LayeredMemory, MemoryUnavailable


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.lock = asyncio.Lock()
        self.fail = False

    async def get(self, key):
        if self.fail:
            raise ConnectionError("redis down")
        return self.values.get(key)

    async def set(self, key, value, ex):
        if self.fail:
            raise ConnectionError("redis down")
        self.values[key] = value

    async def eval(self, script, keys, key, expected, cursor, summary, ttl):
        if self.fail:
            raise ConnectionError("redis down")
        async with self.lock:
            value = json.loads(self.values.get(key, "{}"))
            old = value.get("cursor", "")
            if old != expected:
                return 0
            value = {"cursor": cursor, "summary": json.loads(summary)}
            self.values[key] = json.dumps(value)
            return 1

    async def aclose(self):
        pass


@pytest.fixture
def rig(tmp_path, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("memory.layers.Redis.from_url", lambda *args, **kwargs: fake)
    memory = LayeredMemory("redis://fake", tmp_path / "memory.db", ttl=120)
    return AutomaticCompactor(memory, threshold=0.8, summary_budget=2000), memory, fake


def dialogue():
    first = HumanMessage(
        content="我的目标是维修耳机，如果不能退货，请保留政策引用 ORD1001，手机号后四位 8821"
    )
    call = AIMessage(content="", tool_calls=[{"name": "search_policy", "args": {}, "id": "p1"}])
    result = ToolMessage(
        content=json.dumps(
            {
                "ok": True,
                "references": [{"source": "policy.md", "title": "维修规则"}],
                "content": "说明" * 250,
            }
        ),
        name="search_policy",
        tool_call_id="p1",
    )
    hidden = AIMessage(content="模型内部推理不应保存")
    payment = HumanMessage(content="付款方式是银行卡，但不要把支付信息存进摘要")
    middle = HumanMessage(content="我希望使用文字客服")
    answer = AIMessage(content="收到")
    current = HumanMessage(content="现在继续办理")
    return [first, call, result, hidden, payment, AIMessage(content="收到"), middle,
            answer, current]


@pytest.mark.asyncio
async def test_threshold_and_structured_fact_retention(rig):
    compactor, memory, _ = rig
    messages = dialogue()
    summary, low = await compactor.maybe_compact(
        owner="a", thread="t", messages=messages, system=None, total_budget=10000
    )
    assert summary is None and low["triggered"] is False
    summary, high = await compactor.maybe_compact(
        owner="a", thread="t", messages=messages, system=None, total_budget=400
    )
    assert summary is not None and high["triggered"] is True
    assert "ORD1001" in summary["entities"]
    assert "8821" not in json.dumps(summary, ensure_ascii=False)
    assert "银行卡" not in json.dumps(summary, ensure_ascii=False)
    assert "policy.md#维修规则" in summary["citations"]
    assert "模型内部推理" not in json.dumps(summary, ensure_ascii=False)
    assert "现在继续办理" not in json.dumps(summary, ensure_ascii=False)
    assert (await memory.session("a", "t"))["compaction"]["summary"] == summary
    await memory.save_session("a", "t", {"summary": "另一轮的会话摘要"})
    assert (await memory.session("a", "t"))["compaction"]["summary"] == summary
    assert high["saved_tokens"] > 0


@pytest.mark.asyncio
async def test_incremental_idempotent_and_concurrent_compaction(rig):
    compactor, memory, _ = rig
    messages = dialogue()
    first, _ = await compactor.maybe_compact(
        owner="a", thread="t", messages=messages, system=None, total_budget=400
    )
    assert first is not None
    same, metrics = await compactor.maybe_compact(
        owner="a", thread="t", messages=messages, system=None, total_budget=400
    )
    assert same == first and metrics["triggered"] is False
    extended = [
        *messages,
        AIMessage(content="已答复"),
        HumanMessage(content="请保留文字客服偏好"),
        AIMessage(content="好"),
        HumanMessage(content="下一步是什么？"),
    ]
    results = await asyncio.gather(
        *[
            compactor.maybe_compact(
                owner="a", thread="t", messages=extended, system=None, total_budget=400
            )
            for _ in range(2)
        ]
    )
    assert sum(bool(item[1]["triggered"]) for item in results) == 1
    saved = (await memory.session("a", "t"))["compaction"]["summary"]
    assert any("文字客服" in item for item in saved["preferences"])
    assert len(saved["goals"]) == len(set(saved["goals"]))


@pytest.mark.asyncio
async def test_legacy_cursor_does_not_skip_identical_later_messages(rig):
    compactor, memory, fake = rig
    messages = dialogue()
    first, _ = await compactor.maybe_compact(
        owner="a", thread="legacy", messages=messages, system=None, total_budget=400
    )
    assert first is not None
    key = memory._key("a", "legacy") + ":compaction"
    old_record = json.loads(await fake.get(key))
    old_record["cursor"] = old_record["cursor"].split(":", 1)[1]
    await fake.set(key, json.dumps(old_record), ex=120)
    extended = [
        *messages, AIMessage(content="已答复"), HumanMessage(content="请保留文字客服偏好"),
        AIMessage(content="好"), HumanMessage(content="下一步是什么？"),
    ]
    summary, metrics = await compactor.maybe_compact(
        owner="a", thread="legacy", messages=extended, system=None, total_budget=400
    )
    assert metrics["triggered"] is True
    assert summary is not None
    assert any("文字客服" in item for item in summary["preferences"])


@pytest.mark.asyncio
async def test_restart_isolation_failure_and_model_view(rig, monkeypatch):
    compactor, memory, fake = rig
    messages = dialogue()
    summary, _ = await compactor.maybe_compact(
        owner="a", thread="t", messages=messages, system=None, total_budget=400
    )
    assert summary is not None
    restarted = LayeredMemory("redis://fake", memory.sqlite_path, ttl=120)
    assert (await restarted.session("a", "t"))["compaction"]["summary"] == summary
    assert await restarted.session("b", "t") == {}
    view, system = ContextManager(
        TokenBudget(total=1000, system=200, history=300, memory=500, rag=300, tools=200)
    ).assemble(
        messages=messages,
        system=SystemMessage(content="业务事实以工具为准"),
        state={},
        memory={"compaction": summary},
    )
    assert messages[-1] is view[-1]
    assert system is not None and "ORD1001" in system.content
    assert any(isinstance(m, ToolMessage) for m in view) is False  # Old tool result is not reused.
    assert count_tokens(view + [system]) <= 1000
    fake.fail = True
    with pytest.raises(MemoryUnavailable):
        await compactor.maybe_compact(
            owner="a", thread="t", messages=messages, system=None, total_budget=400
        )
    fake.fail = False
    recovered, metrics = await compactor.maybe_compact(
        owner="a", thread="t", messages=messages, system=None, total_budget=400
    )
    assert recovered == summary and metrics["triggered"] is False
