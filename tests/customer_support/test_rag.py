from __future__ import annotations

import hashlib
from pathlib import Path

from langchain_core.embeddings import Embeddings

from customer_support.policy import load_policy_sections, search_policy
from customer_support.rag import PolicyKnowledgeBase, _lexical_tokens, load_policy_chunks


class HashEmbeddings(Embeddings):
    """Small deterministic test double; real code uses BGE Chinese embeddings."""

    dimensions = 32

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for index in range(max(1, len(text) - 1)):
            token = text[index : index + 2]
            bucket = int(hashlib.sha1(token.encode()).hexdigest()[:8], 16)
            vector[bucket % self.dimensions] += 1.0
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def test_policy_markdown_is_parsed_and_chunked():
    sections = load_policy_sections()
    chunks = load_policy_chunks()

    assert [section.title for section in sections] == [
        "七天无理由退款",
        "特殊商品退换限制",
        "退款到账时效",
        "换货与缺件补发",
        "订单取消",
        "物流时效与轨迹",
        "物流异常",
        "收货地址修改",
        "商品保修",
        "维修申请与进度",
        "发票服务",
        "支付与重复扣款",
        "优惠券与促销",
        "账户与隐私",
        "客服升级与工单",
        "投诉与服务时效",
    ]
    assert len(chunks) >= len(sections)
    assert chunks[0].metadata["source"].endswith("customer_service_policy.md")


def test_hybrid_search_returns_cited_policy(tmp_path: Path):
    knowledge_base = PolicyKnowledgeBase(
        persist_directory=tmp_path / "chroma",
        embedding=HashEmbeddings(),
    )

    hits = knowledge_base.search("电子产品进水了还能保修吗", top_k=2)

    warranty = next(hit for hit in hits if hit["title"] == "商品保修")
    assert "进水" in warranty["content"]
    assert warranty["source"].endswith("customer_service_policy.md")
    assert warranty["lexical_rank"] is not None


def test_index_is_reused_when_policy_does_not_change(tmp_path: Path):
    knowledge_base = PolicyKnowledgeBase(
        persist_directory=tmp_path / "chroma",
        embedding=HashEmbeddings(),
    )

    first_count = knowledge_base.ensure_index()
    manifest_before = knowledge_base.manifest_path.read_text(encoding="utf-8")
    second_count = knowledge_base.ensure_index()

    assert first_count == second_count == len(load_policy_chunks())
    assert knowledge_base.manifest_path.read_text(encoding="utf-8") == manifest_before


def test_dense_search_can_reject_unrelated_question(tmp_path: Path):
    knowledge_base = PolicyKnowledgeBase(
        persist_directory=tmp_path / "chroma",
        embedding=HashEmbeddings(),
        relevance_threshold=0.95,
    )

    hits = knowledge_base.search("请解释快速排序的时间复杂度", top_k=2, method="dense")

    assert hits == []


def test_invalid_search_inputs_fail_before_index_access():
    import pytest

    kb = PolicyKnowledgeBase(embedding=HashEmbeddings())
    with pytest.raises(ValueError, match="positive"):
        kb.search("query", top_k=0)
    with pytest.raises(ValueError, match="exceed 3"):
        kb.search("query", top_k=4)
    with pytest.raises(ValueError, match="method"):
        kb.search("query", method="invalid")
    assert kb.search("   ") == []


def test_fusion_weight_default_preserves_ranking(tmp_path):
    base = PolicyKnowledgeBase(persist_directory=tmp_path / "index", embedding=HashEmbeddings())
    explicit = PolicyKnowledgeBase(
        persist_directory=tmp_path / "index",
        embedding=HashEmbeddings(),
        lexical_weight=1.0,
    )
    assert base.search("电子产品进水了还能保修吗", top_k=2) == explicit.search(
        "电子产品进水了还能保修吗", top_k=2
    )


def test_bm25_modes_and_candidate_limits(tmp_path: Path):
    kb = PolicyKnowledgeBase(persist_directory=tmp_path / "index", embedding=HashEmbeddings())
    assert "ab-1234" in _lexical_tokens("查询 AB-1234 订单")
    assert "2026" in _lexical_tokens("2026 年保修")
    assert kb.search("XY-9999", method="lexical") == []

    for method in ("dense", "lexical", "hybrid"):
        hits = kb.search("电子产品进水保修", top_k=3, method=method)
        assert 1 <= len(hits) <= 3
        assert all(hit["source"] for hit in hits)
        assert all(hit["dense_rank"] is None or hit["dense_rank"] <= 3 for hit in hits)
        assert all(hit["lexical_rank"] is None or hit["lexical_rank"] <= 3 for hit in hits)
        if method == "hybrid":
            for hit in hits:
                expected = sum(
                    1 / (10 + rank)
                    for rank in (hit["dense_rank"], hit["lexical_rank"])
                    if rank is not None
                )
                assert hit["score"] == round(expected, 4)
    assert kb.search("AB-1234", method="lexical") == []


def test_bm25_rebuilds_when_policy_changes(tmp_path: Path):
    policy = tmp_path / "policy.md"
    policy.write_text("## 售后规则\n蓝牙耳机可以申请售后。", encoding="utf-8")
    kb = PolicyKnowledgeBase(
        policy_path=policy, persist_directory=tmp_path / "index", embedding=HashEmbeddings()
    )
    assert kb.search("蓝牙耳机", method="lexical")
    before = kb._bm25
    policy.write_text("## 售后规则\n智能手表可以申请售后。", encoding="utf-8")
    assert kb.search("智能手表", method="lexical")
    assert kb._bm25 is not before
    assert kb.search("蓝牙耳机", method="lexical") == []


def test_search_policy_uses_rewrite_and_reranked_hybrid(monkeypatch):
    class FakeKnowledgeBase:
        policy_path = Path("data/policies/v3")

        def search_reranked_hybrid(self, query: str, top_k: int):
            assert (query, top_k) == ("保修凭证", 3)
            return [
                {"title": str(index), "content": "政策", "source": "policy.md", "score": 0.1}
                for index in range(3)
            ]

    monkeypatch.setattr("customer_support.rag.get_policy_knowledge_base", FakeKnowledgeBase)
    monkeypatch.setattr("customer_support.query_rewrite.rewrite_policy_query", lambda _: "保修凭证")
    result = search_policy("保修")
    assert len(result["references"]) == 3
    assert result["source"] == "policy.md"


def test_reranked_hybrid_uses_filtered_unique_top3_candidates(tmp_path: Path, monkeypatch):
    from langchain_core.documents import Document

    def chunk(identifier: str) -> Document:
        return Document(page_content=f"内容{identifier}", metadata={
            "chunk_id": identifier, "title": f"标题{identifier}", "source": "policy.md"
        })

    kb = PolicyKnowledgeBase(persist_directory=tmp_path / "index", embedding=HashEmbeddings())
    monkeypatch.setattr(kb, "ensure_index", lambda: 4)
    kb._chunks = [chunk(str(index)) for index in range(4)]
    monkeypatch.setattr(kb, "_dense_ranking", lambda query, limit: [
        (chunk("a"), 0.9), (chunk("b"), 0.7), (chunk("c"), 0.2)
    ])
    monkeypatch.setattr(kb, "_lexical_ranking", lambda query, limit: [
        (chunk("b"), 3.0), (chunk("d"), 2.0), (chunk("e"), 1.0)
    ])

    class FakeReranker:
        def score(self, query: str, passages: list[str]) -> list[float]:
            assert query == "有效改写"
            assert len(passages) == 4
            return [float({"a": 1, "b": 4, "d": 3, "e": 2}[p[-1]]) for p in passages]

    hits = kb.search_reranked_hybrid("有效改写", reranker=FakeReranker())
    assert [hit["chunk_id"] for hit in hits] == ["b", "d", "e"]
    assert hits[0]["dense_rank"] == 2
    assert hits[0]["lexical_rank"] == 1
    assert all(hit["chunk_id"] != "c" for hit in hits)


def test_policy_rewrite_validates_and_falls_back(monkeypatch):
    from types import SimpleNamespace

    from customer_support import query_rewrite

    class FakeModel:
        response = '{"query":"耳机没购买凭证如何申请保修？"}'

        def model_copy(self, update):
            assert update == {"temperature": 0, "max_tokens": 180, "streaming": False}
            return self

        def invoke(self, messages):
            assert messages[1].content == "耳机没凭证怎么保修？"
            return SimpleNamespace(content=self.response)

    model = FakeModel()
    monkeypatch.setattr(query_rewrite.settings, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(query_rewrite, "get_model", lambda _: model)
    query = "耳机没凭证怎么保修？"
    assert query_rewrite.rewrite_policy_query(query) == "耳机没购买凭证如何申请保修？"
    model.response = '{"query":"手机缺少购买凭证如何申请保修？"}'
    assert query_rewrite.rewrite_policy_query(query) == query
    model.response = "invalid JSON"
    assert query_rewrite.rewrite_policy_query(query) == query


def test_non_retrievable_sections_are_excluded_from_both_indexes(tmp_path: Path):
    policy = tmp_path / "policy.md"
    policy.write_text(
        "## 免责声明\n纯测试导航标记 XYZ999。\n\n"
        "## 售后规则\n耳机进水后需要核验保修资格。",
        encoding="utf-8",
    )
    kb = PolicyKnowledgeBase(
        policy_path=policy, persist_directory=tmp_path / "index", embedding=HashEmbeddings()
    )
    assert kb.ensure_index() == 1
    assert kb.search("XYZ999", method="lexical") == []
    assert all(hit["title"] != "免责声明" for hit in kb.search("XYZ999", method="dense"))
