"""Validate both submitted files, the frozen dataset and M2 run; import once."""

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, EvalRunRow
from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.human import agreement, validate_reviews
from citeweave.evaluation.reporting import refresh
from citeweave.settings import ROOT

BASELINE = "a32e838b-b5c2-4a6c-b8e7-7aabf2e8f944"


def main():
    folder = ROOT / "evals/reviews/m2-dev-24"
    labels = folder / "M2_Dev24_人工复核_标签.json"
    prose = folder / "M2_Dev24_人工复核_已填写.md"
    source = ROOT / ".runtime/evaluation/runs" / BASELINE / "artifact.json"
    artifact = json.loads(source.read_text(encoding="utf-8"))
    document = json.loads(labels.read_text(encoding="utf-8"))
    dataset, digest = load_dataset()
    reviews = validate_reviews(document, prose.read_text(encoding="utf-8"), dataset, digest, artifact)
    provenance = dict(
        method="owner_submitted_ai_assisted_material_review",
        source_provenance=document["provenance"],
        dataset_hash=digest,
        source_eval_run_id=BASELINE,
        source_artifact_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        source_files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (labels, prose)},
    )
    with transaction() as db:
        run = db.get(EvalRunRow, UUID(BASELINE))
        if run.dataset_hash != digest or run.status != "COMPLETED":
            raise ValueError("review_database_run_mismatch")
        for identity, review in reviews.items():
            row = db.get(EvalCaseRow, (run.id, identity))
            saved = next(c for c in artifact["cases"] if c["case_id"] == identity)
            if not row or str(row.query_run_id) != saved["query_run_id"] or row.result != saved["result"]:
                raise ValueError("review_database_case_mismatch")
            value = dict(review, **provenance)
            if row.human_review:
                existing = {k: v for k, v in row.human_review.items() if k != "recorded_at"}
                if existing != value:
                    raise ValueError("review_overwrite_forbidden")
            else:
                row.human_review = dict(value, recorded_at=datetime.now(timezone.utc).isoformat())
            saved["human_review"] = row.human_review
    refresh(UUID(BASELINE))
    report = dict(provenance, **agreement([c for c in artifact["cases"] if c["case_id"] in reviews]))
    output = ROOT / "docs/reports/m3-human-judge-v1.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {k: report[k] for k in ("agree", "count", "rate", "distribution", "disagreement_ids")},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
