"""Only durable facts required by M1. Schema lifecycle belongs to Alembic."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Stamp:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeBaseRow(Stamp, Base):
    __tablename__ = "cw1_knowledge_bases"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))


class DocumentRow(Stamp, Base):
    __tablename__ = "cw1_documents"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kb_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_knowledge_bases.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    active_version_id: Mapped[UUID | None] = mapped_column(nullable=True)


class VersionRow(Stamp, Base):
    __tablename__ = "cw1_document_versions"
    __table_args__ = (UniqueConstraint("document_id", "sequence"), UniqueConstraint("kb_id", "key"))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_documents.id"), index=True)
    kb_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_knowledge_bases.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(200))
    license: Mapped[str] = mapped_column(String(40))
    source_sha256: Mapped[str] = mapped_column(String(64))
    blob_key: Mapped[str] = mapped_column(String(64))
    canonical_key: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    index_collection: Mapped[str | None] = mapped_column(String(120))
    chunk_count: Mapped[int] = mapped_column(default=0)
    page_count: Mapped[int] = mapped_column(default=0)
    profile: Mapped[dict] = mapped_column(JSONB)
    bm25: Mapped[dict | None] = mapped_column(JSONB)
    key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))


class IngestionJobRow(Stamp, Base):
    __tablename__ = "cw1_ingestion_jobs"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_version_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_document_versions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="ingest", server_default="ingest")
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    attempt: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    fence: Mapped[int] = mapped_column(default=0)
    owner: Mapped[str | None] = mapped_column(String(80))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    absolute_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pipeline_version: Mapped[str] = mapped_column(String(100))
    events: Mapped[list] = mapped_column(JSONB, default=list)


class OutboxRow(Base):
    __tablename__ = "cw1_outbox"
    job_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_ingestion_jobs.id"), primary_key=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChunkRow(Base):
    __tablename__ = "cw1_chunks"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_document_versions.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    block: Mapped[dict] = mapped_column(JSONB)
    evidence: Mapped[dict] = mapped_column(JSONB)


class QueryRunRow(Stamp, Base):
    __tablename__ = "cw1_query_runs"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(index=True)
    kb_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_knowledge_bases.id"))
    key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    absolute_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner: Mapped[UUID | None] = mapped_column()
    fence: Mapped[int | None] = mapped_column()
    runtime_policy: Mapped[str | None] = mapped_column(String(40))
    question: Mapped[str] = mapped_column(Text)
    trace_schema_revision: Mapped[str] = mapped_column(
        String(40), default="legacy-v1", server_default="legacy-v1"
    )
    structural_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    evidence_pack: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(24), default="RUNNING")
    versions: Mapped[list] = mapped_column(JSONB, default=list)
    candidates: Mapped[list] = mapped_column(JSONB, default=list)
    result: Mapped[dict | None] = mapped_column(JSONB)
    usage: Mapped[dict | None] = mapped_column(JSONB)
    reserved_yuan: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0.10"))
    estimated_yuan: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    error_code: Mapped[str | None] = mapped_column(String(80))
    index_bindings: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    runtime_config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    stages: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    calls: Mapped[list] = mapped_column(JSONB, default=list, server_default="[]")
    error_category: Mapped[str | None] = mapped_column(String(24))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CitationRow(Base):
    __tablename__ = "cw1_citations"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_query_runs.id"), primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_chunks.id"), primary_key=True)


class IndexRow(Stamp, Base):
    __tablename__ = "cw2_indexes"
    name: Mapped[str] = mapped_column(String(120), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(index=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_document_versions.id"), index=True)
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("cw1_ingestion_jobs.id"))
    fence: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(String(24), default="BUILDING")
    unit_kind: Mapped[str] = mapped_column(String(24), default="legacy_span", server_default="legacy_span")
    artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("cw3_structure_artifacts.id"))
    index_profile_hash: Mapped[str | None] = mapped_column(String(64))
    embedding_identity: Mapped[dict | None] = mapped_column(JSONB)
    bm25: Mapped[dict | None] = mapped_column(JSONB)
    bm25_hash: Mapped[str | None] = mapped_column(String(64))


class StructureArtifactRow(Base):
    __tablename__ = "cw3_structure_artifacts"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_document_versions.id"), index=True)
    parser_revision: Mapped[str] = mapped_column(String(80))
    profile_hash: Mapped[str] = mapped_column(String(64))
    profile: Mapped[dict] = mapped_column(JSONB)
    canonical_sha: Mapped[str] = mapped_column(String(64))
    tree_hash: Mapped[str] = mapped_column(String(64))
    membership_hash: Mapped[str] = mapped_column(String(64))
    tokenizers: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(24), default="DRAFT")


class StructureNodeRow(Base):
    __tablename__ = "cw3_structure_nodes"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    artifact_id: Mapped[UUID] = mapped_column(ForeignKey("cw3_structure_artifacts.id"), index=True)
    parent_node_id: Mapped[UUID | None] = mapped_column(ForeignKey("cw3_structure_nodes.id"))
    kind: Mapped[str] = mapped_column(String(24))
    number: Mapped[str | None] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(Text)
    heading_ids: Mapped[list] = mapped_column(JSONB)
    content_ids: Mapped[list] = mapped_column(JSONB)
    reading_order: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(24))
    reasons: Mapped[list] = mapped_column(JSONB)
    details: Mapped[dict] = mapped_column(JSONB)


class RetrievalChildRow(Base):
    __tablename__ = "cw3_retrieval_children"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_document_versions.id"), index=True)
    artifact_id: Mapped[UUID] = mapped_column(ForeignKey("cw3_structure_artifacts.id"), index=True)
    parent_node_id: Mapped[UUID] = mapped_column(ForeignKey("cw3_structure_nodes.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    retrieval_text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    membership_hash: Mapped[str] = mapped_column(String(64))
    tokenizers: Mapped[dict] = mapped_column(JSONB)
    token_counts: Mapped[dict] = mapped_column(JSONB)
    details: Mapped[dict] = mapped_column(JSONB)


class ChildSpanRow(Base):
    __tablename__ = "cw3_child_spans"
    child_id: Mapped[UUID] = mapped_column(ForeignKey("cw3_retrieval_children.id"), primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_chunks.id"), primary_key=True)
    version_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_document_versions.id"))
    position: Mapped[int] = mapped_column(Integer)


class OperationRow(Stamp, Base):
    __tablename__ = "cw2_operations"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(index=True)
    key: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(24))
    target: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)


class CircuitRow(Stamp, Base):
    __tablename__ = "cw2_circuits"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, default=dict)


class EvalRunRow(Stamp, Base):
    __tablename__ = "cw2_eval_runs"
    __table_args__ = (UniqueConstraint("workspace_id", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(index=True)
    kb_id: Mapped[UUID] = mapped_column(ForeignKey("cw1_knowledge_bases.id"))
    key: Mapped[str] = mapped_column(String(128))
    dataset_id: Mapped[str] = mapped_column(String(80))
    dataset_hash: Mapped[str] = mapped_column(String(64))
    split: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    versions: Mapped[dict] = mapped_column(JSONB)
    runtime_config: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvalCaseRow(Stamp, Base):
    __tablename__ = "cw2_eval_cases"
    eval_run_id: Mapped[UUID] = mapped_column(ForeignKey("cw2_eval_runs.id"), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    query_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("cw1_query_runs.id"))
    owner: Mapped[UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    judge: Mapped[dict] = mapped_column(JSONB, default=dict)
    human_review: Mapped[dict] = mapped_column(JSONB, default=dict)
    judge_reserved_yuan: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal(0))
    judge_estimated_yuan: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    judge_reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
