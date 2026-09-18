"""Compare two completed evaluations of the same split, dataset and Judge rubric."""

import argparse
import json
from uuid import UUID

from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, EvalRunRow
from citeweave.evaluation.comparison import compare
from citeweave.settings import ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=UUID, required=True)
    parser.add_argument("--candidate", type=UUID, required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if not args.name.replace("-", "").isalnum():
        raise ValueError("invalid_report_name")
    with transaction() as db:
        baseline, candidate = (db.get(EvalRunRow, i) for i in (args.baseline, args.candidate))
        if baseline.status != "COMPLETED" or candidate.status != "COMPLETED":
            raise ValueError("comparison_not_complete")
        cases = [
            list(db.scalars(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == i)))
            for i in (args.baseline, args.candidate)
        ]
    result = compare(baseline, candidate, *cases)
    (ROOT / "docs/reports" / (args.name + ".json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            dict(
                paired=result["paired"],
                regressions=result["new_regression_ids"],
                evidence=result["candidate"]["evidence"],
                answer=result["candidate"]["answer"],
                citation=result["candidate"]["citation"]["micro_grounded"],
                semantic=result["candidate"]["semantic_citation"],
            )
        )
    )


if __name__ == "__main__":
    main()
