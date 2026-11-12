"""Policy document parsing and the public knowledge-base search entry point."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.settings import settings
from customer_support.trace import trace_event

POLICY_PATH = Path("data/policies/v3")
POLICY_SEARCH_CONFIG_VERSION = "policy-search-v1"


class _PolicyResultCache:
    def __init__(self) -> None:
        self.values: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.lock = threading.RLock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self.lock:
            item = self.values.get(key)
            if item is None:
                return None
            expires, value = item
            if expires <= time.monotonic():
                del self.values[key]
                return None
            self.values.move_to_end(key)
            return deepcopy(value)

    def put(self, key: str, value: dict[str, Any]) -> None:
        with self.lock:
            self.values[key] = (
                time.monotonic() + settings.POLICY_SEARCH_CACHE_TTL_SECONDS,
                deepcopy(value),
            )
            self.values.move_to_end(key)
            while len(self.values) > settings.POLICY_SEARCH_CACHE_MAX_ENTRIES:
                self.values.popitem(last=False)


class _PolicyCircuit:
    def __init__(self) -> None:
        self.failures = 0
        self.open_until = 0.0
        self.probe_running = False
        self.lock = threading.RLock()

    def enter(self) -> bool:
        with self.lock:
            now = time.monotonic()
            if self.open_until > now:
                return False
            if self.open_until:
                if self.probe_running:
                    return False
                self.probe_running = True
            return True

    def success(self) -> None:
        with self.lock:
            self.failures = 0
            self.open_until = 0.0
            self.probe_running = False

    def failure(self) -> None:
        with self.lock:
            self.probe_running = False
            self.failures += 1
            if self.failures >= settings.POLICY_SEARCH_CIRCUIT_FAILURE_THRESHOLD:
                self.open_until = time.monotonic() + settings.POLICY_SEARCH_CIRCUIT_RESET_SECONDS


_policy_cache = _PolicyResultCache()
_policy_circuit = _PolicyCircuit()
_executor = ThreadPoolExecutor(
    max_workers=settings.POLICY_SEARCH_WORKER_LIMIT, thread_name_prefix="policy-search"
)
_worker_slots = threading.BoundedSemaphore(settings.POLICY_SEARCH_WORKER_LIMIT)


def policy_files(path: Path) -> list[Path]:
    """Return one policy file or a stable, nonempty set of Markdown corpus files."""
    files = sorted(path.glob("*.md")) if path.is_dir() else [path]
    if not files or any(not item.is_file() for item in files):
        raise ValueError("Policy corpus requires at least one Markdown file")
    return files


@dataclass(frozen=True)
class PolicySection:
    """One ``##`` section parsed from the policy Markdown file."""

    title: str
    content: str
    source: str
    doc_type: str = "policy"
    section_type: str = "rule"
    is_retrievable: bool = True


def _section_metadata(path: Path, title: str) -> dict[str, Any]:
    non_retrievable = {"免责声明", "目录", "导航", "适用范围"}
    section_type = (
        "disclaimer" if title == "免责声明" else
        "navigation" if title in {"目录", "导航", "适用范围"} else
        "process" if title == "处理流程" else "rule"
    )
    return {
        "doc_type": path.stem if path.parent.name == "v3" else "policy",
        "section_type": section_type,
        "is_retrievable": title not in non_retrievable,
    }


def load_policy_sections(path: Path = POLICY_PATH) -> list[PolicySection]:
    """Parse a Markdown policy file into independently retrievable sections."""
    if path.is_dir():
        return [section for item in policy_files(path) for section in load_policy_sections(item)]
    content = path.read_text(encoding="utf-8")
    sections: list[PolicySection] = []
    title = ""
    lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            if title:
                sections.append(
                    PolicySection(
                        title=title,
                        content="\n".join(lines).strip(),
                        source=path.as_posix(),
                        **_section_metadata(path, title),
                    )
                )
            title = line.removeprefix("## ").strip()
            lines = []
        elif title:
            lines.append(line)
    if title:
        sections.append(
            PolicySection(
                title=title,
                content="\n".join(lines).strip(),
                source=path.as_posix(),
                **_section_metadata(path, title),
            )
        )
    return sections


def search_policy(query: str) -> dict[str, Any]:
    """Rewrite and retrieve policy evidence with shared process-local protection."""
    # Local import prevents loading Chroma/FastEmbed when only parsing documents.
    from customer_support.query_rewrite import rewrite_policy_query
    from customer_support.rag import get_policy_knowledge_base

    started = time.perf_counter()
    try:
        knowledge_base = get_policy_knowledge_base()
        corpus_fingerprint = _policy_corpus_fingerprint(knowledge_base.policy_path)
    except Exception as exc:
        return _policy_failure("POLICY_RETRIEVAL_UNAVAILABLE", exc, started)
    retrieval_config = {
        "version": POLICY_SEARCH_CONFIG_VERSION,
        "top_k": 3,
        "model": getattr(getattr(knowledge_base, "embedding", None), "model_name", None),
        "threshold": getattr(knowledge_base, "relevance_threshold", None),
        "lexical_weight": getattr(knowledge_base, "lexical_weight", None),
    }
    cache_key = hashlib.sha256(json.dumps(
        [query, corpus_fingerprint, retrieval_config], ensure_ascii=False,
        sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    cached = _policy_cache.get(cache_key)
    if cached is not None:
        trace_event("policy_retrieval", status="cache_hit", duration_ms=0)
        return cached
    if not _policy_circuit.enter():
        trace_event("policy_retrieval", status="degraded", reason="circuit_open", duration_ms=0)
        return _policy_error("POLICY_RETRIEVAL_CIRCUIT_OPEN")
    if not _worker_slots.acquire(blocking=False):
        _policy_circuit.failure()
        return _policy_failure("POLICY_RETRIEVAL_BUSY", None, started)
    try:
        # Rewrite failures are handled by rewrite_policy_query itself and fall back to raw query.
        try:
            effective_query = rewrite_policy_query(query)
        except Exception as exc:
            effective_query = query
            trace_event("policy_retrieval", status="degraded", reason="rewrite_fallback",
                        error_type=type(exc).__name__, duration_ms=0)
        future = _executor.submit(knowledge_base.search_reranked_hybrid, effective_query, top_k=3)
        future.add_done_callback(lambda _: _worker_slots.release())
        hits = future.result(timeout=settings.POLICY_SEARCH_TIMEOUT_SECONDS)
        result = format_policy_hits(
            hits, fallback_source=knowledge_base.policy_path.as_posix() if not hits else None
        )
        result["ok"] = True
        _policy_circuit.success()
        if hits:
            _policy_cache.put(cache_key, result)
        trace_event("policy_retrieval", status="completed", cache="stored" if hits else "empty",
                    duration_ms=round((time.perf_counter() - started) * 1000, 1))
        return result
    except FutureTimeout as exc:
        _policy_circuit.failure()
        return _policy_failure("POLICY_RETRIEVAL_TIMEOUT", exc, started)
    except Exception as exc:
        _policy_circuit.failure()
        return _policy_failure("POLICY_RETRIEVAL_UNAVAILABLE", exc, started)


def _policy_corpus_fingerprint(path: Path) -> str:
    files = sorted(path.glob("*.md")) if path.is_dir() else [path]
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.name.encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _policy_error(code: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error_code": code,
        "error": "政策检索暂时不可用，请稍后重试或联系人工客服。",
    }


def _policy_failure(code: str, exc: Exception | None, started: float) -> dict[str, Any]:
    trace_event("policy_retrieval", status="degraded", reason=code,
                error_type=type(exc).__name__ if exc else None,
                duration_ms=round((time.perf_counter() - started) * 1000, 1))
    return _policy_error(code)


def format_policy_hits(
    hits: list[dict[str, Any]], fallback_source: str | None = None
) -> dict[str, Any]:
    """Shared tool-result assembly for serving and generation replay."""
    if not hits:
        return {
            "title": "未检索到相关政策",
            "content": "当前知识库没有足够相关的内容，建议转人工客服处理。",
            "source": fallback_source or POLICY_PATH.as_posix(),
            "score": 0.0,
            "references": [],
        }
    best = hits[0]
    return {
        "title": best["title"],
        "content": best["content"],
        "source": best["source"],
        "score": best["score"],
        "references": hits,
    }
