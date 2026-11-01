from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from core import settings
from customer_support.errors import CustomerSupportModelError
from service import app, service


@pytest.mark.parametrize("mode", ["llm", "qwen", "deepseek", "ollama"])
@pytest.mark.parametrize("path", ["/invoke", "/stream"])
def test_provider_error_is_explicit_and_sanitized(monkeypatch, mode, path):
    monkeypatch.setattr(settings, "AUTH_SECRET", None)
    monkeypatch.setattr(settings, "CUSTOMER_SUPPORT_MODE", mode)
    graph = AsyncMock()
    graph.aget_state.return_value.tasks = []
    graph.ainvoke.side_effect = CustomerSupportModelError()

    async def failed_stream(**kwargs):
        raise CustomerSupportModelError()
        yield  # pragma: no cover

    graph.astream = failed_stream
    monkeypatch.setattr(service, "get_agent", lambda _: graph)
    response = TestClient(app).post(
        path, json={"message": "hello"}, headers={"X-Session-Token": "a" * 64}
    )
    if path == "/invoke":
        assert response.status_code == 502
        assert "No fallback" in response.json()["detail"]
    else:
        assert '"type": "error"' in response.text
        assert "No fallback" in response.text
        assert '"type": "message"' not in response.text
