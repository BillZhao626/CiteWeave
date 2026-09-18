"""Durable catalog commands; every returned view is detached from its transaction."""

import hashlib
import json
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from citeweave import schemas
from citeweave.blobs import LocalBlobStore
from citeweave.db import transaction
from citeweave.domain import DocumentRow, IngestionJobRow, KnowledgeBaseRow, OutboxRow, VersionRow
from citeweave.pipeline import PIPELINE_VERSION, PROFILE
from citeweave.settings import settings


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def authorized_kb(db, identity: UUID, workspace: UUID, lock=False):
    query = select(KnowledgeBaseRow).where(
        KnowledgeBaseRow.id == identity, KnowledgeBaseRow.workspace_id == workspace
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "knowledge_base_not_found")
    return row


def create_kb(workspace: UUID, body: schemas.KnowledgeBaseCreate, key: str):
    digest = fingerprint(body.model_dump())
    with transaction() as db:
        identity = db.scalar(
            insert(KnowledgeBaseRow)
            .values(id=uuid4(), workspace_id=workspace, **body.model_dump(), key=key, fingerprint=digest)
            .on_conflict_do_nothing(index_elements=["workspace_id", "key"])
            .returning(KnowledgeBaseRow.id)
        )
        row = db.scalar(
            select(KnowledgeBaseRow).where(
                KnowledgeBaseRow.workspace_id == workspace, KnowledgeBaseRow.key == key
            )
        )
        if row.fingerprint != digest:
            raise HTTPException(409, "idempotency_conflict")
        return schemas.KnowledgeBase.model_validate(row), identity is not None


def upload(workspace, kb_id, data: bytes, filename: str, license: str, key: str, document_id: UUID | None):
    if not data.startswith(b"%PDF-") or not 0 < len(data) <= 10 * 1024 * 1024:
        raise HTTPException(422, "pdf_required_max_10_mib")
    digest = fingerprint([hashlib.sha256(data).hexdigest(), filename, license, str(document_id)])
    with transaction() as db:
        authorized_kb(db, kb_id, workspace, lock=True)
        row = db.scalar(select(VersionRow).where(VersionRow.kb_id == kb_id, VersionRow.key == key))
        if row:
            if row.fingerprint != digest:
                raise HTTPException(409, "idempotency_conflict")
            job = db.scalar(
                select(IngestionJobRow).where(
                    IngestionJobRow.document_version_id == row.id, IngestionJobRow.kind == "ingest"
                )
            )
            return schemas.UploadResult(
                version=schemas.Version.model_validate(row), job=schemas.Job.model_validate(job)
            )
        if document_id:
            document = db.scalar(
                select(DocumentRow)
                .where(DocumentRow.id == document_id, DocumentRow.kb_id == kb_id)
                .with_for_update()
            )
            if not document:
                raise HTTPException(404, "document_not_found")
            sequence = (
                db.scalar(select(func.max(VersionRow.sequence)).where(VersionRow.document_id == document_id))
                + 1
            )
        else:
            if (
                db.scalar(select(func.count()).select_from(DocumentRow).where(DocumentRow.kb_id == kb_id))
                >= 10
            ):
                raise HTTPException(409, "m1_max_10_documents_per_kb")
            document = DocumentRow(id=uuid4(), kb_id=kb_id, title=filename)
            db.add(document)
            db.flush()
            sequence = 1
        # Local write is bounded to 10 MiB. Parsing and all model work happen only in Celery.
        blob_key = LocalBlobStore(settings().blob_root).put(data)
        row = VersionRow(
            id=uuid4(),
            document_id=document.id,
            kb_id=kb_id,
            sequence=sequence,
            filename=filename,
            license=license,
            source_sha256=blob_key,
            blob_key=blob_key,
            profile=PROFILE,
            key=key,
            fingerprint=digest,
        )
        db.add(row)
        db.flush()
        job = IngestionJobRow(
            id=uuid4(),
            document_version_id=row.id,
            max_attempts=settings().max_attempts,
            pipeline_version=PIPELINE_VERSION,
            absolute_deadline=db.scalar(select(func.clock_timestamp()))
            + timedelta(seconds=settings().ingestion_deadline_seconds),
        )
        db.add(job)
        db.flush()
        db.add(OutboxRow(job_id=job.id))
        return schemas.UploadResult(
            version=schemas.Version.model_validate(row), job=schemas.Job.model_validate(job)
        )


def document_view(db, doc):
    rows = db.execute(
        select(VersionRow, IngestionJobRow)
        .join(IngestionJobRow, IngestionJobRow.document_version_id == VersionRow.id)
        .where(VersionRow.document_id == doc.id, IngestionJobRow.kind == "ingest")
        .order_by(VersionRow.sequence.desc())
    ).all()
    return schemas.Document(
        id=doc.id,
        kb_id=doc.kb_id,
        title=doc.title,
        active_version_id=doc.active_version_id,
        versions=[
            schemas.UploadResult(version=schemas.Version.model_validate(v), job=schemas.Job.model_validate(j))
            for v, j in rows
        ],
    )
