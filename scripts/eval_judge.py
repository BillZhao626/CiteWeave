"""Judge saved answers, not re-run questions. Durable pre-call reservation prevents silent double billing."""

import argparse
import asyncio
import json
from uuid import UUID

from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow
from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.judge import assess_answer, reserve
from citeweave.evaluation.reporting import markdown, refresh
from citeweave.settings import ROOT


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-run", type=UUID, required=True)
    args = parser.parse_args()
    dataset, _ = load_dataset()
    specs = {c["case_id"]: c for c in dataset["cases"]}
    with transaction() as db:
        cases = list(
            db.scalars(
                select(EvalCaseRow)
                .where(EvalCaseRow.eval_run_id == args.eval_run)
                .order_by(EvalCaseRow.case_id)
            )
        )
    for case in cases:
        if case.judge:
            continue
        if case.judge_reserved_yuan:
            print(case.case_id, "prior_unknown_judge_not_reissued", flush=True)
            continue
        reserve(args.eval_run, case.case_id)
        judged = await assess_answer(specs[case.case_id], case.result)
        with transaction() as db:
            row = db.get(EvalCaseRow, (args.eval_run, case.case_id))
            row.judge, row.judge_estimated_yuan = judged, judged["estimated_yuan"]
        print(case.case_id, judged["status"], (judged.get("scores") or {}).get("verdict"), flush=True)
    summary = refresh(args.eval_run)
    directory = ROOT / ".runtime/evaluation/runs" / str(args.eval_run)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (directory / "report.md").write_text(markdown(args.eval_run, summary), encoding="utf-8")
    print("Judge report saved", args.eval_run, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
