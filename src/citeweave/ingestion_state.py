"""Leases fence every durable mutation. Broker messages are only wake-up hints."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select

from citeweave.db import transaction
from citeweave.domain import (
    ChunkRow,
    DocumentRow,
    IndexRow,
    IngestionJobRow,
    KnowledgeBaseRow,
    OutboxRow,
    VersionRow,
)
from citeweave.pipeline import ACTIVE, transition_allowed
from citeweave.settings import settings


class StaleAttempt(Exception):
    pass


def now(db):
    return db.scalar(select(func.clock_timestamp()))


def event(job, status, stamp, code=None):
    job.events = [
        *job.events,
        {
            "status": str(status),
            "at": stamp.isoformat(),
            "attempt": job.attempt,
            "fence": job.fence,
            "code": code,
        },
    ]


def owned(db, job_id, fence):
    job = db.scalar(select(IngestionJobRow).where(IngestionJobRow.id == job_id).with_for_update())
    if (
        not job
        or job.fence != fence
        or job.status not in ACTIVE
        or job.lease_until <= now(db)
        or (job.absolute_deadline and job.absolute_deadline <= now(db))
    ):
        raise StaleAttempt()
    return job


def claim(job_id: UUID, owner: str):
    with transaction() as db:
        job = db.scalar(select(IngestionJobRow).where(IngestionJobRow.id == job_id).with_for_update())
        stamp = now(db)
        if not job or job.status not in ("PENDING", "RETRY_WAIT") or job.available_at > stamp:
            return None
        if job.absolute_deadline and job.absolute_deadline <= stamp:
            fail_locked(
                db, job, "ingestion_deadline_exhausted", "Ingestion deadline exhausted", permanent=True
            )
            return None
        if job.attempt >= job.max_attempts:
            raise RuntimeError("retry_invariant_broken")
        job.attempt += 1
        job.fence += 1
        job.owner = owner
        job.status = "PARSING"
        job.lease_until = stamp + timedelta(seconds=settings().lease_seconds)
        job.started_at = job.started_at or stamp
        event(job, job.status, stamp)
        version = db.get(VersionRow, job.document_version_id)
        if job.kind == "ingest":
            version.status = job.status
        workspace = db.get(KnowledgeBaseRow, version.kb_id).workspace_id
        return {
            "job_id": job.id,
            "fence": job.fence,
            "version_id": version.id,
            "kb_id": version.kb_id,
            "workspace_id": workspace,
            "blob_key": version.blob_key,
            "kind": job.kind,
            "profile": version.profile,
            "canonical_key": version.canonical_key,
            "index_collection": version.index_collection,
            "page_count": version.page_count,
            "remaining_seconds": (job.absolute_deadline - stamp).total_seconds()
            if job.absolute_deadline
            else settings().ingestion_deadline_seconds,
        }


def heartbeat(job_id, fence):
    with transaction() as db:
        job = owned(db, job_id, fence)
        job.lease_until = now(db) + timedelta(seconds=settings().lease_seconds)


def stage(job_id, fence, status):
    with transaction() as db:
        job = owned(db, job_id, fence)
        if not transition_allowed(job.status, status):
            raise ValueError("illegal_job_transition")
        job.status = status
        if job.kind == "ingest":
            db.get(VersionRow, job.document_version_id).status = status
        event(job, status, now(db))


def fail_locked(db, job, code, message, permanent=False):
    stamp = now(db)
    job.status = "FAILED_FINAL" if permanent or job.attempt >= job.max_attempts else "RETRY_WAIT"
    job.error_code, job.error_message = code, message
    job.owner, job.lease_until = None, None
    job.fence += 1
    job.available_at = stamp + timedelta(seconds=min(2**job.attempt, 30))
    if job.status == "FAILED_FINAL":
        job.finished_at = stamp
    if job.kind == "ingest":
        db.get(VersionRow, job.document_version_id).status = job.status
    event(job, job.status, stamp, code)
    db.get(OutboxRow, job.id).published_at = None


def fail(job_id, fence, code, message, permanent=False):
    with transaction() as db:
        job = owned(db, job_id, fence)
        fail_locked(db, job, code, message, permanent)


def publish(job_id, fence, chunks, collection, bm25, canonical_key, page_count, structure=None):
    from citeweave.lifecycle import governance_lock

    with transaction() as db:
        governance_lock(db)
        job = owned(db, job_id, fence)
        if job.status != "INDEXING":
            raise ValueError("publish_requires_indexing")
        version = db.get(VersionRow, job.document_version_id)
        index_row = db.get(IndexRow, collection)
        if (
            not index_row
            or index_row.state != "BUILDING"
            or index_row.job_id != job_id
            or index_row.fence != fence
        ):
            raise ValueError("publish_requires_owned_index")
        from citeweave.document_profiles import structural

        if structural(version.profile) != (structure is not None):
            raise ValueError("publish_profile_unit_mismatch")
        if structure is not None:
            from citeweave.structural_ingestion import publish_structure

            publish_structure(db, version, index_row, job, structure, chunks, bm25, canonical_key, page_count)
        elif index_row.unit_kind != "legacy_span":
            raise ValueError("publish_profile_unit_mismatch")
        if job.kind == "rebuild":
            existing = {
                str(c.id): c for c in db.scalars(select(ChunkRow).where(ChunkRow.version_id == version.id))
            }
            if (
                set(existing) != {c["id"] for c in chunks}
                or version.canonical_key != canonical_key
                or (structure is None and version.bm25 != bm25)
                or version.page_count != page_count
                or any(
                    existing[c["id"]].text != c["text"]
                    or existing[c["id"]].block != c["block"]
                    or existing[c["id"]].evidence != c["evidence"]
                    for c in chunks
                )
            ):
                raise ValueError("rebuild_truth_mismatch")
        # Per-attempt collections prevent a stale worker from mutating this published snapshot.
        for chunk in chunks if job.kind == "ingest" and structure is None else []:
            db.add(
                ChunkRow(
                    id=UUID(chunk["id"]),
                    version_id=version.id,
                    text=chunk["text"],
                    block=chunk["block"],
                    evidence=chunk["evidence"],
                )
            )
        if version.index_collection and (old_index := db.get(IndexRow, version.index_collection)):
            old_index.state = "SUPERSEDED"
        index_row.state = "PUBLISHED"
        version.status, version.index_collection = "READY", collection
        if structure is None:
            version.bm25 = bm25
        version.canonical_key = canonical_key
        version.chunk_count, version.page_count = len(chunks), page_count
        document = db.scalar(
            select(DocumentRow).where(DocumentRow.id == version.document_id).with_for_update()
        )
        active = db.get(VersionRow, document.active_version_id) if document.active_version_id else None
        if job.kind == "ingest" and (not active or active.sequence < version.sequence):
            document.active_version_id = version.id
        job.status, job.finished_at = "READY", now(db)
        job.owner, job.lease_until = None, None
        job.error_code, job.error_message = None, None
        event(job, "READY", job.finished_at)


def reconcile(send):
    """Periodic daemon call. Duplicate send after commit ambiguity is intentional and safe."""
    with transaction() as db:
        stamp = now(db)
        from citeweave.query_runtime import expire_queries

        expire_queries(db, stamp)
        exhausted = db.scalars(
            select(IngestionJobRow)
            .where(
                IngestionJobRow.status.in_([*ACTIVE, "PENDING", "RETRY_WAIT"]),
                IngestionJobRow.absolute_deadline <= stamp,
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job in exhausted:
            fail_locked(
                db, job, "ingestion_deadline_exhausted", "Ingestion deadline exhausted", permanent=True
            )
        expired = db.scalars(
            select(IngestionJobRow)
            .where(IngestionJobRow.status.in_(list(ACTIVE)), IngestionJobRow.lease_until < stamp)
            .with_for_update(skip_locked=True)
        ).all()
        for job in expired:
            fail_locked(db, job, "worker_lease_expired", "工作进程中断或失去租约，已记录恢复。")
    with transaction() as db:
        stamp = now(db)
        rows = db.execute(
            select(IngestionJobRow, OutboxRow)
            .join(OutboxRow, OutboxRow.job_id == IngestionJobRow.id)
            .where(
                IngestionJobRow.status.in_(["PENDING", "RETRY_WAIT"]), IngestionJobRow.available_at <= stamp
            )
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        dispatch = []
        for job, outbox in rows:
            if outbox.published_at and outbox.published_at > stamp - timedelta(seconds=15):
                continue
            dispatch.append((job.id, job.fence))
    # Never hold a DB transaction across broker I/O. Commit ambiguity may resend.
    for job_id, fence in dispatch:
        send(str(job_id))
        with transaction() as db:
            job = db.scalar(select(IngestionJobRow).where(IngestionJobRow.id == job_id).with_for_update())
            if job.fence == fence and job.status in {"PENDING", "RETRY_WAIT"}:
                db.get(OutboxRow, job_id).published_at = now(db)
