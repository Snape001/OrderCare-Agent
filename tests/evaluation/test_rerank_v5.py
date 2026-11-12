"""The offline reranker must preserve candidate and scoring invariants."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain_core.documents import Document

sys.path.insert(0, str(Path("scripts").resolve()))
from evaluate_rerank_rag_v5 import rerank_search  # noqa: E402

from evaluation import rerank  # noqa: E402


def chunk(identifier: str, title: str) -> Document:
    return Document(
        page_content=f"{title}的规则",
        metadata={"chunk_id": identifier, "title": title, "source": f"{identifier}.md"},
    )


class FakeKnowledgeBase:
    relevance_threshold = 0.5

    def __init__(self) -> None:
        self.dense = [(chunk("a", "甲"), 0.9), (chunk("b", "乙"), 0.6),
                      (chunk("c", "丙"), 0.2)]
        self.lexical = [(chunk("b", "乙"), 3.0), (chunk("d", "丁"), 1.0),
                        (chunk("e", "戊"), 0.2)]

    def ensure_index(self) -> None:
        pass

    def _dense_ranking(self, query: str, limit: int) -> list[tuple[Document, float]]:
        assert (query, limit) == ("原问题", 3)
        return self.dense

    def _lexical_ranking(self, query: str, limit: int) -> list[tuple[Document, float]]:
        assert (query, limit) == ("原问题", 3)
        return self.lexical


class FakeReranker:
    def score(self, query: str, passages: list[str]) -> list[float]:
        assert query == "原问题"
        assert all("\n" in passage for passage in passages)
        return [float({"甲": 1, "乙": 4, "丁": 3, "戊": 2}[p[0]]) for p in passages]


def test_top3_routes_deduplicate_threshold_and_rerank() -> None:
    hits, details = rerank_search(FakeKnowledgeBase(), FakeReranker(), "原问题")  # type: ignore[arg-type]
    assert [row["chunk_id"] for row in hits] == ["b", "d", "e"]
    assert len(details["dense_candidates"]) == len(details["lexical_candidates"]) == 3
    assert [row["chunk_id"] for row in details["reranked_candidates"]] == ["b", "d", "e", "a"]
    assert details["reranked_candidates"][0]["dense_rank"] == 2
    assert details["reranked_candidates"][0]["lexical_rank"] == 1
    assert all(row["chunk_id"] != "c" for row in details["reranked_candidates"])


def test_rerank_is_not_rrf() -> None:
    class Scores:
        def score(self, query: str, passages: list[str]) -> list[float]:
            return [float({"甲": 10, "乙": 1, "丁": 9, "戊": 8}[p[0]]) for p in passages]

    hits, _ = rerank_search(FakeKnowledgeBase(), Scores(), "原问题")  # type: ignore[arg-type]
    assert [row["chunk_id"] for row in hits] == ["a", "d", "e"]


def test_reranker_uses_cached_files_and_reuses_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def fake_download(**kwargs: object) -> str:
        calls.append(bool(kwargs["local_files_only"]))
        return str(Path("cached") / str(kwargs["filename"]))

    class FakeTokenizer:
        def enable_truncation(self, **_: object) -> None:
            pass

        def enable_padding(self, **_: object) -> None:
            pass

    session = object()
    monkeypatch.setattr(rerank, "hf_hub_download", fake_download)
    monkeypatch.setattr(rerank.Tokenizer, "from_file", lambda _: FakeTokenizer())
    monkeypatch.setattr(rerank.ort, "InferenceSession", lambda *_, **__: session)
    monkeypatch.setattr(rerank, "file_sha256", lambda _: "sha")
    instance = rerank.BGEReranker(cache_dir=Path("cached"))
    assert instance.session is session
    assert calls == [True] * len(rerank.MODEL_FILES)
    rerank.get_reranker.cache_clear()
    monkeypatch.setattr(rerank, "BGEReranker", lambda: instance)
    assert rerank.get_reranker() is rerank.get_reranker() is instance
    rerank.get_reranker.cache_clear()
