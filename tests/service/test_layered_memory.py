"""Layered memory never substitutes the graph checkpoint or order verification."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from memory.layers import (
    LayeredMemory,
    MemoryUnavailable,
    explicit_profile_channel,
    verified_customer_id,
)
from schema import UserInput
from service import service


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.ttl = None
        self.fail = False

    async def ping(self):
        if self.fail:
            raise ConnectionError("redis unavailable")
        return True

    async def get(self, key):
        if self.fail:
            raise ConnectionError("redis unavailable")
        return self.data.get(key)

    async def set(self, key, value, ex):
        if self.fail:
            raise ConnectionError("redis unavailable")
        self.data[key] = value
        self.ttl = ex

    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)

    async def aclose(self):
        pass


@pytest.fixture
def layered(tmp_path, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr("memory.layers.Redis.from_url", lambda *args, **kwargs: fake)
    return LayeredMemory("redis://unused", tmp_path / "memory.db", ttl=120), fake


@pytest.mark.asyncio
async def test_session_ttl_isolation_and_redis_failure(layered):
    memory, redis = layered
    await memory.setup()
    await memory.save_session("owner-a", "thread", {"summary": "物流", "secret": "excluded"})
    assert redis.ttl == 120
    assert await memory.session("owner-a", "thread") == {"summary": "物流"}
    assert await memory.session("owner-b", "thread") == {}
    await memory.delete_session("owner-a", "thread")
    assert await memory.session("owner-a", "thread") == {}
    redis.fail = True
    with pytest.raises(MemoryUnavailable, match="Redis memory unavailable"):
        await memory.session("owner-a", "thread")


@pytest.mark.asyncio
async def test_long_term_dedup_update_delete_and_customer_isolation(layered):
    memory, _ = layered
    await memory.setup()
    await memory.put("c1", "preference", "偏好文字客服")
    await memory.put("c1", "preference", "偏好文字客服")
    await memory.put("c2", "preference", "偏好电话客服")
    assert len(await memory.select("c1", "文字")) == 1
    assert (await memory.select("c2", "文字"))[0]["value"] == "偏好电话客服"
    await memory.update("c1", "preference", "偏好文字客服", "偏好邮件客服")
    assert (await memory.select("c1", "邮件"))[0]["value"] == "偏好邮件客服"
    with pytest.raises(ValueError):
        await memory.put("c1", "preference", "手机号13800138000")
    await memory.delete("c1", "preference", "偏好邮件客服")
    assert await memory.select("c1", "文字") == []


def test_customer_binding_requires_verified_order():
    assert verified_customer_id("查询 ORD1001，手机号后四位 8821") == "C001"
    assert verified_customer_id("查询 ORD1001，手机号后四位 9999") is None
    assert verified_customer_id("查询 ORD1001") is None


def test_profile_extraction_requires_explicit_durable_preference():
    assert explicit_profile_channel("以后请用文字客服沟通") == "text"
    assert explicit_profile_channel("下次希望电话联系") == "phone"
    assert explicit_profile_channel("这次请用文字沟通") is None
    assert explicit_profile_channel("以后不要电话联系") is None
    assert explicit_profile_channel("以后希望不要电话联系") is None


@pytest.mark.asyncio
async def test_structured_profile_crud_dedup_and_isolation(layered):
    memory, _ = layered
    await memory.setup()
    await memory.upsert_profile("C001", "text")
    first = await memory.get_profile("C001")
    await memory.upsert_profile("C001", "text")
    assert await memory.get_profile("C001") == first
    assert await memory.get_profile("C002") is None
    assert (await memory.profile_note("C001"))["value"] == "偏好文字客服"
    await memory.upsert_profile("C001", "phone")
    assert (await memory.get_profile("C001"))["communication_channel"] == "phone"
    with pytest.raises(ValueError):
        await memory.upsert_profile("C001", "手机号13800138000")
    await memory.delete_profile("C001")
    assert await memory.get_profile("C001") is None


@pytest.mark.asyncio
async def test_verified_profile_flows_to_context_and_updates_after_completion(layered, monkeypatch):
    memory, _ = layered
    await memory.setup()
    monkeypatch.setattr(service.app.state, "layered_memory", memory, raising=False)
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(
        values={"route": {"intents": [], "entities": {}}, "task_trace": []}, tasks=[]
    )))
    user = UserInput(message="查询 ORD1001，手机号后四位 8821。以后请用文字客服沟通",
                     thread_id="profile-one", user_id="owner")
    await service._handle_input(user, agent)
    await service._record_memory(agent, user, completed=True)
    assert (await memory.get_profile("C001"))["communication_channel"] == "text"
    other = UserInput(message="查询 ORD1002，手机号后四位 8821，维修耳机",
                      thread_id="profile-two", user_id="owner")
    context, _ = await service._handle_input(other, agent)
    assert any(note["value"] == "偏好文字客服" for note in
               context["config"]["metadata"]["memory_context"]["notes"])
    await memory.put("C001", "preference", "偏好文字客服")
    await memory.upsert_profile("C001", "phone")
    newer = other.model_copy(update={"thread_id": "profile-three"})
    context, _ = await service._handle_input(newer, agent)
    values = [note["value"] for note in
              context["config"]["metadata"]["memory_context"]["notes"]]
    assert "偏好电话客服" in values
    assert "偏好文字客服" not in values


@pytest.mark.asyncio
async def test_new_session_reads_long_term_and_resume_keeps_checkpoint(layered, monkeypatch):
    memory, _ = layered
    await memory.setup()
    await memory.put("C001", "preference", "偏好文字客服")
    monkeypatch.setattr(service.app.state, "layered_memory", memory, raising=False)
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={}, tasks=[])))
    user = UserInput(message="查询 ORD1001，手机号后四位 8821", thread_id="t", user_id="owner")
    kwargs, _ = await service._handle_input(user, agent)
    assert isinstance(kwargs["input"]["messages"][0], HumanMessage)
    assert "偏好文字客服" in kwargs["config"]["metadata"]["memory_context"]["notes"][0]["value"]
    assert (await memory.session("owner", "t"))["customer_id"] == "C001"

    kwargs, _ = await service._handle_input(
        UserInput(message="查询 ORD1002，手机号后四位 8821", thread_id="new", user_id="owner"),
        agent,
    )
    assert "偏好文字客服" in kwargs["config"]["metadata"]["memory_context"]["notes"][0]["value"]

    agent.aget_state.return_value = SimpleNamespace(
        values={"messages": [HumanMessage(content="之前")]}, tasks=[]
    )
    kwargs, _ = await service._handle_input(
        UserInput(message="继续查询", thread_id="t", user_id="owner"), agent
    )
    assert len(kwargs["input"]["messages"]) == 1
    assert isinstance(kwargs["input"]["messages"][0], HumanMessage)

    interrupt = SimpleNamespace(
        interrupts=[
            SimpleNamespace(
                value={"action_requests": [{"name": "create_support_ticket", "args": {}}]}
            )
        ]
    )
    agent.aget_state.return_value = SimpleNamespace(values={"messages": []}, tasks=[interrupt])
    kwargs, _ = await service._handle_input(
        UserInput(message="确认", thread_id="t", user_id="owner"), agent
    )
    assert "approve" in str(kwargs["input"])
    assert any(
        note["value"] == "偏好文字客服"
        for note in kwargs["config"]["metadata"]["memory_context"]["notes"]
    )
