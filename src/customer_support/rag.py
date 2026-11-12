"""Local Chinese RAG pipeline: chunk, embed, persist, retrieve, and fuse."""

from __future__ import annotations

import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import jieba  # type: ignore[import-untyped]
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from rank_bm25 import BM25L  # type: ignore[import-untyped]

from customer_support.policy import POLICY_PATH, PolicySection, load_policy_sections, policy_files

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_CHROMA_PATH = Path("data/chroma")
DEFAULT_SERVING_POLICY_PATH = Path("data/policies/v3")
COLLECTION_NAME = "customer_service_policy"
RETRIEVAL_CANDIDATES = 3
MAX_RESULTS = 3
LEXICAL_INDEX_VERSION = "jieba-bm25l-v1"


class FastEmbedChineseEmbeddings(Embeddings):
    """Small ONNX-based Chinese embeddings with lazy model loading."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Path = Path("data/models"),
        threads: int = 2,
    ) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.threads = threads
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(
                model_name=self.model_name,
                cache_dir=str(self.cache_dir),
                threads=self.threads,
                lazy_load=True,
            )
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed knowledge-base chunks as passages."""
        vectors = self._load_model().passage_embed(texts, batch_size=32)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Embed one user question using the model's query mode."""
        vector = next(iter(self._load_model().query_embed([text])))
        return vector.tolist()


def split_section(
    section: PolicySection,
    chunk_size: int = 220,
    overlap: int = 40,
) -> list[Document]:
    """Split one section into overlapping character windows with metadata."""
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")

    text = section.content.strip()
    documents: list[Document] = []
    start = 0
    chunk_index = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            sentence_end = max(
                text.rfind(mark, start + chunk_size // 2, end)
                for mark in ("。", "！", "？", "；", "\n")
            )
            if sentence_end > start:
                end = sentence_end + 1

        chunk_text = text[start:end].strip()
        chunk_id = hashlib.sha1(
            f"{section.source}:{section.title}:{chunk_index}:{chunk_text}".encode()
        ).hexdigest()[:16]
        documents.append(
            Document(
                page_content=chunk_text,
                metadata={
                    "chunk_id": chunk_id,
                    "title": section.title,
                    "source": section.source,
                    "chunk_index": chunk_index,
                    "doc_type": section.doc_type,
                    "section_type": section.section_type,
                    "is_retrievable": section.is_retrievable,
                },
            )
        )
        if end == len(text):
            break
        start = end - overlap
        chunk_index += 1
    return documents


def load_policy_chunks(path: Path = POLICY_PATH) -> list[Document]:
    """Load every policy section and apply the chunking strategy."""
    return [
        document for section in load_policy_sections(path) for document in split_section(section)
    ]


def _lexical_tokens(text: str) -> list[str]:
    """Segment Chinese text while preserving ASCII words, numbers and identifiers."""
    tokens = [
        token.lower()
        for segment in jieba.lcut(text)
        for token in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)*", segment)
    ]
    tokens.extend(
        identifier.lower()
        for identifier in re.findall(r"[a-zA-Z0-9]+(?:[-_][a-zA-Z0-9]+)+", text)
    )
    return tokens


class PolicyKnowledgeBase:
    """Persistent Chroma index plus lexical/dense rank fusion."""

    def __init__(
        self,
        policy_path: Path = POLICY_PATH,
        persist_directory: Path = DEFAULT_CHROMA_PATH,
        embedding: Embeddings | None = None,
        relevance_threshold: float = 0.50,
        lexical_weight: float = 1.0,
    ) -> None:
        if not 0 <= relevance_threshold <= 1:
            raise ValueError("relevance_threshold must be in [0, 1]")
        if not 0 <= lexical_weight <= 1:
            raise ValueError("lexical_weight must be in [0, 1]")
        self.lexical_weight = lexical_weight
        self.policy_path = policy_path
        self.persist_directory = persist_directory
        self.embedding = embedding or FastEmbedChineseEmbeddings()
        self.relevance_threshold = relevance_threshold
        self._store: Chroma | None = None
        self._chunks: list[Document] | None = None
        self._bm25: BM25L | None = None
        self._lexical_fingerprint: str | None = None

    @property
    def manifest_path(self) -> Path:
        return self.persist_directory / "manifest.json"

    def _source_fingerprint(self, chunks: list[Document]) -> str:
        payload = {
            "policy": (
                self.policy_path.read_text(encoding="utf-8")
                if self.policy_path.is_file()
                else [(p.as_posix(), p.read_text(encoding="utf-8")) for p in policy_files(self.policy_path)]
            ),
            "chunks": [document.metadata["chunk_id"] for document in chunks],
            "embedding": type(self.embedding).__name__,
            "model": getattr(self.embedding, "model_name", "injected"),
            "lexical_index": LEXICAL_INDEX_VERSION,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _new_store(self) -> Chroma:
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        return Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=self.embedding,
            persist_directory=str(self.persist_directory),
            collection_metadata={"hnsw:space": "cosine"},
        )

    def ensure_index(self, force_rebuild: bool = False) -> int:
        """Build the vector index only when the source/configuration changed."""
        chunks = [
            chunk for chunk in load_policy_chunks(self.policy_path)
            if chunk.metadata["is_retrievable"]
        ]
        fingerprint = self._source_fingerprint(chunks)
        manifest: dict[str, Any] = {}
        if self.manifest_path.exists():
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))

        self._store = self._store or self._new_store()
        indexed_count = len(self._store.get(include=[])["ids"])
        is_current = manifest.get("fingerprint") == fingerprint and indexed_count == len(chunks)
        if force_rebuild or not is_current:
            self._store.delete_collection()
            self._store = self._new_store()
            self._store.add_documents(
                chunks,
                ids=[str(document.metadata["chunk_id"]) for document in chunks],
            )
            self.manifest_path.write_text(
                json.dumps(
                    {
                        "fingerprint": fingerprint,
                        "chunk_count": len(chunks),
                        "model": getattr(self.embedding, "model_name", "injected"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        self._chunks = chunks
        if self._bm25 is None or self._lexical_fingerprint != fingerprint:
            corpus = [
                _lexical_tokens(f"{document.metadata.get('title', '')} {document.page_content}")
                for document in chunks
            ]
            self._bm25 = BM25L(corpus)
            self._lexical_fingerprint = fingerprint
        return len(chunks)

    def _dense_ranking(self, query: str, limit: int) -> list[tuple[Document, float]]:
        if self._store is None:
            raise RuntimeError("ensure_index must run before search")
        return self._store.similarity_search_with_relevance_scores(query, k=limit)

    def _lexical_ranking(self, query: str, limit: int) -> list[tuple[Document, float]]:
        if self._chunks is None or self._bm25 is None:
            raise RuntimeError("ensure_index must run before search")
        scores = self._bm25.get_scores(_lexical_tokens(query))
        scored = [
            (document, float(score))
            for document, score in zip(self._chunks, scores)
            if score > 0
        ]
        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    def search_reranked_hybrid(
        self, query: str, top_k: int = 3, reranker: Any | None = None
    ) -> list[dict[str, Any]]:
        """Rerank the union of Dense Top-3 and positive BM25 Top-3."""
        if not 1 <= top_k <= MAX_RESULTS:
            raise ValueError("top_k must be between 1 and 3")
        if not query.strip():
            return []
        self.ensure_index()
        fetch_k = min(RETRIEVAL_CANDIDATES, len(self._chunks or []))
        candidates: dict[str, dict[str, Any]] = {}
        for rank, (document, relevance) in enumerate(self._dense_ranking(query, fetch_k), 1):
            if relevance < self.relevance_threshold:
                continue
            chunk_id = str(document.metadata["chunk_id"])
            candidates[chunk_id] = {
                "chunk_id": chunk_id,
                "source": str(document.metadata["source"]),
                "title": str(document.metadata["title"]),
                "content": document.page_content,
                "dense_rank": rank,
                "dense_relevance": float(relevance),
                "lexical_rank": None,
                "lexical_score": None,
            }
        for rank, (document, lexical_score) in enumerate(self._lexical_ranking(query, fetch_k), 1):
            if lexical_score <= 0:
                continue
            chunk_id = str(document.metadata["chunk_id"])
            if chunk_id in candidates:
                candidates[chunk_id]["lexical_rank"] = rank
                candidates[chunk_id]["lexical_score"] = float(lexical_score)
            else:
                candidates[chunk_id] = {
                    "chunk_id": chunk_id,
                    "source": str(document.metadata["source"]),
                    "title": str(document.metadata["title"]),
                    "content": document.page_content,
                    "dense_rank": None,
                    "dense_relevance": None,
                    "lexical_rank": rank,
                    "lexical_score": float(lexical_score),
                }
        ordered = list(candidates.values())
        if not ordered:
            return []
        if reranker is None:
            from evaluation.rerank import get_reranker

            reranker = get_reranker()
        scores = reranker.score(query, [f"{row['title']}\n{row['content']}" for row in ordered])
        if len(scores) != len(ordered):
            raise ValueError("Reranker returned an unexpected number of scores")
        for row, score in zip(ordered, scores, strict=True):
            row["score"] = float(score)
        ordered.sort(key=lambda row: (-row["score"], row["chunk_id"]))
        return ordered[:top_k]

    def search(
        self,
        query: str,
        top_k: int = 3,
        method: Literal["dense", "lexical", "hybrid"] = "hybrid",
        apply_relevance_threshold: bool = True,
    ) -> list[dict[str, Any]]:
        """Retrieve chunks, fuse rankings, and reject insufficiently relevant results."""
        if top_k < 1:
            raise ValueError("top_k must be positive")
        if top_k > MAX_RESULTS:
            raise ValueError("top_k must not exceed 3")
        if method not in ("dense", "lexical", "hybrid"):
            raise ValueError("Unknown retrieval method")
        if not query.strip():
            return []
        self.ensure_index()
        fetch_k = min(RETRIEVAL_CANDIDATES, len(self._chunks or []))
        dense = self._dense_ranking(query, fetch_k) if method in ("dense", "hybrid") else []
        lexical = self._lexical_ranking(query, fetch_k) if method in ("lexical", "hybrid") else []

        scores: dict[str, float] = {}
        documents: dict[str, Document] = {}
        dense_ranks: dict[str, int] = {}
        dense_relevance: dict[str, float] = {}
        lexical_ranks: dict[str, int] = {}
        lexical_scores: dict[str, float] = {}

        if method in ("dense", "hybrid"):
            for rank, (document, relevance) in enumerate(dense, start=1):
                chunk_id = str(document.metadata["chunk_id"])
                documents[chunk_id] = document
                dense_ranks[chunk_id] = rank
                dense_relevance[chunk_id] = float(relevance)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1 / (10 + rank)

        if method in ("lexical", "hybrid"):
            for rank, (document, lexical_score) in enumerate(lexical, start=1):
                if lexical_score <= 0:
                    continue
                chunk_id = str(document.metadata["chunk_id"])
                documents[chunk_id] = document
                lexical_ranks[chunk_id] = rank
                lexical_scores[chunk_id] = lexical_score
                lexical_weight = 1.0 if method == "lexical" else self.lexical_weight
                scores[chunk_id] = scores.get(chunk_id, 0.0) + lexical_weight / (10 + rank)

        ordered_ids = sorted(scores, key=lambda chunk_id: scores[chunk_id], reverse=True)
        if apply_relevance_threshold and method in ("dense", "hybrid"):
            ordered_ids = [
                chunk_id
                for chunk_id in ordered_ids
                if dense_relevance.get(chunk_id, float("-inf")) >= self.relevance_threshold
                or lexical_scores.get(chunk_id, 0.0) > 0
            ]
        ordered_ids = ordered_ids[:top_k]
        return [
            {
                "title": str(documents[chunk_id].metadata["title"]),
                "content": documents[chunk_id].page_content,
                "source": str(documents[chunk_id].metadata["source"]),
                "chunk_id": chunk_id,
                "score": round(scores[chunk_id], 4),
                "dense_rank": dense_ranks.get(chunk_id),
                "dense_relevance": (
                    round(dense_relevance[chunk_id], 4) if chunk_id in dense_relevance else None
                ),
                "lexical_rank": lexical_ranks.get(chunk_id),
                "lexical_score": (
                    round(lexical_scores[chunk_id], 4) if chunk_id in lexical_scores else None
                ),
            }
            for chunk_id in ordered_ids
        ]


@lru_cache(maxsize=1)
def get_policy_knowledge_base() -> PolicyKnowledgeBase:
    """Reuse one model and Chroma client for all requests in this process."""
    policy_override = os.getenv("ORDERCARE_EVAL_POLICY_PATH")
    index_override = os.getenv("ORDERCARE_EVAL_CHROMA_PATH")
    if bool(policy_override) != bool(index_override):
        raise ValueError("Evaluation policy and Chroma paths must be set together")
    if policy_override and index_override:
        return PolicyKnowledgeBase(
            policy_path=Path(policy_override), persist_directory=Path(index_override)
        )
    return PolicyKnowledgeBase(policy_path=DEFAULT_SERVING_POLICY_PATH)
