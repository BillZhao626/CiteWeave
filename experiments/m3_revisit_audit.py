"""Read-only baseline audit; new evidence goes in a separate M3 report directory."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import ChunkRow
from citeweave.settings import ROOT

REPORT = ROOT / "docs/reports/m3-revisit"
DEV = "b66bab34-b63b-46fe-b33e-f0f116cf65ba"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    REPORT.mkdir(exist_ok=True)
    manifest = read(ROOT / "docs/reports/m3-manifest.json")
    receipt = read(ROOT / ".runtime/m3-release-receipt.json")
    archive = Path(receipt["archive"])
    assert sha(archive) == receipt["sha256"]
    baseline_source = archive.parent / "source"
    assert all(sha(baseline_source / n) == h for n, h in manifest["sha256"].items())
    snapshot = REPORT / "baseline-preservation.json"
    if not snapshot.exists():
        protected = {n: h for n, h in manifest["sha256"].items() if n.startswith(("docs/reports/", "evals/"))}
        protected["docs/reports/m3-manifest.json"] = sha(ROOT / "docs/reports/m3-manifest.json")
        for identity in (DEV, "d2c953cc-e6b2-4f65-8fe4-1c650a4f6f4a", "a32e838b-b5c2-4a6c-b8e7-7aabf2e8f944"):
            name = f".runtime/evaluation/runs/{identity}/artifact.json"
            protected[name] = sha(ROOT / name)
        snapshot.write_text(
            json.dumps(
                dict(
                    at=datetime.now(timezone.utc).isoformat(),
                    archive=str(archive),
                    archive_sha256=receipt["sha256"],
                    protected=protected,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    assert all(sha(ROOT / n) == h for n, h in read(snapshot)["protected"].items())
    artifact = read(ROOT / f".runtime/evaluation/runs/{DEV}/artifact.json")
    compare = read(ROOT / "docs/reports/m3-selected-dev.json")
    versions = artifact["evaluation"]["versions"]
    with transaction() as db:
        chunks = list(
            db.scalars(select(ChunkRow).where(ChunkRow.version_id.in_([UUID(v) for v in versions.values()])))
        )
    blocks = {(str(c.version_id), c.block["block_id"]): c.block for c in chunks}
    print(
        json.dumps(
            dict(
                artifact_keys=list(artifact),
                case_keys=list(artifact["cases"][0]),
                result_keys=list(artifact["cases"][0]["result"]),
            ),
            ensure_ascii=False,
        )
    )
    rows = []
    types = defaultdict(list)
    for case in artifact["cases"]:
        result = case["result"]["assessment"]
        stages = result["stage_rankings"]
        gold = set(result["gold_ids"])
        initial = result["evidence"]["initial"]
        rrf = stages["rrf"]
        row = dict(
            case_id=case["case_id"],
            gold_count=len(gold),
            coverage=result["evidence"],
            gold_rrf_ranks=[rrf.index(g) + 1 for g in gold if g in rrf],
            lost_at_20=[g for g in gold if g in rrf[20:]],
            gold_not_initial=[g for g in gold if g not in rrf],
        )
        rows.append(row)
        types[str(case.get("question_type", "see_dataset"))].append(initial)
    summary = dict(
        at=datetime.now(timezone.utc).isoformat(),
        baseline_eval=DEV,
        dataset_sha256=compare["dataset_hash"],
        versions=versions,
        evidence=compare["candidate"]["evidence"],
        paired_test=read(ROOT / "docs/reports/m3-selected-test.json")["paired"],
        attribution=read(ROOT / "docs/reports/m3-dev-attribution.json")["nonexclusive_counts"],
        parser=dict(
            block_count=len(blocks),
            chunk_count=len(chunks),
            block_name_examples=sorted({b["block_id"] for b in blocks.values()})[:4],
            maximum_block_chars=max(len(b["text"]) for b in blocks.values()),
            blocks_over_160=sum(len(b["text"]) > 160 for b in blocks.values()),
            child_counts_per_block=dict(
                Counter(
                    sum(c.block["block_id"] == k[1] and str(c.version_id) == k[0] for c in chunks)
                    for k in blocks
                )
            ),
        ),
        cases=rows,
        interpretation="Existing Block is a glyph line; most parents equal a child. C2 query-time neighbors are not formal Parent-Child. RRF merges per-version branches then applies a global 20 cutoff; ranks beyond 20 cannot be rescued by reranking.",
    )
    (REPORT / "baseline-audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in {"cases", "versions", "paired_test"}},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
