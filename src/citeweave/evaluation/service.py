"""Product evaluation commands: frozen scope, durable case queue and bounded recovery."""

import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from citeweave import schemas
from citeweave.catalog import authorized_kb
from citeweave.db import transaction
from citeweave.domain import (
    DocumentRow,
    EvalCaseRow,
    EvalRunRow,
    VersionRow,
)
from citeweave.embeddings import embedding_identity, resolve_experiment_bindings
from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.execution import execute_case as execute_case
from citeweave.evaluation.execution import run_case as run_case
from citeweave.evaluation.execution import save_owned as save_owned
from citeweave.evaluation.holdout import HOLDOUT_ID, require_selection
from citeweave.evaluation.lifecycle import cancel as cancel
from citeweave.evaluation.outbox import reconcile as reconcile
from citeweave.lifecycle import governance_lock
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
        allowed_splits = (
            {"dev", "regression", "safety"}
            if dataset_id == "citeweave-public-telecom-eval-v1"
            else {"dev", "test", "all"}
        )
        if split not in allowed_splits:
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
        if profile == "telecom-structural-v1":
            from citeweave.structural_repository import capture

            config["structural_snapshot"] = capture(
                db,
                workspace,
                schemas.QueryCreate(kb_id=kb_id, question="evaluation snapshot", profile=profile),
                [UUID(v) for v in versions.values()],
                {},
            ).model_dump(mode="json")
        now = db.scalar(select(func.clock_timestamp()))
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
            runtime_policy="eval-durable-v1",
            total_deadline=now + timedelta(hours=4),
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
                db.add(
                    EvalCaseRow(
                        eval_run_id=row.id,
                        case_id=case["case_id"],
                        absolute_deadline=row.total_deadline,
                        **values,
                    )
                )
        return row


def branches_from_run(row):
    branches = {
        v: dict(version_id=v, collection=row.index_bindings.get(v), dense=[], bm25=[]) for v in row.versions
    }
    for candidate in row.candidates:
        for hit in candidate["retrieval"]:
            scope = candidate.get("version_id", hit["score_scope"])
            branches[scope][hit.get("source", hit.get("branch"))].append(
                (hit["rank"], candidate["candidate_id"], hit.get("score", hit.get("raw_score")))
            )
    for branch in branches.values():
        for name in ("dense", "bm25"):
            branch[name] = [(identity, score) for _, identity, score in sorted(branch[name])]
    return list(branches.values())


# Public command names are preserved; execution now uses the finite PG policy.
