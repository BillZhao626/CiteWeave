import os
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from structure_fixtures import FixtureTokenizer, original_pdf

from citeweave import catalog, schemas
from citeweave import ingestion_state as state
from citeweave.db import transaction
from citeweave.domain import (
    ChildSpanRow,
    ChunkRow,
    IndexRow,
    IngestionJobRow,
    RetrievalChildRow,
    StructureArtifactRow,
    VersionRow,
)
from citeweave.ingestion import run_ingestion
from citeweave.lifecycle import rebuild
from citeweave.structural_ingestion import load_published

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="needs isolated PG and Qdrant"),
]


def upload():
    workspace = uuid4()
    kb, _ = catalog.create_kb(
        workspace, schemas.KnowledgeBaseCreate(name="Original structure acceptance"), str(uuid4())
    )
    result = catalog.upload(
        workspace,
        kb.id,
        original_pdf(),
        "original.pdf",
        "original",
        "source",
        None,
        "telecom-protocol-pdf-v1",
    )
    return workspace, kb, result


@pytest.fixture
def fixture_models(monkeypatch):
    monkeypatch.setattr("citeweave.structural_ingestion.GatewayTokenizer", FixtureTokenizer)
    monkeypatch.setattr(
        "citeweave.model_client.ModelGateway.embed",
        lambda self, texts, query=False, contract=None: [[1.0] + [0.0] * 383 for _ in texts],
    )


def test_real_persistence_typed_index_rebuild_and_legacy_reader_rejection(fixture_models, monkeypatch):
    workspace, kb, result = upload()
    repeated = catalog.upload(
        workspace,
        kb.id,
        original_pdf(),
        "original.pdf",
        "original",
        "source",
        None,
        "telecom-protocol-pdf-v1",
    )
    assert repeated.version.id == result.version.id and repeated.job.id == result.job.id
    with pytest.raises(HTTPException, match="idempotency_conflict"):
        catalog.upload(workspace, kb.id, original_pdf(), "original.pdf", "original", "source", None)
    run_ingestion(str(result.job.id))
    with transaction() as db:
        job = db.get(IngestionJobRow, result.job.id)
        assert job.status == "READY", job.error_code
        v = db.get(VersionRow, result.version.id)
        index = db.get(IndexRow, v.index_collection)
        assert index.unit_kind == "structural_child" and index.state == "PUBLISHED"
        draft = load_published(db, index.artifact_id)
        assert len(draft["children"]) > 0 and any(len(c["span_ids"]) > 1 for c in draft["children"])
        assert all(c["id"] not in {a["id"] for a in draft["chunks"]} for c in draft["children"])
        assert db.scalar(
            select(func.count()).select_from(ChildSpanRow).where(ChildSpanRow.version_id == v.id)
        ) == sum(len(c["span_ids"]) for c in draft["children"])
        old_collection = v.index_collection
    from citeweave.answering import begin_query

    with pytest.raises(HTTPException, match="structural_query_not_enabled"):
        begin_query(workspace, schemas.QueryCreate(kb_id=kb.id, question="Original marker?"), "query")
    from citeweave.hybrid import HybridRetriever

    with pytest.raises(ValueError, match="structural_query_not_enabled"):
        HybridRetriever().retrieve("Original marker?", [str(result.version.id)])
    # A rebuild cannot call the current PDF parser or tokenizer to replace frozen identities.
    monkeypatch.setattr(
        "citeweave.structural_ingestion.parse_structural_pdf",
        lambda *a: pytest.fail("reparse during rebuild"),
    )
    op = rebuild(workspace, result.version.id, "rebuild")
    run_ingestion(op.detail["job_id"])
    with transaction() as db:
        job = db.get(IngestionJobRow, UUID(op.detail["job_id"]))
        assert job.status == "READY", job.error_code
        v = db.get(VersionRow, result.version.id)
        assert v.index_collection != old_collection
        again = load_published(db, db.get(IndexRow, v.index_collection).artifact_id)
        assert draft["nodes"] == again["nodes"] and draft["children"] == again["children"]
    for statement in [
        "UPDATE cw3_structure_artifacts SET tree_hash='changed' WHERE id=:id",
        "DELETE FROM cw3_structure_nodes WHERE artifact_id=:id",
        "UPDATE cw3_retrieval_children SET retrieval_text='invented' WHERE artifact_id=:id",
        "UPDATE cw1_chunks SET text='invented' WHERE id IN "
        "(SELECT evidence_id FROM cw3_child_spans m JOIN cw3_retrieval_children c "
        "ON c.id=m.child_id WHERE c.artifact_id=:id)",
        "UPDATE cw2_indexes SET bm25_hash='invented' WHERE artifact_id=:id",
    ]:
        with pytest.raises(DBAPIError):
            with transaction() as db:
                db.execute(text(statement), {"id": draft["artifact"]["id"]})
    from citeweave.structure_views import artifact_for

    with transaction() as db:
        assert artifact_for(db, workspace, result.version.id, None).id == UUID(draft["artifact"]["id"])
        with pytest.raises(HTTPException) as denied:
            artifact_for(db, uuid4(), result.version.id, None)
        assert denied.value.status_code == 404


def test_partial_index_and_stale_attempt_never_publish(fixture_models, monkeypatch):
    _, _, result = upload()
    from citeweave.index import QdrantIndex

    original = QdrantIndex.write_children

    def lose_owner(self, collection, children, dense, encoder, start, binding, scope):
        original(self, collection, children, dense, encoder, start, binding, scope)
        with transaction() as db:
            job = db.get(IngestionJobRow, result.job.id)
            job.lease_until = state.now(db) - timedelta(seconds=1)
        state.reconcile(lambda _: None)

    monkeypatch.setattr(QdrantIndex, "write_children", lose_owner)
    run_ingestion(str(result.job.id))
    with transaction() as db:
        job = db.get(IngestionJobRow, result.job.id)
        assert job.status == "RETRY_WAIT"
        assert db.get(VersionRow, result.version.id).index_collection is None
        assert (
            db.scalar(
                select(func.count()).select_from(ChunkRow).where(ChunkRow.version_id == result.version.id)
            )
            == 0
        )
        artifact = db.scalar(
            select(StructureArtifactRow).where(StructureArtifactRow.version_id == result.version.id)
        )
        assert artifact.state == "DRAFT"
        assert (
            db.scalar(
                select(func.count())
                .select_from(RetrievalChildRow)
                .where(RetrievalChildRow.version_id == result.version.id)
            )
            == 0
        )
        job.available_at = state.now(db) - timedelta(seconds=1)
    monkeypatch.setattr(QdrantIndex, "write_children", original)
    run_ingestion(str(result.job.id))
    with transaction() as db:
        job = db.get(IngestionJobRow, result.job.id)
        assert job.status == "READY", job.error_code
        assert job.attempt == 2
