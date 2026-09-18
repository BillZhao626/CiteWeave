"""Export a completed frozen comparison from durable facts; never calls a model."""

import argparse
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, EvalRunRow, QueryRunRow
from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.reporting import aggregate, markdown
from citeweave.settings import ROOT


def distribution(values):
    ordered = sorted(values)
    return dict(
        n=len(ordered),
        median=statistics.median(ordered) if ordered else None,
        p95=ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else None,
    )


def collect(identity, specs, digest):
    with transaction() as db:
        run = db.get(EvalRunRow, identity)
        assert run.status == "COMPLETED" and run.dataset_hash == digest
        cases = list(db.scalars(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == identity)))
        queries = list(
            db.scalars(select(QueryRunRow).where(QueryRunRow.id.in_([c.query_run_id for c in cases])))
        )
    assert len(cases) == len(specs) == 48
    query_by_id = {q.id: q for q in queries}
    splits = {}
    for split in ("all", "dev", "test"):
        subset = [c for c in cases if split == "all" or specs[c.case_id]["split"] == split]
        costs = {
            c.query_run_id: float(q.estimated_yuan) if q.estimated_yuan is not None else None
            for c in subset
            if (q := query_by_id.get(c.query_run_id))
        }
        splits[split] = aggregate(subset, costs)
    stages, shares = defaultdict(list), []
    durations = []
    for query in queries:
        total = (query.completed_at - query.created_at).total_seconds() * 1000 if query.completed_at else None
        if total is not None:
            durations.append(total)
        for stage in query.stages:
            if stage.get("latency_ms") is not None:
                stages[stage["name"]].append(stage["latency_ms"])
                if stage["name"] == "query_embedding" and total:
                    shares.append(stage["latency_ms"] / total)
    return dict(
        id=str(identity),
        created_at=run.created_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        versions=run.versions,
        runtime_config=run.runtime_config,
        splits=splits,
        query_wall_ms=distribution(durations),
        stage_ms={key: distribution(value) for key, value in stages.items()},
        query_embedding_fraction=distribution(shares),
        query_calls=dict(Counter(c["upstream"] for q in queries for c in q.calls)),
        extra_attempts=sum(c.get("attempt", 1) > 1 for q in queries for c in q.calls),
        error_codes=dict(Counter(q.error_code for q in queries if q.error_code)),
        answer_verdicts=dict(Counter((c.judge.get("scores") or {}).get("verdict", "N/A") for c in cases)),
        per_case_evidence={c.case_id: c.result.get("assessment", {}).get("evidence") for c in cases},
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=UUID, required=True)
    parser.add_argument("--candidate", type=UUID, required=True)
    args = parser.parse_args()
    dataset, digest = load_dataset()
    specs = {c["case_id"]: c for c in dataset["cases"]}
    baseline = collect(args.baseline, specs, digest)
    candidate = collect(args.candidate, specs, digest)
    old = baseline["runtime_config"]
    new = candidate["runtime_config"]
    common = set(old) & set(new) - {"source_code", "index_bindings"}
    differences = {k: [old[k], new[k]] for k in sorted(common) if old[k] != new[k]}
    comparison = dict(
        at=datetime.now(timezone.utc).isoformat(),
        dataset_hash=digest,
        distinct_questions=len({c["question"] for c in dataset["cases"]}),
        baseline=baseline,
        candidate=candidate,
        same_versions=baseline["versions"] == candidate["versions"],
        common_runtime_config_differences=differences,
        changed_evidence_cases=[
            key for key in specs if baseline["per_case_evidence"][key] != candidate["per_case_evidence"][key]
        ],
        limits=[
            "Single run per configuration; stochastic answer/Judge differences are not an improvement claim.",
            "M1 Windows harness latency and M2 container worker latency are not controlled performance comparisons.",
            "M2 query_wall_ms uses persisted QueryRun timestamps; stage timings include instrumentation overhead.",
            "No candidate human review is inferred from baseline human labels.",
        ],
    )
    folder = ROOT / "docs/reports"
    (folder / "m2-comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for label, values in (("baseline", baseline), ("candidate", candidate)):
        for split, summary in values["splits"].items():
            (folder / f"m2-{label}-{split}.md").write_text(
                markdown(f"{values['id']} / {split}", summary), encoding="utf-8"
            )
    print(
        json.dumps(
            {k: v for k, v in comparison.items() if k not in {"baseline", "candidate"}}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
