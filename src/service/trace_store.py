"""Session-scoped, sanitized execution records for the Agent workbench."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.settings import settings


def _path() -> Path:
    return Path(settings.SQLITE_DB_PATH).with_name("agent_traces.db")


def _connect() -> sqlite3.Connection:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS agent_traces (
            trace_id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            events_json TEXT NOT NULL,
            question TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL DEFAULT ''
        )"""
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_traces)")}
    for column in ("question", "answer"):
        if column not in columns:
            connection.execute(f"ALTER TABLE agent_traces ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_traces_owner ON agent_traces(owner, created_at DESC)"
    )
    return connection


def save_trace(
    *, trace_id: str, owner: str, thread_id: str, agent_id: str,
    status: str, duration_ms: float, provider: str, model: str,
    events: list[dict[str, Any]],
    question: str = "", answer: str = "",
) -> None:
    with closing(_connect()) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO agent_traces
            (trace_id, owner, thread_id, agent_id, created_at, status,
            duration_ms, provider, model, events_json, question, answer)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trace_id, owner, thread_id, agent_id, datetime.now(UTC).isoformat(),
                status, round(duration_ms, 1), provider, model,
                json.dumps(events, ensure_ascii=False), question, answer,
            ),
        )
        connection.commit()


def list_traces(owner: str, *, thread_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    query = (
        "SELECT trace_id, thread_id, agent_id, created_at, status, duration_ms, provider, model, question "
        "FROM agent_traces WHERE owner = ?"
    )
    values: list[Any] = [owner]
    if thread_id is not None:
        query += " AND thread_id = ?"
        values.append(thread_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    values.append(limit)
    with closing(_connect()) as connection:
        return [dict(row) for row in connection.execute(query, values)]


def get_trace(owner: str, trace_id: str) -> dict[str, Any] | None:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM agent_traces WHERE owner = ? AND trace_id = ?",
            (owner, trace_id),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["events"] = json.loads(result.pop("events_json"))
    result.pop("owner")
    return result
