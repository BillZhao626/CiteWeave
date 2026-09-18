"""Count recorded M3 evaluation spend without double-counting replayed source queries."""

import json
from decimal import Decimal

from citeweave.settings import ROOT


def main():
    folder = ROOT / "docs/reports"
    journal = json.loads((folder / "m3-experiments.json").read_text(encoding="utf-8"))
    identities = {e["run_id"] for e in journal["experiments"]}
    identities.update(e["run"] for e in journal["calibration"]["history"])
    identities.add(journal["selected_dev_verification_run"])
    formal = json.loads((folder / "m3-selected-test.json").read_text(encoding="utf-8"))
    identities.update([formal["baseline_id"], formal["candidate_id"]])
    queries, judges, runs = {}, [], []
    for identity in sorted(identities):
        artifact = json.loads(
            (ROOT / ".runtime/evaluation/runs" / identity / "artifact.json").read_text(encoding="utf-8")
        )
        replay = artifact["evaluation"]["runtime_config"].get("replay_source")
        cases = artifact["cases"]
        for case in cases:
            if not replay and case.get("query_run_id"):
                queries[case["query_run_id"]] = case["result"].get("estimated_yuan")
            judges.append(case.get("judge_estimated_yuan"))
        runs.append(
            dict(id=identity, replay_source=replay, query_cost_incremental=not bool(replay), cases=len(cases))
        )

    def total(values):
        return float(sum((Decimal(str(v)) for v in values if v is not None), Decimal(0)))

    clean_path = folder / "m3-clean-install.json"
    clean = json.loads(clean_path.read_text(encoding="utf-8")) if clean_path.exists() else {}
    smoke = clean.get("probe", {}).get("estimated_yuan")
    result = dict(
        scope="Nine M3 calibration/candidate/repeat/formal-Test EvalRuns; unique new query IDs only. Historical M2 replay-query costs excluded. Separate clean-smoke cost included when available; actual provider bill/account-external usage unavailable.",
        evaluations=runs,
        new_query_count=len(queries),
        query_estimated_yuan=total(queries.values()),
        query_unknown=sum(v is None for v in queries.values()),
        judge_cases=len(judges),
        judge_estimated_yuan=total(judges),
        judge_unavailable_count=sum(v is None for v in judges),
        clean_smoke_estimated_yuan=smoke,
        known_total_estimated_yuan=round(total(queries.values()) + total(judges) + (smoke or 0), 8),
        actual_charge="unavailable",
        currency="CNY",
        configured_monthly_budget_yuan=50,
    )
    (folder / "m3-cost.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "evaluations"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
