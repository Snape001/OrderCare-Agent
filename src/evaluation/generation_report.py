"""Offline comparison of saved answers; no model calls and no retrieval reruns."""

from __future__ import annotations

import copy
from typing import Any

from evaluation.evidence import REVIEW_VERSION, context_digest, reviewed_metrics
from evaluation.generation import METRICS, diagnose, generation_summary
from evaluation.rag import mean, summarize


def prepare_report(
    report: dict[str, Any], audit: dict[str, Any], labels: dict[str, Any]
) -> dict[str, Any]:
    result = copy.deepcopy(report)
    manifest = report["generation_manifest"]
    if audit["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("Evidence audit dataset mismatch")
    by_id = {r["id"]: r for r in audit["cases"]}
    for row in result["runs"][0]["cases"]:
        entry = by_id[row["id"]]
        if entry["context_sha256"] != context_digest(row["context"]):
            raise ValueError("Cannot reuse evidence audit: context differs")
        row["raw_metrics"] = copy.deepcopy(row.get("metrics"))
        row["metrics"], row["judge_warnings"] = reviewed_metrics(row)
        row["metrics"].update(entry["metrics"])
        row["evidence_audit_status"] = entry["status"]
        suff = row["metrics"].get("evidence_sufficiency")
        abstained = row["metrics"].get("abstained")
        row["metrics"]["evidence_abstention_accuracy"] = (
            None if suff is None or abstained is None else float(abstained == (suff == 0))
        )
        row["diagnosis"] = diagnose(
            labels[row["id"]],
            row["hits"],
            row["context"],
            row["metrics"],
            row["generation"].get("answer", ""),
        )
    rows = result["runs"][0]["cases"]
    result["generation_summary"] = generation_summary(rows)
    k = report["metadata"]["configuration"]["top_k"]
    result["retrieval_summary"] = {}
    for split in ("all", "dev", "test"):
        group = [r for r in rows if split == "all" or r["split"] == split]
        result["retrieval_summary"][split] = summarize(group, k)
        summary = result["generation_summary"][split]
        values = [
            r["metrics"]["evidence_abstention_accuracy"]
            for r in group
            if r["metrics"]["evidence_abstention_accuracy"] is not None
        ]
        summary["metrics"]["evidence_abstention_accuracy"] = {
            "mean": mean(values),
            "valid": len(values),
        }
        summary["judge_warning_cases"] = sum(bool(r["judge_warnings"]) for r in group)
        for label, answerable in (("no_answer_refusal", False), ("answerable_false_refusal", True)):
            values = [
                float(r["metrics"]["abstained"])
                for r in group
                if r["should_abstain"] != answerable and r["metrics"].get("abstained") is not None
            ]
            summary[label] = {"mean": mean(values), "valid": len(values)}
    result["review_version"] = REVIEW_VERSION
    return result


def compare_generation(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    bm, cm = baseline["generation_manifest"], candidate["generation_manifest"]
    for key in (
        "dataset_sha256",
        "input_sha256",
        "prompt_version",
        "production_prompt",
        "judge_version",
        "provider",
        "model",
        "case_ids",
        "implementation_sha256",
    ):
        if bm[key] != cm[key]:
            raise ValueError(f"Not comparable: {key}")
    if baseline["model_info"] != candidate["model_info"]:
        raise ValueError("Not comparable: model parameters/identity")
    before, after = baseline["runs"][0]["cases"], candidate["runs"][0]["cases"]
    if [r["id"] for r in before] != [r["id"] for r in after]:
        raise ValueError("Not comparable: cases")
    if any(b["hits"] != c["hits"] for b, c in zip(before, after, strict=True)):
        raise ValueError("This context-only comparison requires identical retrieval")
    result: dict[str, Any] = {"review_version": REVIEW_VERSION, "splits": {}}
    for split in ("all", "dev", "test"):
        pairs = [
            (b, c)
            for b, c in zip(before, after, strict=True)
            if split == "all" or b["split"] == split
        ]
        metrics = {}
        for key in (*METRICS, "evidence_abstention_accuracy"):
            valid = [
                (b["metrics"].get(key), c["metrics"].get(key))
                for b, c in pairs
                if b["metrics"].get(key) is not None and c["metrics"].get(key) is not None
            ]
            metrics[key] = {
                "paired_n": len(valid),
                "baseline": mean([b for b, _ in valid]),
                "candidate": mean([c for _, c in valid]),
                "delta": mean([c - b for b, c in valid]),
            }
        result["splits"][split] = {
            "paired_metrics": metrics,
            "baseline": baseline["generation_summary"][split],
            "candidate": candidate["generation_summary"][split],
            "retrieval_baseline": baseline["retrieval_summary"][split],
            "retrieval_candidate": candidate["retrieval_summary"][split],
        }
    return result


def fmt(value: Any) -> str:
    return "null" if value is None else f"{value:.4f}"


def summary_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 生成与证据评测结果",
        "",
        "所有数值来自保存的真实模型调用；null 不计入均值，必须同时阅读有效样本数。",
        "证据充分性使用独立、不可见模型答案的证据审计；Judge 抽取矛盾的对应指标设为 null。",
        "",
        "| Split | 指标 | 均值 | 有效 N |",
        "| --- | --- | ---: | ---: |",
    ]
    for split, summary in report["generation_summary"].items():
        for key, value in summary["metrics"].items():
            lines.append(f"| {split} | {key} | {fmt(value['mean'])} | {value['valid']} |")
    lines += ["", "## 逐题记录", ""]
    for row in report["runs"][0]["cases"]:
        d = row["diagnosis"]
        lines += [
            f"### {row['id']} / {row['split']}: {row['query']}",
            "",
            f"预期：{row['expected_answer']}",
            "",
            "关键事实：" + "；".join(row["expected_facts"]),
            "",
            "召回：" + "；".join(h["source"] + "#" + h["title"] for h in row["hits"]),
            "",
            "实际回答：",
            "",
            row["generation"].get("answer", "（模型调用失败）"),
            "",
            "缺失证据：" + json_text(d["missing_evidence"]),
            "",
            "失败类型：" + ("、".join(d["failure_types"]) or "未自动归因"),
            "",
            "建议：" + "；".join(d["recommendations"]),
            "",
            "Judge 校验："
            + ("；".join(row["judge_warnings"]) or "结构与锚点校验通过；不等于语义判定准确"),
            "",
        ]
    return "\n".join(lines)


def json_text(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def comparison_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 生成 Baseline / Candidate 对比",
        "",
        "检索结果冻结复用；延迟为第一阶段实测回放，未重新计时。以下生成指标仅在双方都有效的同一批样本上计算差值。",
        "",
        "| Split | 指标 | Baseline | Candidate | 差值 | 配对 N |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for split, item in result["splits"].items():
        for key, m in item["paired_metrics"].items():
            lines.append(
                f"| {split} | {key} | {fmt(m['baseline'])} | {fmt(m['candidate'])} | {fmt(m['delta'])} | {m['paired_n']} |"
            )
        for key in ("recall", "mrr", "ndcg", "context_relevance"):
            b, c = (item[f"retrieval_{run}"]["at_2"][key] for run in ("baseline", "candidate"))
            lines.append(f"| {split} | {key}@2 | {fmt(b)} | {fmt(c)} | {fmt(c - b)} | 可答题 |")
        for key in ("generation_latency_ms", "judge_latency_ms"):
            b, c = item["baseline"][key], item["candidate"][key]
            lines.append(
                f"| {split} | {key} | {fmt(b)} | {fmt(c)} | {fmt(c - b) if b is not None and c is not None else 'null'} | 全部调用 |"
            )
        lines.append(
            f"| {split} | retrieval_p95_ms (replayed) | {fmt(item['retrieval_baseline']['latency_ms']['p95'])} | {fmt(item['retrieval_candidate']['latency_ms']['p95'])} | 0 | 回放 |"
        )
        for phase in ("generation", "judge"):
            for kind in ("input_tokens", "output_tokens", "total_tokens"):
                b, c = (item[run][phase + "_tokens"][kind] for run in ("baseline", "candidate"))
                lines.append(f"| {split} | {phase}_{kind} | {b} | {c} | {c - b} | 总计 |")
    return "\n".join(lines) + "\n"
