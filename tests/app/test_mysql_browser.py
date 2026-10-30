from pathlib import Path
from unittest.mock import patch

import httpx
from streamlit.testing.v1 import AppTest


def test_database_browser_sends_admin_credential(monkeypatch):
    monkeypatch.setenv("DATABASE_ADMIN_SECRET", "browser-admin-test")
    requests = []

    def get(url, **kwargs):
        requests.append(kwargs)
        body = (
            {"tables": ["olist_orders"]}
            if url.endswith("/tables")
            else {
                "table": "olist_orders",
                "total": 1,
                "rows": [{"order_alias": "OL000001"}],
            }
        )
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    with patch("httpx.get", side_effect=get):
        app = AppTest.from_file(str(Path("src/mysql_browser.py").resolve())).run(timeout=20)
    assert not app.exception
    assert requests
    assert all(r["headers"] == {"Authorization": "Bearer browser-admin-test"} for r in requests)
