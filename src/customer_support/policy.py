"""Policy document parsing and the public knowledge-base search entry point."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

POLICY_PATH = Path("data/policies/customer_service_policy.md")


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
            )
        )
    return sections


def search_policy(query: str) -> dict[str, Any]:
    """Search the persistent vector knowledge base and return the best cited hit."""
    # Local import prevents loading Chroma/FastEmbed when only parsing documents.
    from customer_support.rag import get_policy_knowledge_base

    hits = get_policy_knowledge_base().search(query, top_k=2, method="hybrid")
    return format_policy_hits(hits)


def format_policy_hits(hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Shared tool-result assembly for serving and generation replay."""
    if not hits:
        return {
            "title": "未检索到相关政策",
            "content": "当前知识库没有足够相关的内容，建议转人工客服处理。",
            "source": POLICY_PATH.as_posix(),
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
