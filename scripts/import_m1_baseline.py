"""Import the immutable pre-M2 experiment into the product evaluation catalog; no new queries."""

import json
from uuid import UUID

from citeweave.db import transaction
from citeweave.domain import ChunkRow, EvalCaseRow, EvalRunRow
from citeweave.evaluation.reporting import markdown, refresh
from citeweave.settings import ROOT, settings


def main():
    identity = UUID((ROOT / ".runtime/evaluation/m1-baseline-id.txt").read_text())
    directory = ROOT / ".runtime/evaluation/runs" / str(identity)
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    with transaction() as db:
        if db.get(EvalRunRow, identity):
            print("Baseline already imported")
            return
        db.add(
            EvalRunRow(
                id=identity,
                workspace_id=settings().workspace_id,
                kb_id=UUID(metadata["kb_id"]),
                key="m1-baseline:" + str(identity),
                dataset_id="public-standards-v1",
                dataset_hash=metadata["dataset_hash"],
                split="all",
                status="COMPLETED",
                versions=metadata["versions"],
                runtime_config=metadata["config"],
            )
        )
        db.flush()
        for brief in metadata["cases"]:
            result = json.loads((directory / (brief["case_id"] + ".json")).read_text(encoding="utf-8"))
            selected = sorted(
                [c for c in result["candidates"] if c.get("final_evidence_rank")],
                key=lambda c: c["final_evidence_rank"],
            )
            result["selected_evidence"] = [
                dict(
                    label="E" + str(c["final_evidence_rank"]),
                    text=db.get(ChunkRow, UUID(c["candidate_id"])).text,
                )
                for c in selected
            ]
            db.add(
                EvalCaseRow(
                    eval_run_id=identity,
                    case_id=brief["case_id"],
                    status="COMPLETED",
                    query_run_id=UUID(brief["query_run_id"]),
                    result=result,
                )
            )
    summary = refresh(identity)
    (ROOT / "docs/reports/m2-m1-baseline.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "docs/reports/M2_M1_BASELINE.md").write_text(markdown(identity, summary), encoding="utf-8")
    print("Imported baseline", identity)


if __name__ == "__main__":
    main()
