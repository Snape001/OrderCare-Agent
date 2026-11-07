"""Exercise verified Memory writes and later model context with persistent Chroma."""

import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from test_episodic_memory import KeywordEmbedding

import customer_support.store as store
from agents.customer_support_agent import build_customer_support_graph
from memory.context_manager import ContextManager
from memory.episodic import EpisodicMemory, EpisodicMemoryUnavailable
from memory.intent import requested_event
from memory.layers import LayeredMemory
from schema import StreamInput, UserInput
from service import service


class SessionRedis:
    def __init__(self):
        self.data = {}

    async def ping(self):
        return True

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex):
        self.data[key] = value

    async def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)

    async def aclose(self):
        pass


@pytest_asyncio.fixture
async def active_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", tmp_path / "orders.db")
    store.initialize_database()
    with sqlite3.connect(store.DEFAULT_DB_PATH) as db:
        db.execute("INSERT INTO customers VALUES ('C002', '其他用户', '1234')")
        db.execute(
            "INSERT INTO orders VALUES ('ORD9001', 'C002', '运输中', '耳机', NULL, '未签收')"
        )
    redis = SessionRedis()
    monkeypatch.setattr("memory.layers.Redis.from_url", lambda *args, **kwargs: redis)
    layered = LayeredMemory("redis://unused", tmp_path / "profiles.db", ttl=120)
    await layered.setup()
    episodes = EpisodicMemory(
        persist_directory=tmp_path / "chroma", embedding=KeywordEmbedding(),
        similarity_threshold=0.5,
    )
    monkeypatch.setattr(service.app.state, "layered_memory", layered, raising=False)
    monkeypatch.setattr(service.app.state, "episodic_memory", episodes, raising=False)
    yield layered, episodes, tmp_path / "chroma"
    await layered.close()


def _input(message, thread="first", owner="owner"):
    return UserInput(message=message, thread_id=thread, user_id=owner)


def _payloads(events):
    return [json.loads(event[6:]) for event in events if event.startswith("data: {")]


@pytest.mark.asyncio
async def test_explicit_event_persists_and_reaches_next_session_model_context(
    active_memory, monkeypatch
):
    layered, episodes, chroma_path = active_memory
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={}, tasks=[])))
    await service._handle_input(_input("查询 ORD1001，手机号后四位 8821"), agent)
    recorded, _ = await service._handle_input(
        _input("我的耳机左耳没有声音的问题，请帮我记录这次售后情况"), agent
    )
    assert recorded["config"]["metadata"]["memory_response"] == "已记录这次售后情况。"
    raw = episodes.store.get(where={"customer_id": "C001"})
    assert len(raw["ids"]) == 1
    assert "耳机左耳没有声音" in raw["documents"][0]
    other, _ = await service._handle_input(
        _input("查询 ORD9001，手机号后四位 1234", "other", "other-owner"), agent
    )
    assert not any(
        note.get("kind") == "episode"
        for note in other["config"]["metadata"]["memory_context"]["notes"]
    )
    stranger, _ = await service._handle_input(
        _input("你还记得我之前的耳机问题吗", "stranger", "stranger-owner"), agent
    )
    assert stranger["config"]["metadata"]["memory_context"]["notes"] == []
    await service._handle_input(
        _input("我的耳机左耳没有声音的问题，请帮我记录这次售后情况"), agent
    )
    assert len(episodes.store.get(where={"customer_id": "C001"})["ids"]) == 1

    restarted = EpisodicMemory(
        persist_directory=chroma_path, embedding=KeywordEmbedding(), similarity_threshold=0.5
    )
    monkeypatch.setattr(service.app.state, "episodic_memory", restarted)
    await service._handle_input(_input("查询 ORD1001，手机号后四位 8821", "second"), agent)
    question = _input("你还记得我之前遇到过什么耳机问题吗", "second")
    kwargs, _ = await service._handle_input(question, agent)
    notes = kwargs["config"]["metadata"]["memory_context"]["notes"]
    assert any("左耳没有声音" in note["value"] for note in notes)

    seen = []
    original = ContextManager.assemble

    def capture(self, **arguments):
        result = original(self, **arguments)
        seen.append(result[1].content if result[1] else "")
        return result

    monkeypatch.setattr(ContextManager, "assemble", capture)
    graph = build_customer_support_graph(
        FakeMessagesListChatModel(responses=[AIMessage(content="你之前提到耳机左耳没有声音。")]),
        enable_router=False, force_routing=False, tools=[],
    )
    result = await graph.ainvoke(**kwargs)
    assert seen and "左耳没有声音" in seen[0]
    assert result["messages"][-1].content == "你之前提到耳机左耳没有声音。"
    assert (await layered.session("owner", "second"))["customer_id"] == "C001"


@pytest.mark.asyncio
async def test_profile_isolation_and_unverified_access(active_memory):
    layered, episodes, _ = active_memory
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={}, tasks=[])))
    denied, _ = await service._handle_input(_input("记录耳机左耳无声问题", "guest"), agent)
    assert "身份验证" in denied["config"]["metadata"]["memory_response"]
    assert episodes.store.get()["ids"] == []
    await service._handle_input(_input("查询 ORD1001，手机号后四位 8821"), agent)
    preference, _ = await service._handle_input(_input("以后请用文字客服沟通"), agent)
    assert preference["config"]["metadata"]["memory_response"] == "已保存你的沟通偏好。"
    assert (await layered.get_profile("C001"))["communication_channel"] == "text"
    await service._handle_input(_input("查询 ORD1001，手机号后四位 8821", "second"), agent)
    reused, _ = await service._handle_input(_input("我希望怎样联系？", "second"), agent)
    assert any(
        note["value"] == "偏好文字客服"
        for note in reused["config"]["metadata"]["memory_context"]["notes"]
    )
    other, _ = await service._handle_input(
        _input("查询 ORD9001，手机号后四位 1234", "other", "other-owner"), agent
    )
    assert (await layered.session("other-owner", "other"))["customer_id"] == "C002"
    assert not any(
        note.get("value") == "偏好文字客服"
        for note in other["config"]["metadata"]["memory_context"]["notes"]
    )
    unverified, _ = await service._handle_input(_input("还记得耳机问题吗", "new"), agent)
    assert unverified["config"]["metadata"]["memory_context"]["notes"] == []


@pytest.mark.asyncio
async def test_failed_chroma_write_never_reports_saved(active_memory, monkeypatch):
    _, episodes, _ = active_memory
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={}, tasks=[])))
    await service._handle_input(_input("查询 ORD1001，手机号后四位 8821"), agent)

    def unavailable(*args, **kwargs):
        raise RuntimeError("Chroma is unavailable")

    monkeypatch.setattr(episodes.store, "add_texts", unavailable)
    with pytest.raises(EpisodicMemoryUnavailable, match="write failed"):
        await service._handle_input(_input("记录耳机左耳无声问题"), agent)
    monkeypatch.setattr(service, "available_agent", lambda agent_id: agent)
    events = [
        event async for event in service.message_generator(
            StreamInput(message="记录耳机左耳无声问题", thread_id="first", user_id="owner")
        )
    ]
    payloads = _payloads(events)
    assert any(payload["type"] == "error" for payload in payloads)
    assert not any("已记录" in str(payload.get("content", "")) for payload in payloads)


@pytest.mark.asyncio
async def test_stream_confirms_record_only_after_persistent_write(active_memory, monkeypatch):
    _, episodes, _ = active_memory
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={}, tasks=[])))
    await service._handle_input(_input("查询 ORD1001，手机号后四位 8821"), agent)
    monkeypatch.setattr(service, "available_agent", lambda agent_id: agent)
    events = [
        event async for event in service.message_generator(
            StreamInput(
                message="帮我记录这次售后情况：耳机左耳无声",
                thread_id="first", user_id="owner",
            )
        )
    ]
    assert any(
        payload["type"] == "message" and payload["content"]["content"] == "已记录这次售后情况。"
        for payload in _payloads(events)
    )
    assert len(episodes.store.get(where={"customer_id": "C001"})["ids"]) == 1


@pytest.mark.asyncio
async def test_record_read_back_failure_never_claims_success(active_memory, monkeypatch):
    _, episodes, _ = active_memory
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={}, tasks=[])))
    await service._handle_input(_input("查询 ORD1001，手机号后四位 8821"), agent)
    monkeypatch.setattr(episodes, "search", AsyncMock(return_value=[]))
    with pytest.raises(EpisodicMemoryUnavailable, match="read-back failed"):
        await service._handle_input(
            _input("我的耳机左耳没有声音的问题，请帮我记录这次售后情况"), agent
        )


def test_explicit_memory_intent_requires_user_stated_event():
    assert requested_event("七天无理由政策是什么？", []) == (False, None)
    assert requested_event("记住这件事", []) == (True, None)
    found, content = requested_event(
        "记住这件事", [HumanMessage(content="我之前买的耳机左耳无声")]
    )
    assert found and content and "耳机左耳无声" in content
    found, content = requested_event(
        "我的耳机左耳没有声音的问题，请帮我记录这次售后情况", []
    )
    assert found and content and "耳机左耳没有声音" in content
    assert requested_event("请创建售后工单", []) == (False, None)


def test_semantic_episode_is_not_dropped_by_lexical_filter():
    from memory.context_manager import TokenBudget

    messages, system = ContextManager(TokenBudget()).assemble(
        messages=[HumanMessage(content="过去发生什么了？")], system=None, state={},
        memory={"notes": [{
            "kind": "episode", "value": "用户报告的历史售后情况：耳机左耳无声",
            "score": 0.8, "updated_at": "2026-11-06",
        }]},
    )
    assert messages[-1].content == "过去发生什么了？"
    assert system is not None and "左耳无声" in system.content


@pytest.mark.skipif(os.getenv("ORDERCARE_REAL_BGE_TEST") != "1", reason="explicit local BGE run")
@pytest.mark.asyncio
async def test_real_bge_persistent_episode_smoke(tmp_path):
    from customer_support.rag import FastEmbedChineseEmbeddings

    embedding = FastEmbedChineseEmbeddings(cache_dir=Path("data/models"))
    folder = tmp_path / "real-bge-chroma"
    first = EpisodicMemory(persist_directory=folder, embedding=embedding)
    await first.upsert(
        customer_id="C001", event_type="support_event",
        summary="用户报告的历史售后情况：购买的耳机左耳无声",
        source_session="first",
    )
    reopened = EpisodicMemory(persist_directory=folder, embedding=embedding)
    hits = await reopened.search(customer_id="C001", query="以前耳机左耳没声音的问题")
    assert hits and "左耳无声" in hits[0]["value"]
    assert await reopened.search(customer_id="C002", query="耳机左耳没声音") == []
