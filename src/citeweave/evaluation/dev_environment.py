"""Only the seven approved sources in a named, local, isolated DEV database.

Exact UUID admission is evaluation-specific; parsing, publication, indexing and
retrieval are the existing production paths. No broker, provider or fixture.
"""

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid5

import httpx
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from citeweave.blobs import LocalBlobStore
from citeweave.db import engine, migrate, transaction
from citeweave.document_profiles import document_profile
from citeweave.domain import (
    ChunkRow,
    DocumentRow,
    IndexRow,
    IngestionJobRow,
    KnowledgeBaseRow,
    OutboxRow,
    StructureArtifactRow,
    VersionRow,
)
from citeweave.embeddings import E5
from citeweave.evaluation.dev_approval import load_human_gold
from citeweave.evaluation.dev_dataset import DATASET_HASH, identity, verify_original_sources
from citeweave.ingestion import run_ingestion
from citeweave.model_client import ModelGateway
from citeweave.settings import ROOT, settings
from citeweave.tokenization import TOKENIZERS

DATABASE = "cw_dev_v3_" + DATASET_HASH[:16]
ENVIRONMENT = ROOT / ".runtime/evaluation/v02-dev-paid-remediation/environment.json"
BLOB_ROOT = ROOT / ".runtime/evaluation/v02-dev-paid-remediation/blobs"


def bind_environment(*, create=False):
    config = settings()
    original = make_url(config.db_url())
    if original.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("dev_local_database_required")
    if original.database not in {"citeweave", DATABASE}:
        raise ValueError("dev_unexpected_database_configuration")
    url = original.set(database=DATABASE)
    if create:
        admin = create_engine(original.set(database="postgres"), isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as connection:
                if not connection.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": DATABASE}
                ):
                    connection.execute(text('CREATE DATABASE "' + DATABASE + '"'))
        finally:
            admin.dispose()
    if engine.cache_info().currsize:
        engine().dispose()
    engine.cache_clear()
    config.database_url = SecretStr(url.render_as_string(hide_password=False))
    config.blob_root = BLOB_ROOT
    config.model_attempts = 1
    config.provider_attempts = 1
    config.conversation_runtime_policy = None
    with transaction() as db:
        if db.scalar(text("SELECT current_database()")) != DATABASE:
            raise ValueError("dev_isolation_mismatch")
    return DATABASE


def model_binding():
    config = settings()
    if config.model_url != "http://127.0.0.1:18081" or config.qdrant_url != "http://127.0.0.1:16333":
        raise ValueError("dev_local_services_required")
    with httpx.Client(timeout=3, trust_env=False) as client:
        value = client.get(config.model_url + "/health").json()
    if value.get("status") != "ready" or value.get("embedding") != E5:
        raise ValueError("dev_resident_e5_mismatch")
    manifest = json.loads((ROOT / ".runtime/models.json").read_bytes())
    for entry in (E5, TOKENIZERS["bge"]):
        resident = manifest[entry["model"]]
        if resident["revision"] != entry["revision"] or not Path(resident["local_path"]).is_dir():
            raise ValueError("dev_model_manifest_mismatch")
    # Actual gateway tokenizer response binds both E5 and BGE revisions.
    model = ModelGateway()
    model.query_tokens("DEV source verification")
    return dict(embedding=E5, reranker=TOKENIZERS["bge"], gateway="LOCAL_PRODUCTION_E5_BGE")


def prepare_environment(*, recover_local_ingestion=False):
    data, approval, _ = load_human_gold(ROOT)
    verify_original_sources(ROOT, data)
    model_binding()
    with httpx.Client(timeout=3, trust_env=False) as client:
        client.get(settings().qdrant_url + "/healthz").raise_for_status()
    bind_environment(create=True)
    migrate()  # Only the dedicated database; never configured application DB.
    profile = document_profile("telecom-protocol-pdf-v1")
    store = LocalBlobStore(BLOB_ROOT)
    with transaction() as db:
        if not db.get(KnowledgeBaseRow, identity("kb")):
            db.add(
                KnowledgeBaseRow(
                    id=identity("kb"),
                    workspace_id=identity("workspace"),
                    name="Frozen DEV v3",
                    key="frozen-dev-v3",
                    fingerprint=DATASET_HASH,
                )
            )
            db.flush()
        if set(db.scalars(select(VersionRow.id))) - {s.version_id for s in data.sources}:
            raise ValueError("dev_foreign_corpus_rejected")
        for source in data.sources:
            raw = (ROOT / ".runtime/evaluation/v02-dev-sources" / (source.id + ".pdf")).read_bytes()
            key = store.put(raw)
            if key != source.pdf_sha256:
                raise ValueError("dev_source_hash_mismatch")
            row = db.get(VersionRow, source.version_id)
            if row:
                if (row.document_id, row.source_sha256, row.profile) != (
                    source.document_id,
                    source.pdf_sha256,
                    profile,
                ):
                    raise ValueError("dev_version_identity_collision")
                continue
            db.add(DocumentRow(id=source.document_id, kb_id=identity("kb"), title=source.id))
            db.flush()
            db.add(
                VersionRow(
                    id=source.version_id,
                    document_id=source.document_id,
                    kb_id=identity("kb"),
                    sequence=1,
                    filename=source.id + ".pdf",
                    license="MIT original AI-assisted",
                    source_sha256=key,
                    blob_key=key,
                    status="PENDING",
                    profile=profile,
                    key=source.id,
                    fingerprint=source.canonical_sha256,
                )
            )
            db.flush()
            job = IngestionJobRow(
                id=uuid5(source.version_id, "paid-dev-real-ingestion-v1"),
                document_version_id=source.version_id,
                max_attempts=1,
                pipeline_version=profile["pipeline"],
                absolute_deadline=db.scalar(select(func.clock_timestamp()))
                + timedelta(seconds=profile["limits"]["deadline_seconds"]),
            )
            db.add(job)
            db.flush()
            db.add(OutboxRow(job_id=job.id))
    for source in data.sources:
        with transaction() as db:
            status = db.get(VersionRow, source.version_id).status
            job_id = uuid5(source.version_id, "paid-dev-real-ingestion-v1")
            if status == "FAILED_FINAL" and recover_local_ingestion:
                # One explicit local-only recovery, preserve failed attempts and
                # private index names; no model-provider retry or data deletion.
                job_id = uuid5(source.version_id, "paid-dev-real-ingestion-recovery-01")
                if db.get(IngestionJobRow, job_id):
                    raise ValueError("dev_local_recovery_already_used")
                db.add(
                    IngestionJobRow(
                        id=job_id,
                        document_version_id=source.version_id,
                        max_attempts=1,
                        pipeline_version=profile["pipeline"],
                        absolute_deadline=db.scalar(select(func.clock_timestamp()))
                        + timedelta(seconds=profile["limits"]["deadline_seconds"]),
                    )
                )
                db.flush()
                db.add(OutboxRow(job_id=job_id))
                status = "PENDING"
        if status == "PENDING":
            run_ingestion(str(job_id))
        elif status != "READY":
            raise ValueError("dev_ingestion_failed_no_automatic_retry:" + source.id)
    receipt = verify_environment()
    receipt["approval_id"] = approval["approval_id"]
    ENVIRONMENT.parent.mkdir(parents=True, exist_ok=True)
    from citeweave.evaluation.dev_dataset import canonical

    if ENVIRONMENT.exists() and json.loads(ENVIRONMENT.read_bytes()) != receipt:
        raise ValueError("dev_environment_receipt_immutable")
    if not ENVIRONMENT.exists():
        ENVIRONMENT.write_bytes(canonical(receipt))
    return receipt


def verify_environment():
    from citeweave.conversation_contract import Scope
    from citeweave.conversation_evidence import validate_evidence
    from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
    from citeweave.index import QdrantIndex
    from citeweave.structural_ingestion import load_published

    data, _, _ = load_human_gold(ROOT)
    bind_environment()
    models = model_binding()
    bindings = []
    with transaction() as db:
        head = db.scalar(text("SELECT version_num FROM alembic_version"))
        if head not in {"0011", "0012"}:
            raise ValueError("dev_schema_head_mismatch")
        if set(db.scalars(select(VersionRow.id))) != {s.version_id for s in data.sources}:
            raise ValueError("dev_exact_seven_versions_required")
        for source in data.sources:
            v = db.get(VersionRow, source.version_id)
            index = db.get(IndexRow, v.index_collection) if v.index_collection else None
            document = db.get(DocumentRow, v.document_id)
            if (
                v.status != "READY"
                or v.source_sha256 != source.pdf_sha256
                or v.document_id != source.document_id
                or document.active_version_id != v.id
                or not index
                or index.state != "PUBLISHED"
                or index.version_id != v.id
                or index.workspace_id != identity("workspace")
                or index.embedding_identity != E5
            ):
                raise ValueError("dev_ready_publication_binding_mismatch")
            artifact = db.get(StructureArtifactRow, index.artifact_id)
            draft = load_published(db, artifact.id)
            # Production canonical_block hash includes immutable locator/scope;
            # Gold's canonical hash is SHA256(text), both must be reported.
            text_value = "\n".join(
                c.text for c in db.scalars(select(ChunkRow).where(ChunkRow.version_id == v.id))
            )
            # Read canonical blocks rather than assume chunk/physical-row order.
            blocks = json.loads(LocalBlobStore(BLOB_ROOT).get(v.canonical_key))
            canonical_text = "\n".join(b["text"] for b in blocks)
            if hashlib.sha256(canonical_text.encode()).hexdigest() != source.canonical_sha256:
                raise ValueError("dev_gold_canonical_text_mismatch")
            QdrantIndex().verify_children(
                index.name,
                draft["children"],
                dict(
                    unit_kind="structural_child",
                    artifact_id=str(artifact.id),
                    index_profile_hash=index.index_profile_hash,
                    embedding_identity=E5,
                    bm25_hash=index.bm25_hash,
                ),
                dict(
                    workspace_id=str(identity("workspace")), kb_id=str(identity("kb")), version_id=str(v.id)
                ),
            )
            bindings.append(
                dict(
                    source=source.id,
                    document_id=str(v.document_id),
                    version_id=str(v.id),
                    source_sha256=v.source_sha256,
                    gold_text_sha256=source.canonical_sha256,
                    canonical_block_sha256=v.canonical_key,
                    index=index.name,
                    index_profile_hash=index.index_profile_hash,
                    artifact_id=str(artifact.id),
                    tree_hash=artifact.tree_hash,
                    membership_hash=artifact.membership_hash,
                    embedding_identity=index.embedding_identity,
                    bm25_hash=index.bm25_hash,
                    chunk_count=v.chunk_count,
                    raw_chunk_chars=len(text_value),
                )
            )
    retriever = StructuralEvidenceRetriever(model=ModelGateway())
    packs = []
    for source in data.sources:
        view = next(v for v in data.views if source.id in v.scope)
        scope = Scope(kb_id=identity("kb"), version_ids=(source.version_id,))
        material = retriever.retrieve(identity("workspace"), scope, view.question)
        validate_evidence(identity("workspace"), scope, material)
        if not material.citations:
            raise ValueError("dev_real_retrieval_empty:" + source.id)
        packs.append(
            dict(
                source=source.id,
                query=view.question,
                evidence_pack=material.pack.model_dump(mode="json"),
                physical_citations=[c.model_dump(mode="json") for c in material.citations],
            )
        )
    return dict(
        database=DATABASE,
        schema_head=head,
        dataset_sha256=DATASET_HASH,
        models=models,
        bindings=bindings,
        retrieval=packs,
        execution="PROVIDER_FREE_INFRASTRUCTURE_NOT_DEV",
        external_calls=0,
    )
