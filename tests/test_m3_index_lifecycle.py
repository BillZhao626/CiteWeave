"""Real PostgreSQL/Qdrant proof for separately owned experimental indexes."""

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from citeweave import answering, catalog, lifecycle, schemas
from citeweave.db import migrate, transaction
from citeweave.domain import IndexRow, OperationRow, QueryRunRow, VersionRow
from citeweave.embeddings import BGE, resolve_experiment_bindings
from citeweave.index import QdrantIndex
from citeweave.ingestion import run_ingestion
from citeweave.settings import ROOT, settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="isolated DB/services required"),
]


def test_experimental_index_failure_retry_is_fenced_and_does_not_replace_active(monkeypatch):
    from experiments.m3_embedding_index import build, owned

    migrate()
    workspace = settings().workspace_id
    kb, _ = catalog.create_kb(
        workspace, schemas.KnowledgeBaseCreate(name="Dense index fixture"), str(uuid4())
    )
    upload = catalog.upload(
        workspace,
        kb.id,
        (ROOT / "apps/web/public/original-handbook.pdf").read_bytes(),
        "original.pdf",
        "original",
        str(uuid4()),
        None,
    )
    run_ingestion(str(upload.job.id))
    with transaction() as db:
        original = db.get(VersionRow, upload.version.id).index_collection
    original_write = QdrantIndex.write

    def interrupted(self, *args):
        original_write(self, *args)
        raise RuntimeError("fixture_crash_after_external_write")

    key = "fixture-embedding-" + uuid4().hex
    monkeypatch.setattr(QdrantIndex, "write", interrupted)
    with pytest.raises(RuntimeError, match="fixture_crash"):
        build(upload.version.id, "e5-small", key)
    with transaction() as db:
        op = db.scalar(select(OperationRow).where(OperationRow.key == key))
        first, op_id = op.detail["collection"], op.id
        assert op.status == "FAILED"
        assert db.get(VersionRow, upload.version.id).index_collection == original
    monkeypatch.setattr(QdrantIndex, "write", original_write)
    result = build(upload.version.id, "e5-small", key)
    assert result["fence"] == 2 and result["collection"] != first
    assert build(upload.version.id, "e5-small", key) == result
    with transaction() as db:
        assert db.get(VersionRow, upload.version.id).index_collection == original
        assert db.get(IndexRow, result["collection"]).state == "EXPERIMENT_READY"
        with pytest.raises(ValueError, match="fence_lost"):
            owned(db, op_id, 1)
        with pytest.raises(HTTPException, match="embedding_index_not_ready"):
            resolve_experiment_bindings(db, workspace, [upload.version.id], BGE)
        # Provenance-only fixture: no BGE inference or fake quality metric.
        op = db.get(OperationRow, op_id)
        op.detail = dict(op.detail, embedding=BGE)
    body = schemas.QueryCreate(kb_id=kb.id, question="fixture", profile="m3-bge-dense")
    query = answering.begin_query(workspace, body, "fixture-bge-query")
    assert query.index_bindings[str(upload.version.id)] == result["collection"]
    assert lifecycle.gc_delete(workspace, result["collection"], "fixture-gc-protected").status == "PROTECTED"
    with transaction() as db:
        db.get(QueryRunRow, query.id).status = "FAILED"
        with pytest.raises(HTTPException):
            resolve_experiment_bindings(db, uuid4(), [upload.version.id], BGE)
    assert lifecycle.gc_delete(workspace, first, "fixture-gc-stale").status == "COMPLETED"
