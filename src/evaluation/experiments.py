"""Small evaluation-only query expansion; not enabled in the live customer graph."""

from __future__ import annotations

# Versioned terminology normalization, preserving the entire original question.
# Selected from development-set error analysis; no question-ID or expected-label lookup.
EXPANSION_VERSION = "retail-terms-v1"
TERM_EXPANSIONS = {
    "刻字": "定制商品",
    "刻在": "定制商品",
    "验货": "仓库验收 退款到账",
    "开票": "发票",
    "不动弹": "物流轨迹无更新",
}


def expand_query(query: str) -> str:
    terms = list(dict.fromkeys(value for key, value in TERM_EXPANSIONS.items() if key in query))
    return query if not terms else query + " " + " ".join(terms)
