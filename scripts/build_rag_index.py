"""Initialize the current policy RAG index and warm its BGE embedding model."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from customer_support.rag import get_policy_knowledge_base  # noqa: E402


def main() -> None:
    kb = get_policy_knowledge_base()
    count = kb.ensure_index()
    kb.embedding.embed_query("售后政策索引初始化")
    print(f"RAG index ready: {count} chunks; embedding: {getattr(kb.embedding, 'model_name', 'configured')}")


if __name__ == "__main__":
    main()
