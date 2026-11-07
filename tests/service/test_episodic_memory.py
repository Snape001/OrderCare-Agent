"""Isolated Chroma tests with deterministic embeddings; no model download."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage

from memory.context_manager import ContextManager, TokenBudget
from memory.episodic import EpisodicMemory, EpisodicMemoryUnavailable, completed_episode
from schema import UserInput
from service import service


class KeywordEmbedding(Embeddings):
    def _vector(self, text):
        if "退款" in text:
            return [1.0, 0.0, 0.0]
        if "维修" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture
def episodes(tmp_path):
    return EpisodicMemory(persist_directory=tmp_path / "chroma",
                          embedding=KeywordEmbedding(), similarity_threshold=0.5)


@pytest.mark.asyncio
async def test_chroma_upsert_dedup_update_delete_and_collection_isolation(episodes):
    first = await episodes.upsert(
        customer_id="C001", event_type="refund_check", summary="退款资格咨询已完成",
        source_session="thread-a",
    )
    same = await episodes.upsert(
        customer_id="C001", event_type="refund_check", summary="退款资格咨询已完成",
        source_session="thread-b",
    )
    assert same == first
    raw = episodes.store.get(ids=[first])
    assert len(raw["ids"]) == 1
    assert raw["metadatas"][0]["memory_id"] == first
    assert raw["metadatas"][0]["customer_id"] == "C001"
    assert raw["metadatas"][0]["event_type"] == "refund_check"
    assert raw["metadatas"][0]["source_session"] == "thread-b"
    assert raw["metadatas"][0]["created_at"]
    assert episodes.store._collection.name == "customer_support_episodes"

    updated = await episodes.upsert(
        customer_id="C001", event_type="refund_check", summary="退款流程咨询已完成",
        source_session="thread-b", memory_id=first,
    )
    assert updated == first
    assert episodes.store.get(ids=[first])["documents"] == ["退款流程咨询已完成"]
    with pytest.raises(PermissionError):
        await episodes.delete(customer_id="C002", memory_id=first)
    await episodes.delete(customer_id="C001", memory_id=first)
    assert episodes.store.get(ids=[first])["ids"] == []


@pytest.mark.asyncio
async def test_semantic_search_customer_filter_threshold_and_recency(episodes):
    now = datetime(2026, 11, 6, tzinfo=UTC)
    await episodes.upsert(customer_id="C001", event_type="repair_query",
                          summary="维修耳机旧咨询", source_session="old",
                          created_at=now - timedelta(days=300))
    await episodes.upsert(customer_id="C001", event_type="repair_query",
                          summary="维修耳机近期咨询", source_session="new",
                          created_at=now - timedelta(days=2))
    await episodes.upsert(customer_id="C002", event_type="repair_query",
                          summary="维修其他用户咨询", source_session="other",
                          created_at=now)
    await episodes.upsert(customer_id="C001", event_type="refund_check",
                          summary="退款资格咨询", source_session="refund", created_at=now)
    hits = await episodes.search(customer_id="C001", query="维修耳机", k=3, now=now)
    assert [hit["source_session"] for hit in hits] == ["new", "old"]
    assert all(hit["customer_id"] == "C001" for hit in hits)
    assert await episodes.search(customer_id="C002", query="维修耳机", k=3, now=now)
    assert await episodes.search(customer_id="", query="维修耳机") == []


@pytest.mark.asyncio
async def test_recalled_episode_enters_context_under_memory_budget(episodes):
    await episodes.upsert(customer_id="C001", event_type="repair_query",
                          summary="维修耳机售后咨询", source_session="old-thread")
    hits = await episodes.search(customer_id="C001", query="维修耳机")
    messages, system = ContextManager(TokenBudget(
        total=900, system=300, history=250, memory=160, rag=120, tools=120,
    )).assemble(messages=[HumanMessage(content="维修耳机下一步")],
               system=None, state={}, memory={"notes": hits})
    assert messages[-1].content == "维修耳机下一步"
    assert system is not None and "维修耳机售后咨询" in system.content


@pytest.mark.asyncio
async def test_sensitive_content_and_chroma_failure_are_explicit(episodes, monkeypatch):
    for content in ("手机号后四位 8821", "银行卡退款", "<think>内部推理</think>", "sk-1234567890"):
        with pytest.raises(ValueError):
            await episodes.upsert(customer_id="C001", event_type="repair_query",
                                  summary=content, source_session="thread")

    def broken(*args, **kwargs):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(episodes.store, "similarity_search_with_score", broken)
    with pytest.raises(EpisodicMemoryUnavailable, match="search failed"):
        await episodes.search(customer_id="C001", query="维修")
    monkeypatch.setattr(episodes.store, "add_texts", broken)
    with pytest.raises(EpisodicMemoryUnavailable, match="write failed"):
        await episodes.upsert(customer_id="C001", event_type="repair_query",
                              summary="维修耳机咨询", source_session="thread")


def test_episode_extraction_requires_completed_verified_step():
    route = {"intents": ["repair_query"], "entities": {"product_name": "耳机"}}
    done = {"route": route, "task_trace": [
        {"action": "search_policy", "status": "done"}
    ]}
    assert completed_episode(done) == (
        "repair_query", "售后事件：维修政策咨询；已完成步骤：查询售后政策；商品：耳机"
    )
    assert completed_episode({"route": route, "task_trace": [
        {"action": "search_policy", "status": "pending"}
    ]}) is None
    assert completed_episode({"route": {"intents": ["ticket_create"]},
                              "task_trace": [{"action": "search_policy", "status": "done"}]}) is None


@pytest.mark.asyncio
async def test_service_retrieval_requires_verified_customer_and_new_session(episodes, monkeypatch):
    sessions = {}

    async def session(owner, thread):
        return dict(sessions.get((owner, thread), {}))

    async def save_session(owner, thread, value):
        sessions[(owner, thread)] = dict(value)

    memory = SimpleNamespace(session=session, save_session=save_session,
                             select=AsyncMock(return_value=[]), put=AsyncMock())
    monkeypatch.setattr(service.app.state, "layered_memory", memory, raising=False)
    monkeypatch.setattr(service.app.state, "episodic_memory", episodes, raising=False)
    await episodes.upsert(customer_id="C001", event_type="repair_query",
                          summary="维修耳机售后咨询", source_session="old-thread")
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(values={}, tasks=[])))
    kwargs, _ = await service._handle_input(
        UserInput(message="维修耳机，查询 ORD1001，手机号后四位 8821",
                  thread_id="new-thread", user_id="owner"), agent
    )
    notes = kwargs["config"]["metadata"]["memory_context"]["notes"]
    assert any(note["kind"] == "episode" for note in notes)
    assert notes[0]["customer_id"] == "C001"

    other, _ = await service._handle_input(
        UserInput(message="维修耳机", thread_id="unverified", user_id="other"), agent
    )
    assert other["config"]["metadata"]["memory_context"]["notes"] == []

    agent.aget_state = AsyncMock(return_value=SimpleNamespace(
        values={"messages": [object()]}, tasks=[]
    ))
    again, _ = await service._handle_input(
        UserInput(message="继续维修", thread_id="new-thread", user_id="owner"), agent
    )
    assert again["config"]["metadata"]["memory_context"]["notes"] == []


@pytest.mark.asyncio
async def test_service_writes_only_after_complete_and_not_approval(episodes, monkeypatch):
    session_data = {"customer_id": "C001"}
    memory = SimpleNamespace(
        session=AsyncMock(return_value=session_data),
        save_session=AsyncMock(), put=AsyncMock(),
    )
    monkeypatch.setattr(service.app.state, "layered_memory", memory, raising=False)
    monkeypatch.setattr(service.app.state, "episodic_memory", episodes, raising=False)
    values = {"route": {"intents": ["repair_query"], "entities": {}},
              "task_trace": [{"action": "search_policy", "status": "done"}]}
    agent = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(
        values=values, tasks=[]
    )))
    user = UserInput(message="维修咨询", thread_id="t1", user_id="owner")
    await service._record_memory(agent, user, completed=False)
    assert await episodes.search(customer_id="C001", query="维修") == []
    memory.put.assert_not_awaited()
    agent.aget_state.return_value = SimpleNamespace(values=values, tasks=[
        SimpleNamespace(interrupts=[object()])
    ])
    await service._record_memory(agent, user, completed=True)
    assert await episodes.search(customer_id="C001", query="维修") == []
    memory.put.assert_not_awaited()
    agent.aget_state.return_value = SimpleNamespace(values={
        **values, "task_trace": [{"action": "search_policy", "status": "pending"}]
    }, tasks=[])
    await service._record_memory(agent, user, completed=True)
    assert await episodes.search(customer_id="C001", query="维修") == []
    memory.put.assert_not_awaited()
    agent.aget_state.return_value = SimpleNamespace(values=values, tasks=[])
    await service._record_memory(agent, user, completed=True)
    assert len(await episodes.search(customer_id="C001", query="维修")) == 1
    memory.put.assert_awaited_once()
