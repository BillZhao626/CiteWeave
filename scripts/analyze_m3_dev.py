"""Read only Dev from the historical artifact; derive stage losses without Test tuning."""

import json
from collections import Counter
from uuid import UUID

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, QueryRunRow
from citeweave.evaluation.attribution import Category, attribute
from citeweave.evaluation.dataset import load_dataset
from citeweave.settings import ROOT


def main():
    baseline = "a32e838b-b5c2-4a6c-b8e7-7aabf2e8f944"
    artifact = json.loads(
        (ROOT / ".runtime/evaluation/runs" / baseline / "artifact.json").read_text(encoding="utf-8")
    )
    dataset, digest = load_dataset()
    specs = {c["case_id"]: c for c in dataset["cases"] if c["split"] == "dev"}
    # These two sufficiency findings are explicitly in the submitted review reasons.
    reviewed_sufficient = {"cw-public-003", "cw-public-007"}
    cases = []
    with transaction() as db:
        for case in artifact["cases"]:
            if case["case_id"] not in specs:
                continue
            row = db.get(EvalCaseRow, (UUID(baseline), case["case_id"]))
            case["human_review"] = row.human_review
            finding = attribute(
                case,
                specs[case["case_id"]]["answerable"],
                True if case["case_id"] in reviewed_sufficient else None,
            )
            finding["review_reason"] = row.human_review["reason"]
            run = db.get(QueryRunRow, row.query_run_id)
            top = sorted(run.candidates, key=lambda c: c["rrf_rank"])[:20]
            unique = {(c["document_version_id"], " ".join(c["text"].split())) for c in top}
            finding["exact_duplicate_text_in_rrf_top20"] = len(top) - len(unique)
            cases.append(finding)
    counts = Counter(category for case in cases for category in case["categories"])
    report = dict(
        dataset_hash=digest,
        source_eval_run_id=baseline,
        split="dev",
        cases=cases,
        nonexclusive_counts={category: counts[category] for category in Category},
    )
    (ROOT / "docs/reports/m3-dev-attribution.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["nonexclusive_counts"]))


if __name__ == "__main__":
    main()
