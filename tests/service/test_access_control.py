from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from pydantic import SecretStr

from agents.customer_support_mock import builder
from core import settings
from customer_support import store
from service import app, service
from service.access import checkpoint_thread, session_identity


@pytest.fixture
def secured_client(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "AUTH_SECRET", None)
    monkeypatch.setattr(settings, "DATABASE_ADMIN_SECRET", SecretStr("admin-test-only"))
    monkeypatch.setattr(store, "DEFAULT_DB_PATH", tmp_path / "business.db")
    monkeypatch.setenv("BUSINESS_DATABASE_TYPE", "sqlite")
    graph = builder.compile(checkpointer=MemorySaver())
    monkeypatch.setattr(service, "get_agent", lambda agent_id: graph)
    return TestClient(app)


@pytest.mark.parametrize("path", ["/invoke", "/stream", "/history"])
def test_session_credential_required(secured_client, path):
    payload = {"message": "hello", "thread_id": "public-thread"}
    assert secured_client.post(path, json=payload).status_code == 401
    assert (
        secured_client.post(path, json=payload, headers={"X-Session-Token": "short"}).status_code
        == 401
    )


@pytest.mark.parametrize("path", ["/database/tables", "/database/tables/orders"])
def test_database_requires_separate_admin(secured_client, monkeypatch, path):
    import customer_support.mysql_store as mysql

    monkeypatch.setattr(settings, "AUTH_SECRET", SecretStr("ordinary-client"))
    monkeypatch.setattr(mysql, "list_database_tables", lambda: ["orders"])
    monkeypatch.setattr(mysql, "browse_database_table", lambda *args: {"rows": []})
    assert secured_client.get(path).status_code == 401
    assert (
        secured_client.get(path, headers={"Authorization": "Bearer ordinary-client"}).status_code
        == 403
    )
    assert (
        secured_client.get(path, headers={"Authorization": "Bearer admin-test-only"}).status_code
        == 200
    )
    monkeypatch.setattr(settings, "DATABASE_ADMIN_SECRET", None)
    assert (
        secured_client.get(path, headers={"Authorization": "Bearer admin-test-only"}).status_code
        == 503
    )


def test_history_and_confirmation_are_scoped_to_secret(secured_client):
    owner = {"X-Session-Token": "a" * 64}
    stranger = {"X-Session-Token": "b" * 64}
    payload = {"thread_id": "known-thread", "user_id": "spoofable-user"}
    first = secured_client.post(
        "/invoke",
        headers=owner,
        json={
            **payload,
            "message": "为 ORD1001 创建人工客服工单，手机号后四位 8821",
        },
    )
    assert first.status_code == 200
    assert "确认" in first.json()["content"]
    assert secured_client.post("/history", headers=stranger, json=payload).json()["messages"] == []
    other = secured_client.post("/invoke", headers=stranger, json={**payload, "message": "确认"})
    assert other.status_code == 200
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM support_tickets").fetchone()[0] == 0
    own = secured_client.post("/invoke", headers=owner, json={**payload, "message": "确认"})
    assert own.status_code == 200
    assert "工单已创建" in own.json()["content"]
    assert len(secured_client.post("/history", headers=owner, json=payload).json()["messages"]) >= 4


def test_identity_and_agent_namespaces_are_distinct():
    identity = session_identity("a" * 64)
    assert identity == session_identity("a" * 64)
    assert checkpoint_thread(identity, "one", "public") != checkpoint_thread(
        identity, "two", "public"
    )
    assert checkpoint_thread(identity, "one", "public") != checkpoint_thread(
        session_identity("b" * 64), "one", "public"
    )


@pytest.mark.parametrize("path", ["/invoke", "/stream"])
@pytest.mark.parametrize(
    "key", ["checkpoint_id", "checkpoint_ns", "checkpoint_map", "__pregel_checkpointer"]
)
def test_cannot_override_checkpoint_scope(secured_client, path, key):
    response = secured_client.post(
        path,
        headers={"X-Session-Token": "a" * 64},
        json={
            "message": "hello",
            "agent_config": {key: "victim"},
        },
    )
    assert response.status_code == 422


def test_stream_uses_same_owner_namespace_as_invoke(secured_client, monkeypatch):
    graph = AsyncMock()
    graph.aget_state.return_value.tasks = []

    async def events(**kwargs):
        assert kwargs["config"]["configurable"]["thread_id"] == checkpoint_thread(
            session_identity("a" * 64), "customer-support", "public"
        )
        assert kwargs["config"]["configurable"]["user_id"] == session_identity("a" * 64)
        if False:
            yield

    graph.astream = events
    monkeypatch.setattr(service, "get_agent", lambda _: graph)
    response = secured_client.post(
        "/stream",
        headers={"X-Session-Token": "a" * 64},
        json={
            "message": "hello",
            "thread_id": "public",
            "user_id": "victim",
        },
    )
    assert response.status_code == 200
    assert "[DONE]" in response.text
    assert "error" not in response.text
