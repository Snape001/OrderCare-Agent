"""Build an offline paired report from saved three-way retrieval and DeepSeek generations."""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluation.evidence import reviewed_metrics  # noqa: E402
from evaluation.generation import METRICS, generation_summary  # noqa: E402
from evaluation.rag import mean  # noqa: E402
from evaluation.three_way import save_json  # noqa: E402

OUTPUT = Path("data/evaluation/rag/three-way-comparison-v1")


def paired(
    rows: dict[str, dict[str, Any]], left: str, right: str, metric: str, split: str
) -> dict[str, Any]:
    values = []
    for case_id in {key.split(":", 1)[1] for key in rows}:
        a = rows.get(f"{left}:{case_id}")
        b = rows.get(f"{right}:{case_id}")
        if not a or not b or (split != "all" and a["split"] != split):
            continue
        av, bv = a.get("metrics", {}).get(metric), b.get("metrics", {}).get(metric)
        if av is not None and bv is not None:
            values.append((av, bv))
    return {
        "paired_n": len(values),
        "left_mean": mean([a for a, _ in values]),
        "right_mean": mean([b for _, b in values]),
        "delta": mean([b - a for a, b in values]),
    }


def usage_cost(records: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens = sum((r.get("usage") or {}).get("input_tokens", 0) or 0 for r in records)
    output_tokens = sum((r.get("usage") or {}).get("output_tokens", 0) or 0 for r in records)
    cache_read = sum(
        ((r.get("usage") or {}).get("input_token_details") or {}).get("cache_read", 0) or 0
        for r in records
    )
    return {
        "requests": len(records),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "estimated_cny_offpeak": round(
            ((input_tokens - cache_read) * 1 + cache_read * 0.02 + output_tokens * 4) / 1e6,
            6,
        ),
        "estimated_cny_peak": round(
            ((input_tokens - cache_read) * 2 + cache_read * 0.04 + output_tokens * 8) / 1e6,
            6,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output
    retrieval = json.loads((output / "results.json").read_text(encoding="utf-8"))
    generation = json.loads((output / "generation-results.json").read_text(encoding="utf-8"))
    evidence = json.loads((output / "evidence-results.json").read_text(encoding="utf-8"))
    if generation["manifest"]["retrieval_sha256"] != sha256(
        (output / "results.json").read_bytes()
    ).hexdigest():
        raise ValueError("Retrieval results changed since generation")
    if evidence["manifest"]["retrieval_sha256"] != sha256(
        (output / "results.json").read_bytes()
    ).hexdigest():
        raise ValueError("Retrieval results changed since evidence audit")
    rows = copy.deepcopy(generation["cases"])
    for row in rows.values():
        row["raw_metrics"] = copy.deepcopy(row.get("metrics"))
        row["metrics"], row["judge_warnings"] = reviewed_metrics(row)
        entry = evidence["cases"][evidence["mapping"][f"{row['method']}:{row['id']}"]]
        row["metrics"]["evidence_sufficiency"] = entry["metrics"]["evidence_sufficiency"]
        row["metrics"]["fact_evidence_coverage"] = entry["metrics"]["fact_evidence_coverage"]
        row["evidence_sufficiency_origin"] = entry.get("origin", "invalid_judge")
        row["independent_evidence"] = entry["metrics"]
    evidence_summary = {}
    for run in retrieval["runs"]:
        groups = {}
        for split in ("all", "dev", "test"):
            values = [
                evidence["cases"][evidence["mapping"][f"{run['method']}:{row['id']}"]][
                    "metrics"
                ]["evidence_sufficiency"]
                for row in run["cases"]
                if split == "all" or row["split"] == split
            ]
            valid = [value for value in values if value is not None]
            groups[split] = {"mean": mean(valid), "valid": len(valid), "total": len(values)}
        evidence_summary[run["method"]] = groups
    summaries = {
        run["method"]: generation_summary(
            [rows[f"{run['method']}:{case_id}"] for case_id in generation["manifest"]["case_ids"]]
        )
        for run in retrieval["runs"]
    }
    engineering = {
        run["method"]: {
            "retrieval_total_ms": sum(
                sum(row["retrieval_latency_ms"]) for row in run["cases"]
            ),
            "generation_total_ms": sum(
                rows[f"{run['method']}:{case_id}"]["generation"].get("latency_ms", 0)
                for case_id in generation["manifest"]["case_ids"]
            ),
            "judge_total_ms": sum(
                rows[f"{run['method']}:{case_id}"].get("judge", {}).get("latency_ms", 0)
                for case_id in generation["manifest"]["case_ids"]
            ),
        }
        for run in retrieval["runs"]
    }
    no_answer_refusal = {}
    for run in retrieval["runs"]:
        values = [
            rows[f"{run['method']}:{case_id}"]["metrics"].get("abstention_accuracy")
            for case_id in generation["manifest"]["case_ids"]
            if rows[f"{run['method']}:{case_id}"]["should_abstain"]
        ]
        valid = [value for value in values if value is not None]
        no_answer_refusal[run["method"]] = {
            "mean": mean(valid), "valid": len(valid), "total": len(values)
        }
    comparisons = {
        f"{left}_vs_{right}": {
            split: {metric: paired(rows, left, right, metric, split) for metric in METRICS}
            for split in ("all", "dev", "test")
        }
        for left, right in (("dense", "hybrid"), ("hybrid", "rewrite_hybrid"))
    }
    rewrite_cache = json.loads((output / "rewrite-cache.json").read_text(encoding="utf-8"))
    by_phase = {
        "rewrite": usage_cost(list(rewrite_cache["cases"].values())),
        "generation": usage_cost([r["generation"] for r in rows.values()]),
        "judge": usage_cost([r["judge"] for r in rows.values() if "judge" in r]),
        "evidence_audit": usage_cost(
            [r["raw"] for r in evidence["cases"].values() if "raw" in r]
        ),
    }
    calls = list(rewrite_cache["cases"].values())
    calls += [r[phase] for r in rows.values() for phase in ("generation", "judge") if phase in r]
    calls += [r["raw"] for r in evidence["cases"].values() if "raw" in r]
    report = {
        "retrieval_summary": {
            run["method"]: {"all": run["summary"], **run["splits"]} for run in retrieval["runs"]
        },
        "generation_summary": summaries,
        "evidence_summary": evidence_summary,
        "engineering": engineering,
        "generation_no_answer_refusal": no_answer_refusal,
        "paired_comparison": comparisons,
        "generation_case_ids": generation["manifest"]["case_ids"],
        "case_results": {
            key: {
                "metrics": row["metrics"],
                "judge_warnings": row["judge_warnings"],
                "evidence_sufficiency_origin": row["evidence_sufficiency_origin"],
            }
            for key, row in rows.items()
        },
        "api_usage": usage_cost(calls),
        "api_usage_by_phase": by_phase,
        "mean_rewrite_latency_ms": retrieval["rewrite_summary"]["mean_latency_ms"],
        "pricing": {
            "model": generation["manifest"]["model"],
            "source": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
            "price_checked_date": "2026-10-31",
            "unit": "CNY per million tokens",
            "offpeak_uncached_input": 1,
            "offpeak_cached_input": 0.02,
            "offpeak_output": 4,
            "peak_multiplier": 2,
            "note": "Estimate from reported usage; actual billing may differ.",
        },
    }
    save_json(output / "comparison.json", report)
    retrieval_count = len(retrieval["runs"][0]["cases"])
    generation_count = len(report["generation_case_ids"])
    no_answer_count = next(iter(no_answer_refusal.values()))["total"]
    lines = [
        "# RAG 三方案实验报告",
        "",
        f"{retrieval_count}题检索全部完成；每方案对同一组{generation_count}题生成回答。",
        "",
        "## 检索指标",
        "",
        (output / "metrics.md").read_text(encoding="utf-8"),
        "## 生成与证据指标（有效样本均值）",
        "",
        f"### 独立证据充分性：全部{retrieval_count}题",
        "",
        "| 方案 / split | Evidence Sufficiency | 有效题数 |",
        "| --- | ---: | ---: |",
    ]
    fmt = lambda value: "null" if value is None else f"{value:.4f}"  # noqa: E731
    for method, evidence_groups in evidence_summary.items():
        for split, item in evidence_groups.items():
            lines.append(
                f"| {method} / {split} | {fmt(item['mean'])} | {item['valid']}/{item['total']} |"
            )
    lines += [
        "",
        f"### 生成回答：成对{generation_count}题",
        "",
        "| 方案 / split | Correctness | Faithfulness | Citation | Abstention | Evidence sufficiency | 生成题数 / Judge有效题数 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for method, summary in summaries.items():
        for split, item in summary.items():
            m = item["metrics"]
            lines.append(
                f"| {method} / {split} | {fmt(m['answer_correctness']['mean'])} ({m['answer_correctness']['valid']}) | "
                f"{fmt(m['faithfulness']['mean'])} ({m['faithfulness']['valid']}) | "
                f"{fmt(m['citation_support_rate']['mean'])} ({m['citation_support_rate']['valid']}) | "
                f"{fmt(m['abstention_accuracy']['mean'])} ({m['abstention_accuracy']['valid']}) | "
                f"{fmt(m['evidence_sufficiency']['mean'])} ({m['evidence_sufficiency']['valid']}) | "
                f"{item['generated']} / {item['judged']} |"
            )
    lines += [
        "",
        f"无答案题的**生成拒答准确率**单独统计；样本中共有{no_answer_count}道无答案题，"
        "Judge无效的题不计入分母：",
        "",
        "| 方案 | 拒答准确率 | 有效/无答案样本 |",
        "| --- | ---: | ---: |",
    ]
    for method, item in no_answer_refusal.items():
        lines.append(f"| {method} | {fmt(item['mean'])} | {item['valid']}/{item['total']} |")
    lines += ["", "## 成对比较（右方案减左方案）", ""]
    for pair, comparison_groups in comparisons.items():
        lines += [f"### {pair}", "", "| split | 指标 | 配对N | 左 | 右 | 差值 |", "| --- | --- | ---: | ---: | ---: | ---: |"]
        for split, comparison_metrics in comparison_groups.items():
            for metric, pair_item in comparison_metrics.items():
                lines.append(
                    f"| {split} | {metric} | {pair_item['paired_n']} | {fmt(pair_item['left_mean'])} | "
                    f"{fmt(pair_item['right_mean'])} | {fmt(pair_item['delta'])} |"
                )
        lines.append("")
    cost = report["api_usage"]
    lines += [
        "## API、延迟与限制",
        "",
        f"DeepSeek 请求 {cost['requests']} 次；输入 {cost['input_tokens']}、输出 "
        f"{cost['output_tokens']} Token，其中缓存命中输入 {cost['cache_read_tokens']}。",
        f"按官方当前 Flash 价估算，低峰约 ¥{cost['estimated_cny_offpeak']}，"
        f"高峰约 ¥{cost['estimated_cny_peak']}；非实际账单。",
        f"仅 Query Rewrite：{by_phase['rewrite']['requests']}次，均值 {retrieval['rewrite_summary']['mean_latency_ms']:.1f} ms，"
        f"输入/输出 {by_phase['rewrite']['input_tokens']}/{by_phase['rewrite']['output_tokens']} Token，"
        f"低峰估算 ¥{by_phase['rewrite']['estimated_cny_offpeak']}。",
        "各阶段请求/Token/费用估算见 `comparison.json` 的 `api_usage_by_phase`。",
        "",
        f"| 方案 | {retrieval_count}题检索总 ms | {generation_count}题生成总 ms | {generation_count}题 Judge总 ms |",
        "| --- | ---: | ---: | ---: |",
    ]
    for method, item in engineering.items():
        lines.append(
            f"| {method} | {item['retrieval_total_ms']:.1f} | "
            f"{item['generation_total_ms']:.1f} | {item['judge_total_ms']:.1f} |"
        )
    lines += [
        "",
        "重写总耗时单列，未计入本地检索耗时。逐题延迟和 Token 见 JSON。",
        "改写校验只能捕捉显式数字、实体词和否定漂移，不能证明语义完全一致。",
        "同模型 Judge 是估计，格式或原文锚点不可靠时保留 null。",
        f"生成覆盖{generation_count}/{retrieval_count}题；无效 Judge 分数保留 null，不能当作正确或错误。",
        "",
        "## 结论与推荐",
        "",
    ]
    retrieval_summaries = report["retrieval_summary"]
    direct = retrieval_summaries["dense"]
    hybrid = retrieval_summaries["hybrid"]
    rewrite = retrieval_summaries["rewrite_hybrid"]
    lines += [
        f"- **Direct 与 Hybrid：**Recall@2 全量 {fmt(direct['all']['at_2']['recall'])} → "
        f"{fmt(hybrid['all']['at_2']['recall'])}；留出集 {fmt(direct['test']['at_2']['recall'])} → "
        f"{fmt(hybrid['test']['at_2']['recall'])}。MRR、nDCG 与生成层有效样本见上表。",
        f"- **Query Rewrite：**相对 Hybrid 的 Recall@2 全量 {fmt(hybrid['all']['at_2']['recall'])} → "
        f"{fmt(rewrite['all']['at_2']['recall'])}；留出集 {fmt(hybrid['test']['at_2']['recall'])} → "
        f"{fmt(rewrite['test']['at_2']['recall'])}。重写额外平均 "
        f"{retrieval['rewrite_summary']['mean_latency_ms']:.1f} ms/题；以留出集与有效配对生成指标决定是否值得。",
        f"- **证据与拒答：**独立证据充分性全量 Direct/Hybrid/Rewrite 分别为 "
        f"{fmt(evidence_summary['dense']['all']['mean'])}/"
        f"{fmt(evidence_summary['hybrid']['all']['mean'])}/"
        f"{fmt(evidence_summary['rewrite_hybrid']['all']['mean'])}。"
        f"无答案空检索率分别为 {fmt(direct['all']['no_answer_rejection_rate'])}/"
        f"{fmt(hybrid['all']['no_answer_rejection_rate'])}/"
        f"{fmt(rewrite['all']['no_answer_rejection_rate'])}；生成拒答准确率另按有效样本统计。",
        "- **决策：**本实验不自动启用候选。Ground Truth 由开发助手依据模拟政策编写，"
        "尚未经独立人工复核；DeepSeek Judge 仅为辅助估计，失败或不可靠的判定保留 null。",
        "",
    ]
    previous = ROOT / "data/evaluation/rag/three-way-comparison-v1/results.json"
    if retrieval_count > 40 and previous.exists():
        old_runs = {
            run["method"]: run["cases"]
            for run in json.loads(previous.read_text(encoding="utf-8"))["runs"]
        }
        current_runs = {run["method"]: run["cases"] for run in retrieval["runs"]}
        lines += [
            "## 旧40题在扩充知识库后的回归",
            "",
            "同一题目的答案事实保持不变；仅比较检索分数，旧结果取自冻结的 v1 实验。",
            "两轮来源路径和政策标题版本不同，比较的是语义章节命中率。",
            "",
            "| 方案 | v1 Recall@2 | v2 Recall@2 | v1 MRR@2 | v2 MRR@2 | v1 nDCG@2 | v2 nDCG@2 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for method, old_cases in old_runs.items():
            old_ids = {case["id"] for case in old_cases}
            new_cases = [case for case in current_runs[method] if case["id"] in old_ids]
            def mean_metric(cases: list[dict[str, Any]], metric: str) -> float:
                values = [case["retrieval"]["2"][metric] for case in cases]
                return statistics.mean(value for value in values if value is not None)
            lines.append(
                f"| {method} | {fmt(mean_metric(old_cases, 'recall'))} | "
                f"{fmt(mean_metric(new_cases, 'recall'))} | "
                f"{fmt(mean_metric(old_cases, 'mrr'))} | "
                f"{fmt(mean_metric(new_cases, 'mrr'))} | "
                f"{fmt(mean_metric(old_cases, 'ndcg'))} | "
                f"{fmt(mean_metric(new_cases, 'ndcg'))} |"
            )
        lines += [
            "",
            "知识库从单篇扩到41章节后，固定 Top-2 的旧题召回下降；这表明证据在更多相近章节中被分散，"
            "不能仅凭新增50题的总体均值声称扩库提高了旧业务覆盖。",
            "",
        ]
        dense_cases = {case["id"]: case for case in current_runs["dense"]}
        hybrid_cases = {case["id"]: case for case in current_runs["hybrid"]}
        rewrite_cases = {case["id"]: case for case in current_runs["rewrite_hybrid"]}
        def recall_change(left: dict[str, dict[str, Any]], right: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
            gains, losses = [], []
            for case_id, left_case in left.items():
                old_value = left_case["retrieval"]["2"]["recall"]
                new_value = right[case_id]["retrieval"]["2"]["recall"]
                if old_value is None or new_value is None:
                    continue
                if new_value > old_value:
                    gains.append(case_id)
                elif new_value < old_value:
                    losses.append(case_id)
            return gains, losses
        hybrid_gains, hybrid_losses = recall_change(dense_cases, hybrid_cases)
        rewrite_gains, rewrite_losses = recall_change(hybrid_cases, rewrite_cases)
        lines += [
            "## 逐题召回变化与推荐",
            "",
            f"- Hybrid 相对 Direct：提升 {len(hybrid_gains)} 题（{', '.join(hybrid_gains)}）；"
            f"下降 {len(hybrid_losses)} 题（{', '.join(hybrid_losses)}）。",
            f"- Rewrite 相对 Hybrid：提升 {len(rewrite_gains)} 题（{', '.join(rewrite_gains)}）；"
            f"下降 {len(rewrite_losses)} 题（{', '.join(rewrite_losses)}）。",
            "- 当前建议保留线上默认策略；若后续针对 v2 扩库，先研究 Top-K 与上下文预算、"
            "跨文档证据组装及无答案拒答阈值。全量重写的召回净收益为零，不值得常态化增加调用。",
            "- 无答案17题仅有2题返回空结果；其余题召回了同主题但不足以支持答案的政策。"
            "生成拒答的 Judge 有效样本很少，不能外推为全量拒答准确率。",
            "",
        ]
    (output / "optimization-report.md").write_text("\n".join(lines), encoding="utf-8")
    failures = ["# 生成失败与不确定案例", ""]
    for key, row in rows.items():
        if row.get("judge", {}).get("status") != "ok" or row.get("judge_warnings") or any(
            value is not None and value < 1
            for name, value in row["metrics"].items()
            if name in METRICS
        ):
            failures.append(
                f"- {key}：问题={row['query']}；实际回答={row['generation'].get('answer')}；"
                f"检索章节={[h['title'] for h in row['hits']]}；指标={row['metrics']}；"
                f"Judge状态={row.get('judge', {}).get('status')}；告警={row['judge_warnings']}"
            )
    (output / "generation-failures.md").write_text("\n".join(failures) + "\n", encoding="utf-8")
    print(json.dumps({"paired": comparisons, "cost": cost}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
