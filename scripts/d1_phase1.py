"""Durable, provider-free visible arm execution using product retrievers/assessor."""

import argparse
import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from prepare_d1_legacy import LEGACY_DB, STRUCTURAL_DB, use_database
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from citeweave.answering import citation_for
from citeweave.context_tokens import ContextTokenizer
from citeweave.db import transaction
from citeweave.domain import ChildSpanRow, KnowledgeBaseRow, QueryRunRow, VersionRow
from citeweave.evaluation.arms import (
    ARM_REVISION,
    ARMS,
    budget_legacy,
    legacy_pack,
    retrieval_identity,
    structural_pack,
)
from citeweave.evaluation.assessment import Assessor
from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.service import branches_from_run
from citeweave.evaluation.support import group_ranking
from citeweave.evidence import digest
from citeweave.hybrid import HybridRetriever
from citeweave.model_client import ModelGateway
from citeweave.schemas import QueryCreate
from citeweave.settings import ROOT, settings
from citeweave.structural_repository import capture
from citeweave.structural_retrieval import StructuralRetriever
from citeweave.trace import RunTrace, bounded_stage, current_trace, runtime_config


def hashed(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def save(path, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(raw, encoding="utf-8")
    temporary.replace(path)


def source_identity():
    return dict(
        commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        tree=subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT).decode().strip(),
        dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()),
    )


def new_run(arm, case, batch, versions, source, shared=None, snapshot=None):
    profile = "m3-context" if arm.startswith("B") else "telecom-structural-v1"
    config = dict(
        runtime_config(profile),
        evaluation_arm=arm,
        arm_revision=ARM_REVISION,
        arm_policy=ARMS[arm],
        source=source,
        case_id=case["case_id"],
        phase="retrieval_only",
        shared_retrieval_run=shared,
        provider_calls_allowed=False,
    )
    with transaction() as db:
        run = QueryRunRow(
            id=uuid4(),
            owner=uuid4(),
            fence=1,
            workspace_id=settings().workspace_id,
            kb_id=versions[0].kb_id,
            key=f"d1:{batch}:{case['case_id']}:{arm}",
            fingerprint=hashed(config),
            question=case["question"],
            runtime_policy="query-owned-v1",
            absolute_deadline=db.scalar(select(func.clock_timestamp()))
            + timedelta(seconds=60 if arm.startswith("T") else 45),
            versions=[str(v.id) for v in versions],
            index_bindings={str(v.id): v.index_collection for v in versions},
            structural_snapshot=snapshot,
            runtime_config=config,
            reserved_yuan=0,
            estimated_yuan=0,
        )
        db.add(run)
    return run


def finish(run, candidates=None, pack=None, error=None):
    # Like benchmarks/retrieval.py, never fabricate a completed answer QueryRun.
    with transaction() as db:
        row = db.get(QueryRunRow, run.id)
        row.status, row.error_code = "FAILED", error or "evaluation_retrieval_only"
        row.candidates, row.evidence_pack = candidates or [], pack
        row.completed_at = db.scalar(select(func.clock_timestamp()))
        row.runtime_config = dict(row.runtime_config, retrieval_status="FAILED" if error else "SUCCESS")
    return row


def result(case, arm, row, chunks, candidates, pack, versions, assess):
    physical = []
    for n, chunk in enumerate(chunks, 1):
        try:
            citation_for(chunk, f"E{n}")
            physical.append(True)
        except ValueError:
            physical.append(False)
    value = dict(
        case_id=case["case_id"],
        split=case.get("split", "readiness"),
        arm=arm,
        run_id=str(row.id),
        shared_retrieval_run=row.runtime_config["shared_retrieval_run"],
        status="SUCCESS",
        degraded=bool(pack.get("degraded")),
        evidence_policy=pack.get("policy", ARMS[arm]["evidence"]),
        retrieval_sha256=hashed(retrieval_identity(candidates)),
        candidates=candidates,
        pack=pack,
        physical_evidence_probes=dict(valid=sum(physical), total=len(physical)),
        final_answer_citation_validity=None,
        provider_calls=0,
    )
    if assess:
        assessor = Assessor(settings().workspace_id, {v["source_id"]: v["version_id"] for v in versions})
        value["assessment"] = assessor.assess(case, row.id, branches_from_run(row), candidates, None)
        # Reuse accepted support-group ranking for SAME-pool RRF attribution.
        if arm == "T1" and case["split"] == "dev":
            reverse = {v["version_id"]: v["source_id"] for v in versions}
            atoms = {
                str(c.id): dict(
                    source_id=reverse[str(c.version_id)],
                    block_id=c.block["block_id"],
                    start_offset=c.evidence["start_offset"],
                    end_offset=c.evidence["end_offset"],
                )
                for c in assessor.chunks
            }
            projection = {}
            with transaction() as db:
                for m in db.scalars(
                    select(ChildSpanRow).where(
                        ChildSpanRow.child_id.in_([UUID(c["candidate_id"]) for c in candidates])
                    )
                ):
                    projection.setdefault(str(m.child_id), []).append(atoms[str(m.evidence_id)])
            pool = [c for c in candidates if c.get("bge")]
            rrf = [c["candidate_id"] for c in sorted(pool, key=lambda c: c["rrf_rank"])]
            bge = [c["candidate_id"] for c in sorted(pool, key=lambda c: c["bge"]["output_rank"])]
            assert set(rrf) == set(bge)
            value["ablation"] = dict(
                pool=rrf,
                pool_sha256=hashed(sorted(rrf)),
                bge_order=bge,
                rrf={
                    str(k): group_ranking(rrf, projection, case["support_groups"], k) for k in (5, 10, 20, 40)
                },
                bge={
                    str(k): group_ranking(bge, projection, case["support_groups"], k) for k in (5, 10, 20, 40)
                },
            )
    return value


def execute_pair(base, family, case, batch, source, dataset, assess):
    use_database(base, LEGACY_DB if family == "B" else STRUCTURAL_DB)
    with transaction() as db:
        versions = list(
            db.scalars(select(VersionRow).where(VersionRow.status == "READY").order_by(VersionRow.id))
        )
    with transaction() as db:
        workspace = db.get(KnowledgeBaseRow, versions[0].kb_id).workspace_id
    os.environ["CW_WORKSPACE_ID"] = str(workspace)
    settings.cache_clear()
    source_map = {s["sha256"]: s["source_id"] for s in dataset["sources"]}
    assert {v.source_sha256 for v in versions} == set(source_map)
    mapping = [dict(source_id=source_map[v.source_sha256], version_id=str(v.id)) for v in versions]
    model, snapshot = ModelGateway(), None
    arms = ("B0", "B1") if family == "B" else ("T1", "T2")
    if family == "T":
        counts = model.query_tokens(case["question"])
        body = QueryCreate(
            kb_id=versions[0].kb_id,
            question=case["question"],
            profile="telecom-structural-v1",
            evidence_mode="compare" if case.get("question_type") == "comparison" else "single",
        )
        with transaction() as db:
            snapshot = capture(
                db, settings().workspace_id, body, [v.id for v in versions], counts
            ).model_dump(mode="json")
    first = new_run(arms[0], case, batch, versions, source, snapshot=snapshot)
    second = new_run(arms[1], case, batch, versions, source, shared=str(first.id), snapshot=snapshot)
    trace = RunTrace(first.id, first.owner, first.fence)
    token = current_trace.set(trace)
    try:
        retriever = (
            HybridRetriever(profile="m3-context", capture_selection=True)
            if family == "B"
            else StructuralRetriever(snapshot, parent_expansion=False, capture_selection=True)
        )
        chunks, candidates = retriever.retrieve(case["question"], first.versions)
        if family == "T" and retriever.pack.degraded:
            finish(
                first,
                candidates,
                retriever.pack.model_dump(mode="json"),
                error="degraded_reranker_unavailable",
            )
            finish(second, error="shared_retrieval_degraded")
            return [
                dict(
                    case_id=case["case_id"],
                    split=case.get("split"),
                    arm=a,
                    run_id=str(r.id),
                    status="DEGRADED",
                    degraded=True,
                    error="degraded_reranker_unavailable",
                    provider_calls=0,
                )
                for a, r in zip(arms, (first, second), strict=True)
            ]
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        finish(first, error=code)
        finish(second, error=code)
        return [
            dict(
                case_id=case["case_id"],
                split=case.get("split"),
                arm=a,
                run_id=str(r.id),
                status="FAILED",
                degraded=False,
                error=code,
                provider_calls=0,
            )
            for a, r in zip(arms, (first, second), strict=True)
        ]
    finally:
        current_trace.reset(token)
    tokenizer = ContextTokenizer(model)
    if family == "B":
        pack = legacy_pack(chunks, case["question"], tokenizer, ARMS["B0"]["evidence"])
        seed_chunks, pool, before = retriever.selection_inputs or ([], [], {})
        other_chunks, other_pack = budget_legacy(seed_chunks, pool, case["question"], tokenizer)
        other_candidates = [dict(c, final_evidence_rank=None) for c in before.values()]
        by_id = {c["candidate_id"]: c for c in other_candidates}
        for n, chunk in enumerate(other_chunks, 1):
            c = by_id.setdefault(
                str(chunk.id),
                dict(
                    candidate_id=str(chunk.id),
                    document_version_id=str(chunk.version_id),
                    retrieval=[],
                    reranker_score=None,
                ),
            )
            c["final_evidence_rank"] = n
        other_candidates = list(by_id.values())
    else:
        pack = retriever.pack.model_dump(mode="json")
        with bounded_stage(2):
            other_chunks, other_pack_obj, other_candidates = structural_pack(
                retriever.selection_inputs, parent_expansion=True
            )
        other_pack = other_pack_obj.model_dump(mode="json")
        assert pack["seed_child_ids"] == other_pack["seed_child_ids"]
        assert pack["added_chars"] == 0 and all(s["origin"] == "seed" for s in pack["spans"])
    assert retrieval_identity(candidates) == retrieval_identity(other_candidates)
    one = finish(first, candidates, pack)
    two = finish(second, other_candidates, other_pack)
    results = [
        result(case, a, row, cs, cand, p, mapping, assess)
        for a, row, cs, cand, p in (
            (arms[0], one, chunks, candidates, pack),
            (arms[1], two, other_chunks, other_candidates, other_pack),
        )
    ]
    if family == "T":
        results[0]["snapshot_sha256"] = results[1]["snapshot_sha256"] = hashed(snapshot)
        if assess and case["split"] == "dev":
            rrf_chunks, rrf_pack, rrf_candidates = structural_pack(
                retriever.selection_inputs, parent_expansion=False, rrf_only=True
            )
            # Save explicit offline evidence execution without inventing another product arm.
            with transaction() as db:
                row = db.get(QueryRunRow, first.id)
                row.runtime_config = dict(
                    row.runtime_config, offline_rrf_seed_pack=rrf_pack.model_dump(mode="json")
                )
            from citeweave.evaluation.support import support_coverage

            reverse = {v["version_id"]: v["source_id"] for v in mapping}
            rrf_atoms = [
                dict(
                    source_id=reverse[str(c.version_id)],
                    block_id=c.block["block_id"],
                    start_offset=c.evidence["start_offset"],
                    end_offset=c.evidence["end_offset"],
                )
                for c in rrf_chunks
            ]
            results[0]["ablation"]["rrf_seed_coverage"] = support_coverage(
                rrf_atoms, case["support_groups"], case["required_aspects"], case["required_sources"]
            )
            results[0]["ablation"]["bge_seed_coverage"] = results[0]["assessment"]["support_coverage"][
                "final"
            ]
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["readiness", "evaluate"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    base = make_url(settings().db_url())
    os.environ["DEEPSEEK_API_KEY"] = ""
    source = source_identity()
    if args.mode == "evaluate" and source["dirty"]:
        raise ValueError("phase1_requires_committed_source")
    dataset, dataset_hash = load_dataset("citeweave-public-telecom-eval-v1")
    assert len(dataset["cases"]) == 72
    assert {c["split"] for c in dataset["cases"]} == {"dev", "regression", "safety"}
    cases = (
        dataset["cases"]
        if args.mode == "evaluate"
        else [
            dict(
                case_id="readiness-single",
                question="Describe HTTP field parsing requirements.",
                question_type="single-fact",
            ),
            dict(
                case_id="readiness-compare",
                question="Compare message delivery in MQTT and HTTP.",
                question_type="comparison",
            ),
        ]
    )
    batch = args.mode + "-" + uuid4().hex[:12]
    manifest = dict(
        batch=batch,
        source=source,
        arm_revision=ARM_REVISION,
        arms=ARMS,
        dataset_hash=dataset_hash,
        mode=args.mode,
        provider_calls=0,
        holdout_access="NOT_ACCESSED",
        development_revision_count=0,
        scope="all seven captured sources; comparison evidence mode only",
        ordering="dataset order; B0/B1 shared draw then T1/T2 shared draw",
    )
    manifest_path = args.output / "manifest.json"
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(prior[k] != manifest[k] for k in ("source", "dataset_hash", "arm_revision", "mode")):
            raise ValueError("resume_identity_mismatch")
        manifest, batch = prior, prior["batch"]
    save(args.output / "manifest.json", manifest)
    results = []
    for case in cases:
        for family in ("B", "T"):
            path = args.output / f"{case['case_id']}-{family}.json"
            if path.exists():
                values = json.loads(path.read_text(encoding="utf-8"))
                results.extend(values)
                continue
            try:
                values = execute_pair(base, family, case, batch, source, dataset, args.mode == "evaluate")
            except Exception as exc:
                # Preserve failures; never reissue a query to improve the measurement.
                values = [
                    dict(
                        case_id=case["case_id"],
                        split=case.get("split"),
                        arm=a,
                        status="FAILED",
                        degraded=False,
                        error=type(exc).__name__,
                        provider_calls=0,
                    )
                    for a in (("B0", "B1") if family == "B" else ("T1", "T2"))
                ]
                import traceback

                (args.output / f"{case['case_id']}-{family}-error.txt").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
                # Close any owned rows even if packaging/assessment failed after retrieval.
                with transaction() as db:
                    for value in values:
                        row = db.scalar(
                            select(QueryRunRow).where(
                                QueryRunRow.key == f"d1:{batch}:{case['case_id']}:{value['arm']}"
                            )
                        )
                        if row:
                            value["run_id"] = str(row.id)
                            row.status, row.error_code = "FAILED", "phase1_assessment_or_pack_failure"
                            row.runtime_config = dict(row.runtime_config, evaluation_error=type(exc).__name__)
                            row.completed_at = db.scalar(select(func.clock_timestamp()))
            save(path, values)
            results.extend(values)
            print(
                json.dumps(
                    [
                        dict(case=v["case_id"], arm=v["arm"], status=v["status"], error=v.get("error"))
                        for v in values
                    ]
                ),
                flush=True,
            )
    save(args.output / "results.json", results)
    if args.mode == "readiness":
        assert len(results) == 8 and all(r["status"] == "SUCCESS" and not r["degraded"] for r in results)
        assert any(r["pack"].get("added_chars", 0) > 0 for r in results if r["arm"] == "T2")
        save(
            args.output / "readiness.json",
            dict(
                status="PASS",
                source=source,
                queries=2,
                arms=8,
                paired_equivalence=True,
                T1_parent_added=0,
                real_BGE=True,
                provider_calls=0,
                development_cases_executed=0,
            ),
        )
    print(
        json.dumps(
            dict(status="DONE", records=len(results), success=sum(r["status"] == "SUCCESS" for r in results))
        )
    )


if __name__ == "__main__":
    main()
