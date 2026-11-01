"""Read-only workbench data and explicit, isolated policy search debugging."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from agents import DEFAULT_AGENT, get_agent
from core import settings
from core.llm import get_model
from customer_support.mcp_client import discovered_tool_names
from customer_support.policy import POLICY_PATH, load_policy_sections, policy_files
from customer_support.rag import (
    DEFAULT_CHROMA_PATH,
    PolicyKnowledgeBase,
    get_policy_knowledge_base,
    load_policy_chunks,
)
from customer_support.trace import safe_plan, safe_route, safe_task_trace, safe_text
from evaluation.llm import parse_json
from evaluation.three_way import REWRITE_PROMPT, Rewrite, validate_rewrite
from schema.models import DeepseekModelName
from service.access import checkpoint_thread, session_identity
from service.trace_store import get_trace, list_traces

router = APIRouter(prefix="/workbench", tags=["workbench"])


class SearchDebugInput(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    top_k: int = Field(default=2, ge=1, le=10)
    rewrite: bool = False


def _manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {key: data.get(key) for key in ("fingerprint", "chunk_count", "model")}


def _sqlite_available() -> bool:
    path = Path(settings.SQLITE_DB_PATH)
    if not path.is_file():
        return False
    try:
        with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as db:
            return db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    except (OSError, sqlite3.Error):
        return False


@router.get("/status")
def system_status(_: Annotated[str, Depends(session_identity)]) -> dict[str, Any]:
    try:
        get_agent(DEFAULT_AGENT)
        graph_loaded = True
    except RuntimeError:
        graph_loaded = False
    index = _manifest(DEFAULT_CHROMA_PATH / "manifest.json")
    mcp_tools = discovered_tool_names() if graph_loaded else ()
    return {
        "provider": settings.CUSTOMER_SUPPORT_MODE,
        "model": (
            settings.DEEPSEEK_MODEL if settings.CUSTOMER_SUPPORT_MODE == "deepseek"
            else settings.OLLAMA_MODEL if settings.CUSTOMER_SUPPORT_MODE == "ollama"
            else settings.DASHSCOPE_MODEL if settings.CUSTOMER_SUPPORT_MODE == "qwen"
            else str(settings.DEFAULT_MODEL or "")
        ),
        "api": "ready",
        "checkpoint": {"backend": settings.DATABASE_TYPE, "available": _sqlite_available() if settings.DATABASE_TYPE == "sqlite" else graph_loaded},
        "chroma": {"indexed": index is not None, "manifest": index},
        "mcp": {"server": "ordercare-business-tools", "transport": "stdio",
                "tools_discovered": bool(mcp_tools), "tool_count": len(mcp_tools),
                "tools": list(mcp_tools),
                "status": "discovered_at_startup" if mcp_tools else "not_discovered"},
        "agent_graph": {"loaded": graph_loaded, "agent_id": DEFAULT_AGENT},
    }


@router.get("/policies")
def policies(_: Annotated[str, Depends(session_identity)]) -> dict[str, Any]:
    collections = [("online", POLICY_PATH), ("experiment-v2", Path("data/policies/v2"))]
    documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    for label, path in collections:
        if not path.exists():
            continue
        for file in policy_files(path):
            raw = file.read_text(encoding="utf-8")
            documents.append({
                "collection": label, "source": file.as_posix(), "preview": raw[:2500],
                "sections": len(load_policy_sections(file)),
                "updated_at": datetime.fromtimestamp(file.stat().st_mtime, UTC).isoformat(),
            })
        for chunk in load_policy_chunks(path):
            chunks.append({"collection": label, "source": chunk.metadata["source"], "title": chunk.metadata["title"], "chunk_id": chunk.metadata["chunk_id"], "chunk_index": chunk.metadata["chunk_index"], "content": chunk.page_content})
    return {
        "documents": documents,
        "chunks": chunks,
        "online_index": _manifest(DEFAULT_CHROMA_PATH / "manifest.json"),
        "experiment_index": _manifest(Path("data/evaluation/rag/three-way-comparison-v2/chroma-index/manifest.json")),
        "debug_collection": "online",
    }


@router.post("/search")
async def search_debug(
    request: SearchDebugInput, _: Annotated[str, Depends(session_identity)]
) -> dict[str, Any]:
    kb: PolicyKnowledgeBase = get_policy_knowledge_base()
    runs: list[dict[str, Any]] = []
    for method in ("dense", "hybrid"):
        started = perf_counter()
        hits = await asyncio.to_thread(kb.search, request.query, request.top_k, method)
        runs.append({"method": method, "query": safe_text(request.query, 300), "latency_ms": round((perf_counter() - started) * 1000, 1), "hits": hits})
    rewrite_info: dict[str, Any] | None = None
    if request.rewrite:
        if not settings.DEEPSEEK_API_KEY:
            raise HTTPException(status_code=409, detail="DeepSeek rewrite is not configured")
        model = get_model(DeepseekModelName.DEEPSEEK_CHAT)
        started = perf_counter()
        try:
            response = await model.ainvoke([
                SystemMessage(content=REWRITE_PROMPT), HumanMessage(content=request.query)
            ])
            proposed = Rewrite.model_validate(parse_json(response.content)).query
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Query rewrite failed") from exc
        issues = validate_rewrite(request.query, proposed)
        effective = request.query if issues else proposed
        rewrite_info = {"proposed": safe_text(proposed, 300), "effective": safe_text(effective, 300), "validation_issues": issues, "latency_ms": round((perf_counter() - started) * 1000, 1)}
        started = perf_counter()
        hits = await asyncio.to_thread(kb.search, effective, request.top_k, "hybrid")
        runs.append({"method": "rewrite_hybrid", "query": safe_text(effective, 300), "latency_ms": round((perf_counter() - started) * 1000, 1), "hits": hits})
    return {"collection": "online", "top_k": request.top_k, "runs": runs, "rewrite": rewrite_info}


@router.get("/traces")
def traces(
    identity: Annotated[str, Depends(session_identity)],
    thread_id: str | None = None,
    limit: int = Query(default=30, ge=1, le=50),
) -> dict[str, Any]:
    return {"traces": list_traces(identity, thread_id=thread_id, limit=limit)}


@router.get("/traces/{trace_id}")
def trace_detail(trace_id: str, identity: Annotated[str, Depends(session_identity)]) -> dict[str, Any]:
    record = get_trace(identity, trace_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return record


@router.get("/sessions/{thread_id}")
async def session_state(
    thread_id: str, identity: Annotated[str, Depends(session_identity)]
) -> dict[str, Any]:
    try:
        agent = get_agent(DEFAULT_AGENT)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Agent is unavailable") from exc
    state = await agent.aget_state(config=RunnableConfig(configurable={
        "thread_id": checkpoint_thread(identity, DEFAULT_AGENT, thread_id),
        "user_id": identity,
    }))
    values = state.values or {}
    route = values.get("route")
    return {
        "thread_id": thread_id,
        "message_count": len(values.get("messages", [])),
        "checkpoint_available": bool(values),
        "interrupted": any(getattr(task, "interrupts", None) for task in state.tasks),
        "route": safe_route(route) if isinstance(route, dict) else None,
        "plan": safe_plan(values.get("plan")),
        "task_trace": safe_task_trace(values.get("task_trace")),
    }
