"""The setup entry point builds the online index without loading evaluation labels."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def test_build_rag_index_only_initializes_current_policy(monkeypatch, capsys) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "build_rag_index.py"
    spec = importlib.util.spec_from_file_location("build_rag_index", script)
    assert spec and spec.loader
    build_rag_index = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_rag_index)
    calls: list[str] = []
    embedding = SimpleNamespace(
        model_name="test-bge",
        embed_query=lambda query: calls.append(query) or [0.1],
    )
    knowledge_base = SimpleNamespace(
        embedding=embedding,
        ensure_index=lambda: calls.append("ensure_index") or 16,
    )
    monkeypatch.setattr(build_rag_index, "get_policy_knowledge_base", lambda: knowledge_base)

    build_rag_index.main()

    assert calls == ["ensure_index", "售后政策索引初始化"]
    assert "16 chunks" in capsys.readouterr().out
