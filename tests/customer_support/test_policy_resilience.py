from __future__ import annotations

import time
from pathlib import Path

import pytest

import customer_support.policy as policy
from core.settings import settings


class FakeKnowledgeBase:
    def __init__(self, path: Path, search):
        self.policy_path = path
        self.embedding = type("Embedding", (), {"model_name": "fake-v1"})()
        self.relevance_threshold = 0.5
        self.lexical_weight = 1.0
        self.search_reranked_hybrid = search


@pytest.fixture
def isolated_policy(monkeypatch: pytest.MonkeyPatch):
    source = Path("data/policies/v3")
    monkeypatch.setattr(policy, "_policy_cache", policy._PolicyResultCache())
    monkeypatch.setattr(policy, "_policy_circuit", policy._PolicyCircuit())
    monkeypatch.setattr(settings, "POLICY_SEARCH_CACHE_TTL_SECONDS", 600)
    monkeypatch.setattr(settings, "POLICY_SEARCH_CACHE_MAX_ENTRIES", 8)
    monkeypatch.setattr(settings, "POLICY_SEARCH_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(settings, "POLICY_SEARCH_CIRCUIT_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(settings, "POLICY_SEARCH_CIRCUIT_RESET_SECONDS", 0.03)
    monkeypatch.setattr(policy, "_worker_slots", __import__("threading").BoundedSemaphore(2))
    monkeypatch.setattr("customer_support.query_rewrite.rewrite_policy_query", lambda query: query)
    return source


def test_success_cache_copies_results_and_invalidates_on_corpus_change(isolated_policy, monkeypatch):
    calls = 0
    corpus = "v1"
    monkeypatch.setattr(policy, "_policy_corpus_fingerprint", lambda _: corpus)

    def search(query, top_k):
        nonlocal calls
        calls += 1
        return [{"title": "规则", "content": "内容", "source": "p.md", "score": 0.8}]

    kb = FakeKnowledgeBase(isolated_policy, search)
    monkeypatch.setattr("customer_support.rag.get_policy_knowledge_base", lambda: kb)
    first = policy.search_policy("退货")
    first["references"].clear()
    second = policy.search_policy("退货")
    assert second["references"]
    assert calls == 1
    corpus = "v2"
    policy.search_policy("退货")
    assert calls == 2


def test_empty_results_are_successful_but_not_cached(isolated_policy, monkeypatch):
    calls = 0

    def search(query, top_k):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr("customer_support.rag.get_policy_knowledge_base", lambda: FakeKnowledgeBase(isolated_policy, search))
    assert policy.search_policy("不存在")["ok"] is True
    policy.search_policy("不存在")
    assert calls == 2
    assert policy._policy_circuit.failures == 0


def test_retrieval_failures_open_circuit_then_single_probe_recovers(isolated_policy, monkeypatch):
    calls = 0
    broken = True

    def search(query, top_k):
        nonlocal calls
        calls += 1
        if broken:
            raise RuntimeError("private detail")
        return [{"title": "规则", "content": "内容", "source": "p.md", "score": 0.8}]

    monkeypatch.setattr("customer_support.rag.get_policy_knowledge_base", lambda: FakeKnowledgeBase(isolated_policy, search))
    for _ in range(2):
        result = policy.search_policy("故障查询")
        assert result["ok"] is False
        assert result["error_code"] == "POLICY_RETRIEVAL_UNAVAILABLE"
        assert "private detail" not in result["error"]
    assert policy.search_policy("故障查询")["error_code"] == "POLICY_RETRIEVAL_CIRCUIT_OPEN"
    assert calls == 2
    time.sleep(0.04)
    broken = False
    assert policy.search_policy("故障查询")["ok"] is True
    assert calls == 3


def test_retrieval_timeout_is_not_reported_as_empty(isolated_policy, monkeypatch):
    monkeypatch.setattr(settings, "POLICY_SEARCH_TIMEOUT_SECONDS", 0.01)

    def search(query, top_k):
        time.sleep(0.05)
        return []

    monkeypatch.setattr("customer_support.rag.get_policy_knowledge_base", lambda: FakeKnowledgeBase(isolated_policy, search))
    result = policy.search_policy("慢查询")
    assert result["ok"] is False
    assert result["error_code"] == "POLICY_RETRIEVAL_TIMEOUT"
    assert "references" not in result
