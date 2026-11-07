"""Verified-customer episodic support memory in a separate Chroma collection."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from memory.layers import MemoryUnavailable

COLLECTION = "customer_support_episodes"
_sensitive = re.compile(
    r"(?i)(?:sk-[\w-]{8,}|bearer\s+[\w.-]+|<think>|\bcot\b|"
    r"手机号|手机后四位|银行卡|信用卡|卡号|支付账户|付款方式|密码|密钥|api.?key|"
    r"\b(?:ORD\d+|OL\d{6})\b|(?<![A-Za-z0-9])\d{4,}(?![A-Za-z0-9]))"
)
_product = re.compile(r"^[\u4e00-\u9fffA-Za-z\s]{1,30}$")
_valuable = {"refund_check", "repair_query", "ticket_create", "support_event"}
_actions = {"check_refund_eligibility", "search_policy", "create_support_ticket"}
_event_labels = {
    "refund_check": "退款资格核验", "repair_query": "维修政策咨询",
    "ticket_create": "售后工单创建",
}
_action_labels = {
    "check_refund_eligibility": "核验退款资格", "search_policy": "查询售后政策",
    "create_support_ticket": "创建售后工单",
}


class EpisodicMemoryUnavailable(MemoryUnavailable):
    """Chroma episodic memory operation failed."""


logger = logging.getLogger(__name__)


def completed_episode(values: dict[str, Any]) -> tuple[str, str] | None:
    """Extract only verified completed *steps*, not free-form model claims."""
    route = values.get("route") or {}
    intents = [str(value) for value in route.get("intents", [])]
    event_type = next((intent for intent in intents if intent in _valuable - {"support_event"}), None)
    trace = values.get("task_trace") or []
    if not event_type or not isinstance(trace, list):
        return None
    if any(
        isinstance(step, dict) and step.get("status") in {"pending", "blocked", "failed"}
        for step in trace
    ):
        return None
    done = sorted({
        str(step["action"]) for step in trace
        if isinstance(step, dict) and step.get("status") == "done"
        and step.get("action") in _actions
    })
    if not done or (event_type == "ticket_create" and "create_support_ticket" not in done):
        return None
    product = str((route.get("entities") or {}).get("product_name") or "")
    safe_product = product if _product.fullmatch(product) else ""
    summary = "售后事件：" + _event_labels[event_type] + "；已完成步骤：" + "、".join(
        _action_labels[action] for action in done
    )
    if safe_product:
        summary += "；商品：" + safe_product
    return event_type, summary


class EpisodicMemory:
    def __init__(
        self,
        *,
        persist_directory: Path,
        embedding: Embeddings,
        similarity_threshold: float = 0.55,
        recency_weight: float = 0.15,
    ) -> None:
        if not 0 <= similarity_threshold <= 1 or not 0 <= recency_weight <= 1:
            raise ValueError("Episodic similarity threshold and recency weight must be in [0, 1]")
        self.similarity_threshold = similarity_threshold
        self.recency_weight = recency_weight
        try:
            persist_directory.mkdir(parents=True, exist_ok=True)
            self.store = Chroma(
                collection_name=COLLECTION,
                embedding_function=embedding,
                persist_directory=str(persist_directory),
                collection_metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            raise EpisodicMemoryUnavailable("Episodic Chroma unavailable") from exc

    @staticmethod
    def _validate(customer_id: str, summary: str, source_session: str) -> None:
        if not customer_id or not source_session or not 1 <= len(summary) <= 240:
            raise ValueError("Verified customer, source session and short summary required")
        if _sensitive.search(summary):
            raise ValueError("Sensitive or reasoning content cannot be stored as an episode")

    async def upsert(
        self,
        *,
        customer_id: str,
        event_type: str,
        summary: str,
        source_session: str,
        memory_id: str | None = None,
        created_at: datetime | None = None,
    ) -> str:
        self._validate(customer_id, summary, source_session)
        if event_type not in _valuable:
            raise ValueError("Unsupported episodic event type")
        identifier = memory_id or hashlib.sha256(
            f"{customer_id}:{event_type}:{summary}".encode()
        ).hexdigest()[:24]
        try:
            existing = await asyncio.to_thread(self.store.get, ids=[identifier])
            metadata = (existing.get("metadatas") or [None])[0]
            if metadata and metadata.get("customer_id") != customer_id:
                raise PermissionError("Episode owner mismatch")
            timestamp = (
                str(metadata["created_at"]) if metadata and memory_id is None
                else (created_at or datetime.now(UTC)).isoformat()
            )
            await asyncio.to_thread(
                self.store.add_texts,
                [summary],
                metadatas=[{
                    "memory_id": identifier, "customer_id": customer_id,
                    "event_type": event_type, "created_at": timestamp,
                    "source_session": source_session,
                }],
                ids=[identifier],
            )
            logger.info("Episodic Memory persisted event_type=%s memory_id=%s", event_type, identifier)
            return identifier
        except PermissionError:
            raise
        except Exception as exc:
            logger.exception("Episodic Memory write failed")
            raise EpisodicMemoryUnavailable("Episodic Chroma write failed") from exc

    async def delete(self, *, customer_id: str, memory_id: str) -> None:
        try:
            existing = await asyncio.to_thread(self.store.get, ids=[memory_id])
            metadata = (existing.get("metadatas") or [None])[0]
            if metadata is None:
                return
            if metadata.get("customer_id") != customer_id:
                raise PermissionError("Episode owner mismatch")
            await asyncio.to_thread(self.store.delete, ids=[memory_id])
        except PermissionError:
            raise
        except Exception as exc:
            raise EpisodicMemoryUnavailable("Episodic Chroma delete failed") from exc

    async def search(
        self, *, customer_id: str, query: str, k: int = 4, now: datetime | None = None
    ) -> list[dict[str, Any]]:
        if not customer_id or not query.strip():
            return []
        if k < 1:
            raise ValueError("Top-K must be positive")
        try:
            hits = await asyncio.to_thread(
                self.store.similarity_search_with_score,
                query, k=max(k * 3, k), filter={"customer_id": customer_id},
            )
        except Exception as exc:
            logger.exception("Episodic Memory search failed")
            raise EpisodicMemoryUnavailable("Episodic Chroma search failed") from exc
        current = now or datetime.now(UTC)
        results: list[dict[str, Any]] = []
        for document, distance in hits:
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            if similarity < self.similarity_threshold:
                continue
            metadata = document.metadata
            if metadata.get("customer_id") != customer_id:
                continue
            try:
                created = datetime.fromisoformat(str(metadata["created_at"]))
                age_days = max(0.0, (current - created).total_seconds() / 86400)
            except (ValueError, TypeError, KeyError):
                age_days = 3650.0
            recency = math.exp(-age_days / 180)
            score = (1 - self.recency_weight) * similarity + self.recency_weight * recency
            results.append({
                "memory_id": str(metadata["memory_id"]),
                "customer_id": customer_id,
                "kind": "episode",
                "value": document.page_content,
                "event_type": str(metadata["event_type"]),
                "updated_at": str(metadata["created_at"]),
                "source_session": str(metadata["source_session"]),
                "similarity": round(similarity, 4),
                "score": round(score, 4),
            })
        selected = sorted(results, key=lambda item: item["score"], reverse=True)[:k]
        logger.info("Episodic Memory retrieved hits=%d", len(selected))
        return selected
