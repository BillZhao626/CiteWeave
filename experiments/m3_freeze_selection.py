"""Execute once AFTER Dev decisions and passing gates, BEFORE opening holdout results."""

import argparse
import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import EvalRunRow
from citeweave.evaluation.holdout import HOLDOUT_ID, HOLDOUT_SHA256, runtime_sources
from citeweave.profiles import query_profile
from citeweave.settings import ROOT
from citeweave.trace import runtime_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--gates-prefix", default="m3-revisit")
    args = parser.parse_args()
    query_profile(args.profile)
    target = ROOT / "evals/m3-revisit-selection.json"
    if target.exists():
        raise ValueError("selection_already_frozen")
    if not args.gates_prefix.replace("-", "").isalnum():
        raise ValueError("invalid_gates_prefix")
    gates_path = ROOT / "docs/reports" / (args.gates_prefix + "-gates.json")
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    if len(gates["results"]) != 9 or not all(gate["passed"] for gate in gates["results"]):
        raise ValueError("selection_requires_complete_passing_gates")
    journal = json.loads((ROOT / "docs/reports/m3-revisit/experiments.json").read_text(encoding="utf-8"))
    if any(e["decision"] not in {"KEEP", "REJECT"} for e in journal["experiments"]):
        raise ValueError("experiment_decisions_pending")
    with transaction() as db:
        if db.scalar(select(EvalRunRow.id).where(EvalRunRow.dataset_id == HOLDOUT_ID).limit(1)):
            raise ValueError("holdout_already_used")
    freeze = dict(
        status="FROZEN_BEFORE_HOLDOUT",
        at=datetime.now(timezone.utc).isoformat(),
        selected_profile=args.profile,
        reason=args.reason,
        decisions=journal["experiments"],
        config=runtime_config(args.profile),
        holdout_sha256=HOLDOUT_SHA256,
        runtime_sources=runtime_sources(),
        gates_report=gates_path.relative_to(ROOT).as_posix(),
        gates_sha256=hashlib.sha256(gates_path.read_bytes()).hexdigest(),
        limitations="AI-authored literal-source-checked Gold, not independent human annotation; historical RFC genre and possible model pretraining exposure",
    )
    raw = json.dumps(freeze, ensure_ascii=False, indent=2) + "\n"
    target.write_text(raw, encoding="utf-8")
    (ROOT / "docs/reports/m3-revisit/selection-freeze.json").write_text(raw, encoding="utf-8")
    print("Candidate selected and frozen before Holdout", args.profile)


if __name__ == "__main__":
    main()
