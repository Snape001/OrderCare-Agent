"""Small opt-in Redis session memory and SQLite customer memory.

Checkpoint remains the source of truth for graph messages and interrupts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite
from redis.asyncio import Redis

from customer_support.store import get_order_status
from memory.context_manager import query_terms

logger = logging.getLogger(__name__)


class MemoryUnavailable(RuntimeError):
    """Redis session memory failed; callers must not silently continue."""


_order = re.compile(r"\b(?:ORD\d+|OL\d{6})\b", re.I)
_last4 = re.compile(r"(?:手机号后四位|手机后四位|尾号)\s*[:：]?\s*(\d{4})")
_safe_value = re.compile(r"^[\w\u4e00-\u9fff\s，。,.、：；-]{1,160}$")
_profile_channels = {"text": "偏好文字客服", "phone": "偏好电话客服"}


def explicit_profile_channel(message: str) -> str | None:
    """Accept only explicit, durable communication preferences; never store raw text."""
    if not re.search(r"以后|今后|下次|长期", message):
        return None
    if re.search(r"(?:不要|不想|别|避免).{0,8}(?:电话|语音|文字|在线客服|打字)", message):
        return None
    if re.search(r"(?:请|希望|偏好|优先).{0,8}(?:文字|在线客服|打字)(?:沟通|联系|客服)?", message):
        return "text"
    if re.search(r"(?:请|希望|偏好|优先).{0,8}(?:电话|语音)(?:沟通|联系|客服)?", message):
        return "phone"
    return None


def verified_customer_id(message: str) -> str | None:
    """Resolve identity only after the existing order verification succeeds."""
    order = _order.search(message)
    last4 = _last4.search(message)
    if not order or not last4:
        return None
    order_id = order.group().upper()
    if not get_order_status(order_id, last4.group(1)).get("ok"):
        return None
    from customer_support.olist_store import is_olist_order_id

    if os.getenv("BUSINESS_DATABASE_TYPE", "sqlite").lower() == "mysql":
        from customer_support.mysql_store import _connect

        with _connect() as mysql_connection, mysql_connection.cursor() as cursor:
            if is_olist_order_id(order_id):
                cursor.execute(
                    "SELECT customer_id FROM olist_orders WHERE order_alias=%s", (order_id,)
                )
            else:
                cursor.execute("SELECT customer_id FROM orders WHERE id=%s", (order_id,))
            row = cursor.fetchone()
            return str(row["customer_id"]) if row else None
    if is_olist_order_id(order_id):
        from customer_support.olist_store import DEFAULT_OLIST_DB_PATH

        path = DEFAULT_OLIST_DB_PATH
        query = "SELECT customer_id FROM olist_orders WHERE order_alias=?"
    else:
        from customer_support.store import DEFAULT_DB_PATH

        path = DEFAULT_DB_PATH
        query = "SELECT customer_id FROM orders WHERE id=?"
    with sqlite3.connect(path) as sqlite_connection:
        row = sqlite_connection.execute(query, (order_id,)).fetchone()
    return str(row[0]) if row else None


class LayeredMemory:
    def __init__(self, redis_url: str, sqlite_path: str | Path, ttl: int = 86400) -> None:
        if ttl < 60:
            raise ValueError("MEMORY_TTL_SECONDS must be at least 60")
        self.redis = Redis.from_url(redis_url, decode_responses=True, socket_timeout=2)
        self.sqlite_path = Path(sqlite_path)
        self.ttl = ttl

    async def setup(self) -> None:
        try:
            await self.redis.ping()
        except Exception as exc:
            logger.exception("Redis memory initialization failed")
            raise MemoryUnavailable("Redis memory unavailable") from exc
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.sqlite_path) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS customer_memories (
                customer_id TEXT NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY(customer_id, kind, value))""")
            await db.execute("""CREATE TABLE IF NOT EXISTS customer_profiles (
                customer_id TEXT PRIMARY KEY,
                communication_channel TEXT NOT NULL CHECK(communication_channel IN ('text', 'phone')),
                updated_at TEXT NOT NULL)""")
            await db.commit()

    async def close(self) -> None:
        await self.redis.aclose()

    @staticmethod
    def _key(owner: str, thread: str) -> str:
        digest = hashlib.sha256(f"{owner}:{thread}".encode()).hexdigest()
        return f"ordercare:memory:{digest}"

    async def session(self, owner: str, thread: str) -> dict[str, Any]:
        try:
            raw = await self.redis.get(self._key(owner, thread))
            compacted = await self.redis.get(self._key(owner, thread) + ":compaction")
        except Exception as exc:
            logger.exception("Redis memory read failed")
            raise MemoryUnavailable("Redis memory unavailable") from exc
        result = json.loads(raw) if raw else {}
        if compacted:
            record = json.loads(compacted)
            # Redis Lua cjson encodes empty arrays as empty objects. Restore the
            # summary schema on read so a restart cannot change list fields.
            summary = record.get("summary", {})
            if isinstance(summary, dict):
                record["summary"] = {
                    key: [] if value == {} else value for key, value in summary.items()
                }
            result["compaction"] = record
        return result

    async def save_session(self, owner: str, thread: str, data: dict[str, Any]) -> None:
        allowed = {
            key: data[key]
            for key in ("customer_id", "current_order", "summary", "working")
            if key in data
        }
        try:
            await self.redis.set(
                self._key(owner, thread), json.dumps(allowed, ensure_ascii=False), ex=self.ttl
            )
        except Exception as exc:
            logger.exception("Redis memory write failed")
            raise MemoryUnavailable("Redis memory unavailable") from exc

    async def delete_session(self, owner: str, thread: str) -> None:
        try:
            await self.redis.delete(
                self._key(owner, thread), self._key(owner, thread) + ":compaction"
            )
        except Exception as exc:
            logger.exception("Redis memory delete failed")
            raise MemoryUnavailable("Redis memory unavailable") from exc

    async def save_compaction(
        self,
        owner: str,
        thread: str,
        expected_cursor: str,
        cursor: str,
        summary: dict[str, list[str]],
    ) -> bool:
        """Atomically replace only the separate compaction key."""
        script = """
        local raw = redis.call('GET', KEYS[1])
        local value = raw and cjson.decode(raw) or {}
        local old = value.cursor or ''
        if old ~= ARGV[1] then return 0 end
        value = {cursor = ARGV[2], summary = cjson.decode(ARGV[3])}
        redis.call('SET', KEYS[1], cjson.encode(value), 'EX', tonumber(ARGV[4]))
        return 1
        """
        try:
            return bool(
                await self.redis.eval(
                    script,
                    1,
                    self._key(owner, thread) + ":compaction",
                    expected_cursor,
                    cursor,
                    json.dumps(summary, ensure_ascii=False),
                    self.ttl,
                )
            )
        except Exception as exc:
            logger.exception("Redis compaction write failed")
            raise MemoryUnavailable("Redis memory unavailable") from exc

    async def update(self, customer_id: str, kind: str, old: str, new: str) -> None:
        await self.put(customer_id, kind, new)
        if old != new:
            await self.delete(customer_id, kind, old)

    async def put(self, customer_id: str, kind: str, value: str) -> None:
        if (
            kind not in {"preference", "support_summary"}
            or not _safe_value.fullmatch(value)
            or re.search(r"\d{4,}|(?i:手机号|支付|密钥|密码|token|api.key)", value)
        ):
            raise ValueError("Only short non-sensitive preference or support summaries are allowed")
        async with aiosqlite.connect(self.sqlite_path) as db:
            await db.execute(
                """INSERT INTO customer_memories VALUES (?, ?, ?, ?)
                ON CONFLICT(customer_id, kind, value) DO UPDATE SET updated_at=excluded.updated_at""",
                (customer_id, kind, value, datetime.now(UTC).isoformat()),
            )
            await db.commit()

    async def delete(self, customer_id: str, kind: str, value: str | None = None) -> None:
        async with aiosqlite.connect(self.sqlite_path) as db:
            if value is None:
                await db.execute(
                    "DELETE FROM customer_memories WHERE customer_id=? AND kind=?",
                    (customer_id, kind),
                )
            else:
                await db.execute(
                    "DELETE FROM customer_memories WHERE customer_id=? AND kind=? AND value=?",
                    (customer_id, kind, value),
                )
            await db.commit()

    async def upsert_profile(self, customer_id: str, communication_channel: str) -> None:
        """Create/update one structured profile field; repeating a value is idempotent."""
        if not customer_id or communication_channel not in _profile_channels:
            raise ValueError("Verified customer and supported communication channel required")
        async with aiosqlite.connect(self.sqlite_path) as db:
            await db.execute(
                """INSERT INTO customer_profiles VALUES (?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                communication_channel=excluded.communication_channel,
                updated_at=CASE WHEN communication_channel=excluded.communication_channel
                    THEN customer_profiles.updated_at ELSE excluded.updated_at END""",
                (customer_id, communication_channel, datetime.now(UTC).isoformat()),
            )
            await db.commit()

    async def get_profile(self, customer_id: str) -> dict[str, str] | None:
        if not customer_id:
            return None
        async with aiosqlite.connect(self.sqlite_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute(
                    "SELECT communication_channel, updated_at FROM customer_profiles WHERE customer_id=?",
                    (customer_id,),
                )
            ).fetchone()
        return dict(row) if row else None

    async def delete_profile(self, customer_id: str) -> None:
        async with aiosqlite.connect(self.sqlite_path) as db:
            await db.execute("DELETE FROM customer_profiles WHERE customer_id=?", (customer_id,))
            await db.commit()

    async def profile_note(self, customer_id: str) -> dict[str, str] | None:
        profile = await self.get_profile(customer_id)
        if profile is None:
            return None
        return {
            "kind": "preference",
            "value": _profile_channels[profile["communication_channel"]],
            "updated_at": profile["updated_at"],
        }

    async def select(self, customer_id: str, query: str, limit: int = 4) -> list[dict[str, str]]:
        async with aiosqlite.connect(self.sqlite_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (
                await db.execute(
                    "SELECT kind, value, updated_at FROM customer_memories WHERE customer_id=? ORDER BY updated_at DESC LIMIT 50",
                    (customer_id,),
                )
            ).fetchall()
        terms = query_terms(query)
        return [
            dict(row)
            for row in sorted(
                rows,
                key=lambda row: (
                    sum(term in row["value"].lower() for term in terms),
                    row["updated_at"],
                ),
                reverse=True,
            )[:limit]
        ]
