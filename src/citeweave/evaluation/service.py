"""Product evaluation commands: frozen scope, durable case queue and bounded recovery."""

import asyncio
import hashlib
import logging
import time
from contextlib import aclosing
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text

from citeweave import answering, schemas
from citeweave.catalog import authorized_kb
from citeweave.db import transaction
from citeweave.domain import (
    ChunkRow,
    DocumentRow,
    EvalCaseRow,
    EvalRunRow,
    IngestionJobRow,
    QueryRunRow,
    VersionRow,
)
from citeweave.embeddings import embedding_identity, resolve_experiment_bindings
from citeweave.evaluation.assessment import Assessor
from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.holdout import HOLDOUT_ID, require_selection
from citeweave.evaluation.judge import assess_answer, reserve
from citeweave.evaluation.reporting import refresh
from citeweave.lifecycle import LIVE, governance_lock
from citeweave.profiles import query_profile
from citeweave.settings import ROOT
from citeweave.trace import runtime_config


def authorized_eval(db, workspace, identity):
    row = db.scalar(select(EvalRunRow).where(EvalRunRow.id == identity, EvalRunRow.workspace_id == workspace))
    if not row:
        raise HTTPException(404, "evaluation_not_found")
    return row


def create(
    workspace, kb_id, dataset_id, split, key, profile="m2", judge_profile="judge-v1", replay_source=None
):
    if dataset_id == HOLDOUT_ID:
        require_selection(profile, judge_profile, split)
    if judge_profile not in {"judge-v1", "judge-v2", "judge-v3", "judge-v4"}:
        raise HTTPException(422, "unknown_judge_profile")
    config = runtime_config(profile)
    dataset, digest = load_dataset(dataset_id)
    with transaction() as db:
        governance_lock(db)
        authorized_kb(db, kb_id, workspace)
        existing = db.scalar(
            select(EvalRunRow).where(EvalRunRow.workspace_id == workspace, EvalRunRow.key == key)
        )
        if existing:
            if (existing.kb_id, existing.dataset_hash, existing.split) != (kb_id, digest, split):
                raise HTTPException(409, "idempotency_conflict")
            expected = (profile, judge_profile, str(replay_source) if replay_source else None)
            actual = (
                existing.runtime_config.get("query_profile", "m2"),
                existing.runtime_config.get("judge_profile", "judge-v1"),
                existing.runtime_config.get("replay_source"),
            )
            if expected != actual:
                raise HTTPException(409, "idempotency_conflict")
            return existing
        if split not in {"dev", "test", "all"}:
            raise HTTPException(422, "invalid_split")
        if db.scalar(select(EvalRunRow.id).where(EvalRunRow.status.in_(["PENDING", "RUNNING"])).limit(1)):
            raise HTTPException(409, "evaluation_capacity")
        active = list(
            db.scalars(
                select(VersionRow)
                .join(DocumentRow, DocumentRow.active_version_id == VersionRow.id)
                .where(DocumentRow.kb_id == kb_id, VersionRow.status == "READY")
            )
        )
        versions, bindings = {}, {}
        for source in dataset["sources"]:
            matches = [v for v in active if v.source_sha256 == source["sha256"]]
            if len(matches) != 1:
                raise HTTPException(409, "evaluation_corpus_missing_or_ambiguous")
            version = matches[0]
            versions[source["source_id"]] = str(version.id)
            bindings[str(version.id)] = version.index_collection
        revision = query_profile(profile)
        if revision.get("embedding_key") and not replay_source:
            bindings = resolve_experiment_bindings(
                db,
                workspace,
                [UUID(v) for v in versions.values()],
                embedding_identity(revision["embedding_key"]),
            )
        source, source_cases = None, {}
        if replay_source:
            source = authorized_eval(db, workspace, replay_source)
            if profile != source.runtime_config.get("query_profile", "m2"):
                raise HTTPException(409, "replay_profile_mismatch")
            if (source.kb_id, source.dataset_hash, source.status) != (kb_id, digest, "COMPLETED"):
                raise HTTPException(409, "replay_source_mismatch")
            source_cases = {
                c.case_id: c
                for c in db.scalars(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == replay_source))
            }
            versions = source.versions
            bindings = source.runtime_config["index_bindings"]
        config.update(
            index_bindings=bindings,
            judge_profile=judge_profile,
            judge_prompt_sha256=hashlib.sha256(
                (ROOT / "prompts" / (judge_profile + ".txt")).read_bytes()
            ).hexdigest(),
            replay_source=str(replay_source) if replay_source else None,
        )
        row = EvalRunRow(
            id=uuid4(),
            workspace_id=workspace,
            kb_id=kb_id,
            key=key,
            dataset_id=dataset_id,
            dataset_hash=digest,
            split=split,
            versions=versions,
            runtime_config=config,
        )
        db.add(row)
        db.flush()
        for case in dataset["cases"]:
            if split == "all" or case["split"] == split:
                values = {}
                if source:
                    original = source_cases.get(case["case_id"])
                    if not original or not original.result or original.status != "COMPLETED":
                        raise HTTPException(409, "replay_case_missing")
                    values = dict(
                        query_run_id=original.query_run_id,
                        result=original.result,
                        human_review=original.human_review,
                    )
                db.add(EvalCaseRow(eval_run_id=row.id, case_id=case["case_id"], **values))
        return row


def branches_from_run(row):
    branches = {
        v: dict(version_id=v, collection=row.index_bindings.get(v), dense=[], bm25=[]) for v in row.versions
    }
    for candidate in row.candidates:
        for hit in candidate["retrieval"]:
            branches[hit["score_scope"]][hit["source"]].append(
                (hit["rank"], candidate["candidate_id"], hit["score"])
            )
    for branch in branches.values():
        for name in ("dense", "bm25"):
            branch[name] = [(identity, score) for _, identity, score in sorted(branch[name])]
    return list(branches.values())


def cancel(workspace, eval_id):
    """Stop scheduling. A currently executing query finishes within its existing deadline."""
    with transaction() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(17702203)"))
        row = authorized_eval(db, workspace, eval_id)
        if row.status in {"COMPLETED", "CANCELLED"}:
            return row
        row.status, row.completed_at = "CANCELLED", db.scalar(select(func.clock_timestamp()))
        for case in db.scalars(
            select(EvalCaseRow)
            .where(EvalCaseRow.eval_run_id == eval_id, EvalCaseRow.status.in_(["PENDING", "QUEUED"]))
            .with_for_update()
        ):
            case.status, case.owner, case.lease_until = "CANCELLED", None, None
        return row


@lru_cache(maxsize=1)
def assessor_for(workspace, version_items):
    return Assessor(workspace, dict(version_items))


def save_owned(eval_id, case_id, owner, **values):
    with transaction() as db:
        row = db.scalar(
            select(EvalCaseRow)
            .where(EvalCaseRow.eval_run_id == eval_id, EvalCaseRow.case_id == case_id)
            .with_for_update()
        )
        if (
            not row
            or row.owner != owner
            or not row.lease_until
            or row.lease_until <= db.scalar(select(func.clock_timestamp()))
        ):
            raise ValueError("evaluation_lease_lost")
        for key, value in values.items():
            setattr(row, key, value)


async def execute_case(eval_id, case_id, owner):
    with transaction() as db:
        evaluation = db.get(EvalRunRow, eval_id)
        saved = db.get(EvalCaseRow, (eval_id, case_id))
    dataset, digest = load_dataset(evaluation.dataset_id)
    spec = next(c for c in dataset["cases"] if c["case_id"] == case_id)
    if digest != evaluation.dataset_hash:
        raise ValueError("evaluation_dataset_changed")
    current = runtime_config(evaluation.runtime_config.get("query_profile", "m2"))
    if "query_profile" not in evaluation.runtime_config:
        current.pop("query_profile")
        current.pop("query_revision")
    if any(evaluation.runtime_config.get(k) != v for k, v in current.items()):
        raise ValueError("evaluation_config_changed")
    judge_profile = evaluation.runtime_config.get("judge_profile", "judge-v1")
    if (
        hashlib.sha256((ROOT / "prompts" / (judge_profile + ".txt")).read_bytes()).hexdigest()
        != evaluation.runtime_config["judge_prompt_sha256"]
    ):
        raise ValueError("evaluation_judge_changed")
    start = time.perf_counter()
    result = saved.result
    if not result:
        key = f"eval:{eval_id}:{case_id}"
        with transaction() as db:
            prior = db.scalar(
                select(QueryRunRow).where(
                    QueryRunRow.workspace_id == evaluation.workspace_id, QueryRunRow.key == key
                )
            )
        if prior and prior.status == "RUNNING":
            # Never reconnect/reissue a provider call with uncertain outcome after worker loss.
            if prior.created_at > datetime.now(timezone.utc) - timedelta(seconds=120):
                raise HTTPException(429, "query_running")
            answering.failed(prior.id, "api_interrupted", True)
        run = answering.begin_query(
            evaluation.workspace_id,
            schemas.QueryCreate(
                kb_id=evaluation.kb_id,
                question=spec["question"],
                profile=evaluation.runtime_config.get("query_profile", "m2"),
            ),
            key,
            captured_bindings=evaluation.runtime_config["index_bindings"],
        )
        save_owned(eval_id, case_id, owner, query_run_id=run.id)
        async with aclosing(answering.stream_answer(run)) as stream:
            async for _ in stream:
                pass
        with transaction() as db:
            row = db.get(QueryRunRow, run.id)
            selected = sorted(
                [c for c in row.candidates if c.get("final_evidence_rank")],
                key=lambda c: c["final_evidence_rank"],
            )
            evidence = [
                dict(
                    label="E" + str(c["final_evidence_rank"]),
                    text=db.get(ChunkRow, UUID(c["candidate_id"])).text,
                )
                for c in selected
            ]
        assessor = assessor_for(evaluation.workspace_id, tuple(sorted(evaluation.versions.items())))
        branches = branches_from_run(row)
        result = dict(
            case_id=case_id,
            split=spec["split"],
            query_run_id=str(row.id),
            status=row.status,
            question=spec["question"],
            question_type=spec["question_type"],
            answerable=spec["answerable"],
            answer=row.result,
            selected_evidence=evidence,
            error_code=row.error_code,
            usage=row.usage,
            estimated_yuan=float(row.estimated_yuan) if row.estimated_yuan is not None else None,
            latency_ms=(time.perf_counter() - start) * 1000,
            actual_config=row.runtime_config,
            assessment=assessor.assess(spec, row.id, branches, row.candidates, row.result),
        )
        save_owned(eval_id, case_id, owner, result=result)
    with transaction() as db:
        saved = db.get(EvalCaseRow, (eval_id, case_id))
        cancelled = db.get(EvalRunRow, eval_id).status == "CANCELLED"
    if not saved.judge and not cancelled:
        if saved.judge_reserved_yuan:
            judged = dict(
                status="FAILED",
                error_code="judge_unknown_after_interruption",
                estimated_yuan=None,
                method="llm_judge_not_ground_truth",
                scores=None,
            )
        else:
            reserve(eval_id, case_id)
            judged = await assess_answer(spec, result, judge_profile)
        save_owned(eval_id, case_id, owner, judge=judged, judge_estimated_yuan=judged["estimated_yuan"])
    save_owned(eval_id, case_id, owner, status="COMPLETED")
    refresh(eval_id)


def run_case(eval_id, case_id):
    identity, owner = UUID(eval_id), uuid4()
    with transaction() as db:
        row = db.scalar(
            select(EvalCaseRow)
            .where(EvalCaseRow.eval_run_id == identity, EvalCaseRow.case_id == case_id)
            .with_for_update()
        )
        evaluation = db.get(EvalRunRow, identity)
        if not row or row.status not in {"QUEUED", "PENDING"} or evaluation.status == "CANCELLED":
            return
        row.status, row.owner = "RUNNING", owner
        row.lease_until = db.scalar(select(func.clock_timestamp())) + timedelta(seconds=180)
        evaluation.status = "RUNNING"
    try:
        asyncio.run(execute_case(identity, case_id, owner))
    except HTTPException as exc:
        if exc.status_code == 429 and exc.detail in {"single_query_capacity", "query_running"}:
            save_owned(identity, case_id, owner, status="PENDING")
        else:
            save_owned(
                identity,
                case_id,
                owner,
                status="FAILED",
                judge={"status": "FAILED", "error_code": str(exc.detail)},
            )
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc) == "evaluation_lease_lost":
            logging.warning("evaluation_lease_lost eval=%s case=%s", identity, case_id)
            return
        save_owned(
            identity,
            case_id,
            owner,
            status="FAILED",
            judge={"status": "FAILED", "error_code": type(exc).__name__},
        )


def reconcile(send):
    completed = []
    dispatch = None
    with transaction() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(17702203)"))
        now = db.scalar(select(func.clock_timestamp()))
        for row in db.scalars(
            select(EvalCaseRow)
            .where(EvalCaseRow.status.in_(["QUEUED", "RUNNING"]), EvalCaseRow.lease_until < now)
            .with_for_update(skip_locked=True)
        ):
            parent = db.get(EvalRunRow, row.eval_run_id)
            row.status = "CANCELLED" if parent.status == "CANCELLED" else "PENDING"
            row.owner = None
        for evaluation in db.scalars(
            select(EvalRunRow)
            .where(EvalRunRow.status.in_(["PENDING", "RUNNING"]))
            .with_for_update(skip_locked=True)
        ):
            unfinished = db.scalar(
                select(EvalCaseRow.case_id)
                .where(
                    EvalCaseRow.eval_run_id == evaluation.id,
                    EvalCaseRow.status.in_(["PENDING", "QUEUED", "RUNNING"]),
                )
                .limit(1)
            )
            if not unfinished:
                evaluation.status, evaluation.completed_at = "COMPLETED", now
                completed.append(evaluation.id)
        if not db.scalar(
            select(IngestionJobRow.id).where(IngestionJobRow.status.in_(LIVE)).limit(1)
        ) and not db.scalar(
            select(EvalCaseRow.case_id).where(EvalCaseRow.status.in_(["QUEUED", "RUNNING"])).limit(1)
        ):
            row = db.scalar(
                select(EvalCaseRow)
                .join(EvalRunRow)
                .where(EvalCaseRow.status == "PENDING", EvalRunRow.status.in_(["PENDING", "RUNNING"]))
                .order_by(EvalRunRow.created_at, EvalCaseRow.case_id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if row:
                row.status, row.lease_until = "QUEUED", now + timedelta(seconds=60)
                dispatch = (str(row.eval_run_id), row.case_id)
    if dispatch:
        send(*dispatch)  # A failed send remains durable QUEUED and recovers after its lease.
    for identity in completed:
        refresh(identity)
