"""Conservative index ownership, fenced rebuild, explicit release switching and audited GC."""

import re
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, text

from citeweave.catalog import authorized_kb
from citeweave.db import transaction
from citeweave.domain import (
    ChunkRow,
    CitationRow,
    DocumentRow,
    EvalRunRow,
    IndexRow,
    IngestionJobRow,
    KnowledgeBaseRow,
    OperationRow,
    OutboxRow,
    QueryRunRow,
    VersionRow,
)
from citeweave.index import QdrantIndex
from citeweave.pipeline import ACTIVE, PIPELINE_VERSION
from citeweave.settings import settings

LIVE = ["PENDING", "RETRY_WAIT", *ACTIVE]


def governance_lock(db):
    db.execute(text("SELECT pg_advisory_xact_lock(17702202)"))


def authorized_version(db, workspace, version_id):
    version = db.get(VersionRow, version_id)
    if not version:
        raise HTTPException(404, "version_not_found")
    authorized_kb(db, version.kb_id, workspace)
    return version


def operation(db, workspace, key, kind, target):
    existing = db.scalar(
        select(OperationRow).where(OperationRow.workspace_id == workspace, OperationRow.key == key)
    )
    if existing:
        if existing.kind != kind or existing.target != target:
            raise HTTPException(409, "idempotency_conflict")
        return existing, False
    row = OperationRow(id=uuid4(), workspace_id=workspace, key=key, kind=kind, target=target)
    db.add(row)
    db.flush()
    return row, True


def register_index(lease, name):
    from citeweave.ingestion_state import owned

    with transaction() as db:
        governance_lock(db)
        owned(db, lease["job_id"], lease["fence"])
        if db.get(IndexRow, name):
            raise ValueError("index_name_collision")
        db.add(
            IndexRow(
                name=name,
                workspace_id=lease["workspace_id"],
                version_id=lease["version_id"],
                job_id=lease["job_id"],
                fence=lease["fence"],
                state="BUILDING",
            )
        )


def adopt_legacy(db, workspace, names):
    """Only adopt exact M1 names with a matching durable INDEXING event or published pointer."""
    versions = list(
        db.scalars(
            select(VersionRow).join(KnowledgeBaseRow).where(KnowledgeBaseRow.workspace_id == workspace)
        )
    )
    known = {v.id.hex: v for v in versions}
    for name in names:
        if db.get(IndexRow, name):
            continue
        match = re.fullmatch(r"cw1_v([0-9a-f]{32})_f([1-9][0-9]*)", name)
        if not match or match[1] not in known:
            continue
        version, fence = known[match[1]], int(match[2])
        jobs = list(
            db.scalars(
                select(IngestionJobRow).where(
                    IngestionJobRow.document_version_id == version.id, IngestionJobRow.kind == "ingest"
                )
            )
        )
        proof = next(
            (
                job
                for job in jobs
                if any(e.get("status") == "INDEXING" and e.get("fence") == fence for e in job.events)
            ),
            None,
        )
        if name == version.index_collection or proof:
            db.add(
                IndexRow(
                    name=name,
                    workspace_id=workspace,
                    version_id=version.id,
                    job_id=proof.id if proof else None,
                    fence=fence,
                    state="PUBLISHED" if name == version.index_collection else "SUPERSEDED",
                )
            )
    db.flush()


def protected_reasons(db, row):
    reasons = []
    if row.state == "BUILDING":
        from datetime import datetime, timezone

        for build in db.scalars(
            select(OperationRow).where(
                OperationRow.kind == "embedding_index", OperationRow.status == "RUNNING"
            )
        ):
            if (
                build.detail.get("collection") == row.name
                and build.detail.get("fence") == row.fence
                and datetime.fromisoformat(build.detail["lease_until"]) > datetime.now(timezone.utc)
            ):
                reasons.append("live_embedding_index_attempt")
    version = db.get(VersionRow, row.version_id)
    doc = db.get(DocumentRow, version.document_id)
    if version.index_collection == row.name:
        reasons.append("active_published" if doc.active_version_id == version.id else "published_version")
    job = db.get(IngestionJobRow, row.job_id) if row.job_id else None
    if job and job.status in LIVE:
        # Also protects queued/retrying jobs; do not race future publication or recovery.
        reasons.append("running_or_recoverable_attempt")
    for evaluation in db.scalars(select(EvalRunRow)):
        if row.name in evaluation.runtime_config.get("index_bindings", {}).values():
            reasons.append("evaluation_snapshot_reference")
            break
    runs = db.scalars(select(QueryRunRow).where(QueryRunRow.versions.contains([str(version.id)])))
    for run in runs:
        referenced = row.name in run.index_bindings.values()
        legacy = not run.index_bindings
        if referenced:
            reasons.append("run_snapshot_reference")
            break
        if legacy and run.status == "RUNNING":
            reasons.append("legacy_live_run")
            break
        if legacy and db.scalar(
            select(CitationRow.run_id)
            .join(ChunkRow, CitationRow.evidence_id == ChunkRow.id)
            .where(CitationRow.run_id == run.id, ChunkRow.version_id == version.id)
            .limit(1)
        ):
            reasons.append("legacy_citation_version_reference")
            break
    return sorted(set(reasons))


def gc_plan(workspace):
    index = QdrantIndex()
    names = {c.name for c in index.client.get_collections().collections}
    with transaction() as db:
        governance_lock(db)
        adopt_legacy(db, workspace, names)
        registered = {
            r.name: r for r in db.scalars(select(IndexRow).where(IndexRow.workspace_id == workspace))
        }
        result = []
        for name in sorted(names | registered.keys()):
            row = registered.get(name)
            reasons = protected_reasons(db, row) if row else ["unknown_ownership"]
            if row and row.state == "DELETED":
                reasons.append("already_deleted" if name not in names else "unexpected_reappeared_collection")
            result.append(
                dict(
                    name=name,
                    disposition="protected" if reasons else "candidate",
                    reasons=reasons or ["unreferenced_owned_attempt"],
                    exists=name in names,
                    state=row.state if row else "UNKNOWN",
                    version_id=str(row.version_id) if row else None,
                )
            )
        return result


def gc_delete(workspace, name, key):
    # Durable intent first. A crash after external deletion can be retried using the same key.
    with transaction() as db:
        governance_lock(db)
        row = db.get(IndexRow, name)
        if not row or row.workspace_id != workspace:
            raise HTTPException(404, "owned_index_not_found")
        op, _ = operation(db, workspace, key, "gc", name)
        if op.status == "COMPLETED":
            return op
    with transaction() as db:
        governance_lock(db)
        row = db.get(IndexRow, name)
        op = db.scalar(
            select(OperationRow).where(OperationRow.workspace_id == workspace, OperationRow.key == key)
        )
        reasons = protected_reasons(db, row)
        if reasons:
            op.status, op.detail = "PROTECTED", {"reasons": reasons}
            return op
        if row.state == "DELETED":
            op.status, op.detail = "COMPLETED", {"already_deleted": True}
            return op
        try:
            index = QdrantIndex()
            if index.client.collection_exists(name):
                index.client.delete_collection(name)
            if index.client.collection_exists(name):
                raise RuntimeError("index_delete_not_confirmed")
            row.state = "DELETED"
            op.status, op.detail = "COMPLETED", {"deleted": name, "reason": "unreferenced_owned_attempt"}
        except Exception as exc:
            op.status, op.detail = (
                "FAILED",
                {"error_code": "index_delete_failed", "class": type(exc).__name__},
            )
        return op


def rebuild(workspace, version_id, key):
    with transaction() as db:
        governance_lock(db)
        version = authorized_version(db, workspace, version_id)
        op, fresh = operation(db, workspace, key, "rebuild", str(version_id))
        if not fresh:
            return op
        if version.status != "READY":
            raise HTTPException(409, "rebuild_requires_ready_version")
        if db.scalar(
            select(IngestionJobRow.id)
            .where(IngestionJobRow.document_version_id == version.id, IngestionJobRow.status.in_(LIVE))
            .limit(1)
        ):
            raise HTTPException(409, "version_job_running")
        job = IngestionJobRow(
            id=uuid4(),
            document_version_id=version.id,
            kind="rebuild",
            max_attempts=settings().max_attempts,
            pipeline_version=version.profile.get("pipeline", PIPELINE_VERSION),
            absolute_deadline=db.scalar(select(func.clock_timestamp()))
            + timedelta(
                seconds=version.profile.get("limits", {}).get(
                    "deadline_seconds", settings().ingestion_deadline_seconds
                )
            ),
        )
        db.add(job)
        db.flush()
        db.add(OutboxRow(job_id=job.id))
        op.status, op.detail = "ACCEPTED", {"job_id": str(job.id)}
        return op


def rollback(workspace, document_id, target_version, expected_active, key):
    with transaction() as db:
        governance_lock(db)
        version = authorized_version(db, workspace, target_version)
        if version.document_id != document_id:
            raise HTTPException(404, "version_not_found")
        doc = db.scalar(select(DocumentRow).where(DocumentRow.id == document_id).with_for_update())
        op, fresh = operation(db, workspace, key, "rollback", str(document_id) + ":" + str(target_version))
        if not fresh:
            if op.detail.get("expected_active") != str(expected_active):
                raise HTTPException(409, "idempotency_conflict")
            return op
        if doc.active_version_id != expected_active:
            raise HTTPException(409, "active_version_changed")
        if version.status != "READY" or not version.index_collection:
            raise HTTPException(409, "rollback_requires_ready_version")
        if db.scalar(
            select(IngestionJobRow.id)
            .join(VersionRow)
            .where(
                VersionRow.document_id == document_id,
                IngestionJobRow.kind == "ingest",
                IngestionJobRow.status.in_(LIVE),
            )
            .limit(1)
        ):
            raise HTTPException(409, "document_ingestion_running")
        index_row = db.get(IndexRow, version.index_collection)
        if version.profile.get("unit_kind") == "structural_child":
            from citeweave.document_profiles import content_hash
            from citeweave.domain import StructureArtifactRow

            artifact = (
                db.get(StructureArtifactRow, index_row.artifact_id)
                if index_row and index_row.artifact_id
                else None
            )
            if (
                not artifact
                or artifact.state != "PUBLISHED"
                or artifact.version_id != version.id
                or index_row.unit_kind != "structural_child"
                or index_row.index_profile_hash != content_hash(version.profile)
            ):
                raise HTTPException(409, "structure_binding_unavailable")
        if index_row and index_row.state == "DELETED":
            raise HTTPException(409, "index_unavailable_rebuild_required")
        if not QdrantIndex().client.collection_exists(version.index_collection):
            raise HTTPException(409, "index_unavailable_rebuild_required")
        doc.active_version_id = target_version
        op.status, op.detail = (
            "COMPLETED",
            {"expected_active": str(expected_active), "active_version_id": str(target_version)},
        )
        return op
