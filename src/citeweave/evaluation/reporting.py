"""Reproducible aggregate report with visible denominators, failures and judge limitations."""

import json
from collections import Counter

from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, EvalRunRow, QueryRunRow
from citeweave.evaluation.attribution import attribute
from citeweave.evaluation.metrics import mean_defined, ranking_metrics


def aggregate(rows, query_costs=None, durable=False):
    results = [r.result for r in rows if r.result]
    value = dict(
        case_count=len(rows),
        assessed_count=len(results),
        unassessed_failed_count=sum(r.status == "FAILED" and not r.result for r in rows),
        query_status=dict(Counter(r.get("status", "UNAVAILABLE") for r in results)),
        case_status=dict(Counter(r.status for r in rows)),
        retrieval={},
        evidence={},
        citation={},
        answer={},
        limitations=[
            "Small shared-corpus benchmark; not general business accuracy.",
            "Dense/BM25 cross-document display uses RRF of per-version ranks; raw scores are not added.",
            "Citation precision/recall measure finite annotated gold overlap AFTER independent PDF grounding; alternate valid support can be absent from gold.",
            "LLM judgment is fallible; correctness is separate from refusal safety and exact quote validity.",
        ],
    )
    for stage in ("dense", "bm25", "rrf", "reranked"):
        value["retrieval"][stage] = {
            str(k): {
                metric: mean_defined(
                    [
                        r["assessment"]["retrieval"][stage][str(k)][metric]
                        if r["assessment"].get("metric_revision") == "source-support-v1"
                        else ranking_metrics(
                            r["assessment"]["stage_rankings"][stage], set(r["assessment"]["gold_ids"]), k
                        )[metric]
                        for r in results
                    ]
                )
                for metric in ("hit", "recall", "mrr", "ndcg")
            }
            for k in (5, 6, 10, 20, 40)
        }
    for key in ("initial", "rerank_input", "final"):
        value["evidence"][key] = mean_defined([r["assessment"]["evidence"][key] for r in results])
    for key in ("precision", "recall", "grounded_rate"):
        value["citation"][key] = mean_defined([r["assessment"]["citation"][key] for r in results])
    checks = [c for r in results for c in r["assessment"]["citation"]["checks"]]
    value["citation"]["micro_grounded"] = dict(passed=sum(c["grounded"] for c in checks), count=len(checks))
    for key in ("correctness", "completeness", "faithfulness", "relevancy", "refusal_correctness"):
        value["answer"][key] = mean_defined(
            [
                (r.judge.get("scores") or {}).get(
                    key, 0 if not durable and r.status == "FAILED" and key != "faithfulness" else None
                )
                for r in rows
            ]
        )
    value["judge_status"] = dict(Counter(r.judge.get("status", "PENDING") for r in rows))
    if durable:
        scored = [r for r in rows if (r.judge.get("scores") or {}).get("correctness") is not None]
        value["quality_accounting"] = dict(
            total_cases=len(rows),
            semantic_evaluable=len(scored),
            missing_judgment=len(rows) - len(scored),
            query_completed=sum(r.result.get("status") == "COMPLETED" for r in rows),
            end_to_end_correctness=sum((r.judge.get("scores") or {}).get("correctness", 0) or 0 for r in rows)
            / len(rows)
            if rows
            else None,
            end_to_end_note="Missing judgment contributes no demonstrated correctness; it is not a semantic zero label.",
            conditional_quality=value["answer"],
        )
        for key in ("required_aspect_coverage", "required_source_coverage"):
            value["evidence"][key] = {
                phase: mean_defined(
                    [r["assessment"].get("support_coverage", {}).get(phase, {}).get(key) for r in results]
                )
                for phase in ("initial", "final")
            }
        for answerable, name in ((True, "answerable_refusal"), (False, "unanswerable_correct_refusal")):
            eligible = [r for r in results if r.get("answerable") is answerable]
            value["answer"][name] = dict(
                count=sum((r.get("answer") or {}).get("text") == "证据不足，无法回答。" for r in eligible),
                denominator=len(eligible),
            )
    claims = [c for r in rows for c in (r.judge.get("scores") or {}).get("claims", [])]
    value["semantic_citation"] = dict(
        method="fallible_judge_claim_to_cited_evidence",
        claim_count=len(claims),
        support=mean_defined([c["support"] for c in claims]),
        fully_supported=sum(c["support"] == 1 for c in claims),
        unsupported=sum(c["support"] == 0 for c in claims),
        cited_claim_fraction=sum(bool(c["evidence_labels"]) for c in claims) / len(claims)
        if claims
        else None,
        limitation="Fallible rubric-versioned factual units (v4 uses original sentence units); finite-gold citation precision/recall and PDF grounding are separate metrics.",
    )
    value["human_review"] = dict(
        reviewed=sum(bool(r.human_review) for r in rows),
        comparisons=[
            dict(
                case_id=r.case_id,
                human=r.human_review,
                judge_verdict=(r.judge.get("scores") or {}).get("verdict"),
                agrees=r.human_review.get("verdict") == (r.judge.get("scores") or {}).get("verdict"),
            )
            for r in rows
            if r.human_review
        ],
    )
    costs = [r.get("estimated_yuan") for r in results]
    if query_costs is not None:
        costs = list(query_costs.values())
    judge_costs = [
        float(r.judge_estimated_yuan) if r.judge_estimated_yuan is not None else None for r in rows
    ]
    value["cost"] = dict(
        query_known_estimated_yuan=sum(c for c in costs if c is not None),
        query_unknown=sum(c is None for c in costs),
        judge_known_estimated_yuan=sum(c for c in judge_costs if c is not None),
        judge_unknown=sum(
            c is None and bool(r.judge_reserved_yuan) for c, r in zip(judge_costs, rows, strict=True)
        ),
        actual_charge="unavailable",
    )
    latencies = sorted(r["latency_ms"] for r in results if "latency_ms" in r)
    value["latency_ms"] = dict(
        p50=latencies[len(latencies) // 2] if latencies else None,
        p95=latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None,
    )
    bad = []
    for row in rows:
        if not row.result:
            if row.status == "FAILED":
                bad.append(
                    dict(
                        case_id=row.case_id,
                        reasons=["assessment_failure:" + str(row.judge.get("error_code"))],
                    )
                )
            continue
        ev = row.result["assessment"]["evidence"]
        reasons = []
        if row.result["status"] != "COMPLETED":
            reasons.append("request_failure:" + str(row.result.get("error_code")))
        for phase in ("initial", "rerank_input", "final"):
            if ev[phase] is not None and ev[phase] < 1:
                reasons.append("incomplete_gold_at_" + phase)
        if (row.judge.get("scores") or {}).get("verdict") != "correct_complete":
            reasons.append("answer_partial_incorrect_or_unreviewed")
        if reasons:
            bad.append(dict(case_id=row.case_id, reasons=reasons))
    value["bad_cases"] = bad
    value["stage_attribution"] = [
        attribute(
            dict(case_id=r.case_id, result=r.result, judge=r.judge, human_review=r.human_review),
            r.result["answerable"],
        )
        for r in rows
        if r.result and "answerable" in r.result
    ]
    return value


def refresh(eval_id):
    with transaction() as db:
        row = db.get(EvalRunRow, eval_id)
        cases = list(
            db.scalars(
                select(EvalCaseRow).where(EvalCaseRow.eval_run_id == eval_id).order_by(EvalCaseRow.case_id)
            )
        )
        costs = dict(
            db.execute(
                select(QueryRunRow.id, QueryRunRow.estimated_yuan).where(
                    QueryRunRow.id.in_([case.query_run_id for case in cases if case.query_run_id])
                )
            ).all()
        )
        row.summary = aggregate(
            cases,
            {k: float(v) if v is not None else None for k, v in costs.items()},
            durable=row.runtime_policy == "eval-durable-v1",
        )
        return row.summary


def markdown(identity, summary):
    def metric(value):
        return "unavailable" if value["mean"] is None else f"{value['mean']:.4f} (n={value['denominator']})"

    lines = [
        f"# Evaluation {identity}",
        "",
        f"Cases: {summary['case_count']}; query status: {summary['query_status']}",
        "",
        "| Stage @20 | Recall | MRR | nDCG |",
        "|---|---:|---:|---:|",
    ]
    for stage, values in summary["retrieval"].items():
        lines.append(
            "| "
            + stage
            + " | "
            + " | ".join(metric(values["20"][m]) for m in ("recall", "mrr", "ndcg"))
            + " |"
        )
    lines += [
        "",
        "Evidence coverage: " + json.dumps(summary["evidence"]),
        "",
        "Citation: " + json.dumps(summary["citation"]),
        "",
        "Answer rubric: " + json.dumps(summary["answer"]),
        "",
        "Judge status: " + json.dumps(summary["judge_status"]),
        "Human review: " + json.dumps(summary["human_review"], ensure_ascii=False),
        "",
        "Cost (estimated only): " + json.dumps(summary["cost"]),
        "",
        "Latency: " + json.dumps(summary["latency_ms"]),
        "",
        *["- " + note for note in summary["limitations"]],
        "",
        "## Bad cases",
        "",
        *[f"- {c['case_id']}: {', '.join(c['reasons'])}" for c in summary["bad_cases"]],
    ]
    return "\n".join(lines) + "\n"
