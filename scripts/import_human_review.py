"""Import only the project owner's explicit recorded review; do not fabricate human labels."""

import json
from datetime import datetime, timezone
from uuid import UUID

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow
from citeweave.evaluation.reporting import refresh
from citeweave.settings import ROOT


def main():
    document = json.loads((ROOT / "evals/reviews/m1-baseline-human.json").read_text(encoding="utf-8"))
    identity = UUID(document["eval_run_id"])
    with transaction() as db:
        for case in document["cases"]:
            row = db.get(EvalCaseRow, (identity, case["case_id"]))
            row.human_review = dict(
                case,
                reviewer=document["reviewer"],
                source=document["source"],
                method=document["method"],
                recorded_at=datetime.now(timezone.utc).isoformat(),
            )
    refresh(identity)
    print("Imported 3 explicit owner reviews")


if __name__ == "__main__":
    main()
