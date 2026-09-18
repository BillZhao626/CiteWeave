"""Summarize preserved run artifacts; never rerun or overwrite Judge results."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean

from citeweave.evaluation.attribution import attribute
from citeweave.settings import ROOT

FOLDER = ROOT / "docs/reports/m3-revisit"


def average(values):
    values = [v for v in values if v is not None]
    return dict(mean=mean(values) if values else None, denominator=len(values))


def summarize(identity):
    path = ROOT / ".runtime/evaluation/runs" / identity / "artifact.json"
    raw = path.read_bytes()
    artifact = json.loads(raw)
    evaluation, cases = artifact["evaluation"], artifact["cases"]
    summary = evaluation["summary"]
    assert evaluation["status"] == "COMPLETED"
    by_type = defaultdict(list)
    seeds, outcomes, attribution = [], [], Counter()
    for case in cases:
        result = case["result"]
        by_type[result["question_type"]].append(case)
        assessment = result["assessment"]
        gold = set(assessment["gold_ids"])
        coverage = len(set(assessment["stage_rankings"]["reranked"][:6]) & gold) / len(gold) if gold else None
        seeds.append(coverage)
        attribution.update(attribute(case, result["answerable"])["categories"])
        outcomes.append(
            dict(
                case_id=case["case_id"],
                question_type=result["question_type"],
                evidence=assessment["evidence"],
                seed_coverage=coverage,
                status=result["status"],
                error_code=result.get("error_code"),
                judge_status=case["judge"].get("status"),
                correctness=(case["judge"].get("scores") or {}).get("correctness"),
                context_spans=len(result["selected_evidence"]),
                context_chars=sum(len(e["text"]) for e in result["selected_evidence"]),
            )
        )
    return dict(
        eval_run_id=identity,
        artifact_sha256=hashlib.sha256(raw).hexdigest(),
        dataset_hash=evaluation["dataset_hash"],
        split=evaluation["split"],
        profile=evaluation["runtime_config"]["query_profile"],
        created_at=evaluation["created_at"],
        config=evaluation["runtime_config"],
        funnel=dict(summary["evidence"], six_seed=average(seeds)),
        ranking=summary["retrieval"],
        answer=summary["answer"],
        citation=summary["citation"],
        semantic_citation=summary["semantic_citation"],
        cost=summary["cost"],
        latency_ms=summary["latency_ms"],
        query_status=summary["query_status"],
        nonexclusive_attribution=dict(attribution),
        cases=outcomes,
        by_question_type={
            name: dict(
                count=len(rows),
                correctness=average([(r["judge"].get("scores") or {}).get("correctness") for r in rows]),
                final_coverage=average([r["result"]["assessment"]["evidence"]["final"] for r in rows]),
            )
            for name, rows in by_type.items()
        },
    )


def main():
    journal = json.loads((FOLDER / "experiments.json").read_text(encoding="utf-8"))
    runs = dict(
        historical_c2_dev="b66bab34-b63b-46fe-b33e-f0f116cf65ba", fresh_c2_dev=journal["fresh_baseline_dev"]
    )
    for experiment in journal["experiments"]:
        for key in ("run_id", "repeat_run_id", "e5_control_run_id"):
            if experiment.get(key):
                runs[experiment["id"] + "_" + key] = experiment[key]
    for name, identity in journal.get("final_runs", {}).items():
        runs[name] = identity
    values = {name: summarize(identity) for name, identity in runs.items()}
    result = dict(
        at=datetime.now(timezone.utc).isoformat(),
        runs=values,
        notes=[
            "Evidence means use answerable Gold denominators; initial is the union of retrieved branches, candidate is actual reranker input, six_seed precedes bounded context.",
            "Dense/BM25 display metrics combine per-version ranks by RRF; raw cross-version scores are not summed.",
            "All stage attributions are non-exclusive observations; incomplete finite Gold does not prove semantic insufficiency or generation blame.",
            "Judge metrics remain unchanged. Separate source-context audits can reveal false-positive judgments and block promotion.",
            "Latencies here follow the artifact aggregator (upper middle p50); controlled paired comparison reports can use a different median convention.",
        ],
    )
    (FOLDER / "quality-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                name: dict(
                    funnel=r["funnel"],
                    correctness=r["answer"]["correctness"],
                    physical=r["citation"]["micro_grounded"],
                    latency_ms=r["latency_ms"],
                )
                for name, r in values.items()
            }
        )
    )


if __name__ == "__main__":
    main()
