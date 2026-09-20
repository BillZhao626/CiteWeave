"""Verify saved non-dataset readiness draws without repeating retrieval or BGE."""

import argparse
import json
import subprocess
from pathlib import Path
from uuid import UUID

from d1_phase1 import hashed, save
from prepare_d1_legacy import STRUCTURAL_DB, use_database
from sqlalchemy.engine import make_url

from citeweave.context_tokens import ContextTokenizer
from citeweave.db import transaction
from citeweave.domain import QueryRunRow
from citeweave.evaluation.arms import structural_pack
from citeweave.model_client import ModelGateway
from citeweave.query_evidence import StructuralCandidate, StructuralSnapshot
from citeweave.settings import ROOT, settings
from citeweave.structural_repository import StructuralRepository

ACCEPTED = "6797a4c8500204b8a0d4e8e6640d44feafb840e3"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    rows = json.loads((args.directory / "results.json").read_text(encoding="utf-8"))
    assert len(rows) == 8 and all(r["status"] == "SUCCESS" for r in rows)
    old = subprocess.check_output(
        ["git", "show", ACCEPTED + ":src/citeweave/evidence_selection.py"], cwd=ROOT
    )
    namespace = {}
    exec(compile(old, "accepted-stage-c-evidence-selection", "exec"), namespace)
    use_database(make_url(settings().db_url()), STRUCTURAL_DB)
    proofs = []
    for identity in sorted({r["case_id"] for r in rows}):
        group = {r["arm"]: r for r in rows if r["case_id"] == identity}
        assert group["B0"]["retrieval_sha256"] == group["B1"]["retrieval_sha256"]
        assert group["T1"]["retrieval_sha256"] == group["T2"]["retrieval_sha256"]
        assert group["T1"]["snapshot_sha256"] == group["T2"]["snapshot_sha256"]
        assert group["B0"]["pack"]["policy"] == "legacy-m3-context-v1"
        b1 = group["B1"]["pack"]
        assert b1["serialized_chars"] <= 6400 and b1["serialized_tokens"] <= 2048 and len(b1["spans"]) <= 96
        with transaction() as db:
            run = db.get(QueryRunRow, UUID(group["T1"]["run_id"]))
        snapshot = StructuralSnapshot.model_validate(run.structural_snapshot)
        repo = StructuralRepository(snapshot)
        repo.builds()
        candidates = {c["candidate_id"]: StructuralCandidate.model_validate(c) for c in run.candidates}
        for c in candidates.values():
            c.seed_rank, c.selection_reason = None, "outside_pool"
        pool = [i for i, c in candidates.items() if c.bge]
        ordered = sorted(pool, key=lambda i: candidates[i].bge.output_rank)
        assert len(pool) == 20 and {candidates[i].bge.input_rank for i in pool} == set(range(1, 21))
        children = repo.children(pool)
        atoms = repo.atoms({i for c in children.values() for i in c["span_ids"]})
        inputs = dict(
            ordered=ordered,
            candidates=candidates,
            children=children,
            repository=repo,
            tokenizer=ContextTokenizer(ModelGateway()),
            degraded=None,
            reason=None,
            seed_atoms=atoms,
        )
        _, original = namespace["select_evidence"](**inputs)
        assert original.model_dump(mode="json") == group["T2"]["pack"]
        _, rrf_pack, _ = structural_pack(inputs, parent_expansion=False, rrf_only=True)
        assert rrf_pack.degraded is None and rrf_pack.added_chars == 0
        proofs.append(
            dict(
                case_id=identity,
                B0_B1_identical=True,
                T1_T2_identical=True,
                accepted_T2_exact_pack_equal=True,
                BGE_healthy=True,
                pool_count=20,
                same_rrf_bge_pool_sha256=hashed(sorted(pool)),
                RRF_evidence_pack=rrf_pack.model_dump(mode="json"),
                B1_chars=b1["serialized_chars"],
                B1_tokens=b1["serialized_tokens"],
                B1_spans=len(b1["spans"]),
            )
        )
    save(
        args.directory / "paired-proof.json",
        dict(
            status="PASS",
            proofs=proofs,
            retrieval_reexecuted=False,
            real_BGE_reexecuted=False,
            provider_calls=0,
            accepted_commit=ACCEPTED,
        ),
    )
    print(
        json.dumps(dict(status="PASS", real_queries=2, accepted_T2_exact_match=True, same_pool_ablation=True))
    )


if __name__ == "__main__":
    main()
