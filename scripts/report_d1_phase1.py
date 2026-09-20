"""Summarize accepted source-support metrics; paired case bootstrap, no semantic judge."""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np

SEED = 20260920


def mean(values):
    usable = [x for x in values if x is not None]
    return dict(mean=float(np.mean(usable)) if usable else None, evaluable=len(usable), total=len(values))


def paired(before, after):
    pairs = [(a, b) for a, b in zip(before, after, strict=True) if a is not None and b is not None]
    if not pairs:
        return dict(point=None, ci95=None, evaluable=0, total=len(before))
    delta = np.array([b - a for a, b in pairs])
    rng = np.random.default_rng(SEED)
    samples = np.mean(delta[rng.integers(0, len(delta), size=(10000, len(delta)))], axis=1)
    return dict(
        point=float(delta.mean()),
        ci95=[float(x) for x in np.quantile(samples, [0.025, 0.975])],
        evaluable=len(pairs),
        total=len(before),
        seed=SEED,
        resamples=10000,
    )


def evidence(row, stage="final", metric="required_aspect_coverage"):
    return row.get("assessment", {}).get("support_coverage", {}).get(stage, {}).get(metric)


def ranking(row, stage, k, metric):
    return row.get("assessment", {}).get("retrieval", {}).get(stage, {}).get(str(k), {}).get(metric)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    rows = json.loads((args.directory / "results.json").read_text(encoding="utf-8"))
    manifest = json.loads((args.directory / "manifest.json").read_text(encoding="utf-8"))
    assert len(rows) == 288 and len({(r["case_id"], r["arm"]) for r in rows}) == 288
    summary, comparisons, ablation, bad = {}, {}, {}, []
    for split, total in (("dev", 32), ("regression", 24), ("safety", 16)):
        summary[split] = {}
        for arm in ("B0", "B1", "T1", "T2"):
            group = [r for r in rows if r["split"] == split and r["arm"] == arm]
            assert len(group) == total
            stats = dict(
                total=total,
                status_counts=dict(Counter(r["status"] for r in group)),
                degraded=sum(bool(r.get("degraded")) for r in group),
                retrieval={},
            )
            for stage in ("dense", "bm25", "rrf", "reranked"):
                stats["retrieval"][stage] = {
                    f"recall@{k}": mean([ranking(r, stage, k, "recall") for r in group])
                    for k in (5, 10, 20, 40)
                }
                stats["retrieval"][stage].update(
                    {f"{m}@10": mean([ranking(r, stage, 10, m) for r in group]) for m in ("mrr", "ndcg")}
                )
            stats["evidence"] = {
                stage: {
                    metric: mean([evidence(r, stage, metric) for r in group])
                    for metric in ("required_aspect_coverage", "group_coverage", "required_source_coverage")
                }
                for stage in ("initial", "rerank_input", "final")
            }
            stats["physical_evidence_probes"] = {
                k: sum(r.get("physical_evidence_probes", {}).get(k, 0) for r in group)
                for k in ("valid", "total")
            }
            stats["final_answer_citation_validity"] = None
            stats["errors"] = dict(Counter(r.get("error") for r in group if r["status"] != "SUCCESS"))
            summary[split][arm] = stats
            for r in group:
                initial, pool, final = [evidence(r, s) for s in ("initial", "rerank_input", "final")]
                categories = []
                if r["status"] != "SUCCESS":
                    categories.append("query_or_evaluation_failure")
                if initial is not None and initial < 1:
                    categories.append("branch_union_missing_required_aspects")
                if pool is not None and initial is not None and pool < initial:
                    categories.append("candidate_pool_loses_support")
                if final is not None and pool is not None and final < pool:
                    categories.append("selection_or_budget_loses_support")
                if final is not None and final < 1:
                    categories.append("final_context_incomplete")
                if categories:
                    bad.append(
                        dict(
                            case_id=r["case_id"],
                            split=split,
                            arm=arm,
                            categories=categories,
                            initial=initial,
                            candidate=pool,
                            final=final,
                        )
                    )
        comparisons[split] = {}
        by_arm = {
            a: {r["case_id"]: r for r in rows if r["split"] == split and r["arm"] == a}
            for a in ("B0", "B1", "T1", "T2")
        }
        for left, right in (("B0", "B1"), ("B1", "T2"), ("T1", "T2")):
            ids = sorted(by_arm[left])
            comparisons[split][right + "-" + left] = paired(
                [evidence(by_arm[left][i]) for i in ids], [evidence(by_arm[right][i]) for i in ids]
            )
    dev = sorted([r for r in rows if r["split"] == "dev" and r["arm"] == "T1"], key=lambda r: r["case_id"])
    for k, metric in [(k, "recall") for k in (5, 10, 20, 40)] + [(10, "mrr"), (10, "ndcg")]:
        values = [
            [r.get("ablation", {}).get(order, {}).get(str(k), {}).get(metric) for r in dev]
            for order in ("rrf", "bge")
        ]
        ablation[f"{metric}@{k}"] = paired(*values)
    ablation["required_evidence_coverage"] = paired(
        *[
            [
                r.get("ablation", {}).get(order + "_seed_coverage", {}).get("required_aspect_coverage")
                for r in dev
            ]
            for order in ("rrf", "bge")
        ]
    )
    equivalence = []
    for case_id in sorted({r["case_id"] for r in rows}):
        case = {r["arm"]: r for r in rows if r["case_id"] == case_id}
        for left, right in (("B0", "B1"), ("T1", "T2")):
            a, b = case[left], case[right]
            eligible = a["status"] == b["status"] == "SUCCESS"
            equivalent = a.get("retrieval_sha256") == b.get("retrieval_sha256") if eligible else None
            if eligible and left == "T1":
                equivalent = (
                    equivalent
                    and a["snapshot_sha256"] == b["snapshot_sha256"]
                    and a["pack"]["seed_child_ids"] == b["pack"]["seed_child_ids"]
                )
            equivalence.append(
                dict(case_id=case_id, pair=left + "/" + right, eligible=eligible, equivalent=equivalent)
            )
    complete = all(r["status"] == "SUCCESS" and not r.get("degraded") for r in rows)
    budgets = all(
        r["pack"]["serialized_chars"] <= 6400
        and r["pack"]["serialized_tokens"] <= 2048
        and len(r["pack"]["spans"]) <= 96
        for r in rows
        if r["arm"] == "B1" and r["status"] == "SUCCESS"
    )
    valid = all(
        r.get("physical_evidence_probes", {}).get("valid")
        == r.get("physical_evidence_probes", {}).get("total")
        for r in rows
        if r["status"] == "SUCCESS"
    )
    status = (
        "STAGE_D1_PHASE1_PASS"
        if complete and budgets and valid and all(e["equivalent"] for e in equivalence)
        else "STAGE_D1_PHASE1_BLOCKED"
    )
    output = dict(
        marker=status,
        manifest=manifest,
        by_split=summary,
        paired_evidence=comparisons,
        development_ablation=ablation,
        equivalence=equivalence,
        budget_checks_pass=budgets,
        physical_probe_checks_pass=valid,
        bad_cases=bad,
        development_revision_count=0,
        provider_calls=0,
        holdout_access="NOT_ACCESSED",
        candidate_frozen=False,
    )
    (args.directory / "summary.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        "# D1 Phase 1 retrieval/evidence",
        "",
        status,
        "",
        "No answer or judge execution; Development revision count 0; Holdout NOT_ACCESSED.",
        "",
        "Metrics below use source support groups and positive-Gold/evaluable denominators. No-positive-Gold cases are N/A. Full Dense/BM25/RRF/BGE stages and denominator counts are in summary.json.",
        "",
        "| Split | Arm | Success/total | BGE R@5 | R@10 | R@20 | R@40 | MRR@10 | nDCG@10 | Candidate aspects | Final aspects | Required sources |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def fmt(v):
        return "N/A" if v is None else f"{v:.4f}"

    for split, arms in summary.items():
        for arm, s in arms.items():
            r = s["retrieval"]["reranked"]
            values = (
                [r[f"recall@{k}"]["mean"] for k in (5, 10, 20, 40)]
                + [r[f"{m}@10"]["mean"] for m in ("mrr", "ndcg")]
                + [
                    s["evidence"]["rerank_input"]["required_aspect_coverage"]["mean"],
                    s["evidence"]["final"]["required_aspect_coverage"]["mean"],
                    s["evidence"]["final"]["required_source_coverage"]["mean"],
                ]
            )
            lines.append(
                f"| {split} | {arm} | {s['status_counts'].get('SUCCESS', 0)}/{s['total']} | "
                + " | ".join(map(fmt, values))
                + " |"
            )
    lines += [
        "",
        "Final answer Citation validity is N/A (no answers); physical evidence probes use product citation_for/resolve_span and are reported separately.",
        "",
        "## Paired required-aspect evidence coverage",
        "",
        "All differences are right minus left; case bootstrap seed 20260920, 10,000 resamples; missing metrics stay missing.",
    ]
    for split, pairs in comparisons.items():
        for pair, v in pairs.items():
            lines.append(f"- {split} {pair}: {v}")
    lines += ["", "## Development same-pool BGE minus RRF", ""]
    for metric, v in ablation.items():
        lines.append(f"- {metric}: {v}")
    lines += [
        "",
        "No semantic Safety pass, critical-answer assessment or final target freeze is claimed. Improvement requires the paired 95% lower bound > 0.",
        "",
        "Detailed errors, case-level coverage loss categories, pairing proofs and all denominators: summary.json; raw per-case outputs: *-B.json and *-T.json.",
    ]
    (args.directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            dict(marker=status, status_counts=dict(Counter(r["status"] for r in rows)), ablation=ablation)
        )
    )


if __name__ == "__main__":
    main()
