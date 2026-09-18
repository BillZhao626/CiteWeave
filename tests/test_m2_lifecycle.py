"""Real PG/Qdrant/model lifecycle invariants; all artifacts belong to an isolated test DB."""

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from citeweave import answering, catalog, lifecycle, schemas
from citeweave.db import migrate, transaction
from citeweave.domain import ChunkRow, DocumentRow, IndexRow, OperationRow, QueryRunRow, VersionRow
from citeweave.index import QdrantIndex
from citeweave.ingestion import run_ingestion
from citeweave.settings import ROOT

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="isolated DB/services required"),
]


def test_rebuild_preserves_truth_rollback_keeps_citation_and_gc_rechecks_references():
    migrate()
    workspace = uuid4()
    kb, _ = catalog.create_kb(workspace, schemas.KnowledgeBaseCreate(name="M2 lifecycle fixture"), "kb")
    data = (ROOT / "apps/web/public/original-handbook.pdf").read_bytes()
    first = catalog.upload(workspace, kb.id, data, "original.pdf", "original", "v1", None)
    run_ingestion(str(first.job.id))
    second = catalog.upload(
        workspace, kb.id, data, "original.pdf", "original", "v2", first.version.document_id
    )
    run_ingestion(str(second.job.id))
    with transaction() as db:
        version = db.get(VersionRow, second.version.id)
        original_index, canonical = version.index_collection, version.canonical_key
        ids_before = set(db.scalars(select(ChunkRow.id).where(ChunkRow.version_id == version.id)))

    class Provider:
        async def stream(self, messages):
            yield {"text": "依据证据 [E1]。"}
            yield {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    run = answering.begin_query(
        workspace, schemas.QueryCreate(kb_id=kb.id, question="湖畔站采样间隔？"), "query"
    )

    async def ask():
        return [part async for part in answering.stream_answer(run, provider=Provider())]

    assert '"type":"final"' in asyncio.run(ask())[-1]
    operation = lifecycle.rebuild(workspace, second.version.id, "rebuild")
    assert lifecycle.rebuild(workspace, second.version.id, "rebuild").id == operation.id
    with transaction() as db:
        assert db.get(VersionRow, second.version.id).status == "READY"
    run_ingestion(operation.detail["job_id"])
    with transaction() as db:
        version = db.get(VersionRow, second.version.id)
        assert version.status == "READY" and version.index_collection != original_index
        assert version.canonical_key == canonical
        assert ids_before == set(db.scalars(select(ChunkRow.id).where(ChunkRow.version_id == version.id)))
        result = db.get(QueryRunRow, run.id)
        assert result.index_bindings[str(second.version.id)] == original_index
        assert {s["name"] for s in result.stages} >= {
            "retrieval_dense",
            "retrieval_bm25",
            "rrf",
            "reranker",
            "llm",
            "citation_validation",
        }
        evidence_id = result.result["citations"][0]["evidence_id"]
    from uuid import UUID

    assert (
        answering.get_citation(workspace, run.id, UUID(evidence_id)).document_version_id == second.version.id
    )
    with pytest.raises(HTTPException) as exc:
        lifecycle.rollback(
            workspace, first.version.document_id, first.version.id, first.version.id, "wrong-active"
        )
    assert exc.value.status_code == 409
    lifecycle.rollback(workspace, first.version.document_id, first.version.id, second.version.id, "rollback")
    with transaction() as db:
        assert db.get(DocumentRow, first.version.document_id).active_version_id == first.version.id
    assert (
        answering.get_citation(workspace, run.id, UUID(evidence_id)).document_version_id == second.version.id
    )
    assert lifecycle.gc_delete(workspace, original_index, "gc-referenced").status == "PROTECTED"
    orphan = "cw2_test_orphan_" + uuid4().hex
    index = QdrantIndex()
    index.create(orphan)
    with transaction() as db:
        db.add(IndexRow(name=orphan, workspace_id=workspace, version_id=first.version.id, state="SUPERSEDED"))
    planned = next(r for r in lifecycle.gc_plan(workspace) if r["name"] == orphan)
    assert planned["disposition"] == "candidate"
    assert index.client.collection_exists(orphan)  # dry-run did not mutate Qdrant
    deleted = lifecycle.gc_delete(workspace, orphan, "gc-orphan")
    assert deleted.status == "COMPLETED" and not index.client.collection_exists(orphan)
    assert lifecycle.gc_delete(workspace, orphan, "gc-orphan").id == deleted.id
    with transaction() as db:
        assert db.get(OperationRow, deleted.id).detail["deleted"] == orphan
    with pytest.raises(HTTPException):
        lifecycle.rebuild(uuid4(), first.version.id, "foreign")


def test_gc_unknown_ownership_never_deleted():
    migrate()
    workspace, name = uuid4(), "cw2_unknown_" + uuid4().hex
    index = QdrantIndex()
    index.create(name)
    try:
        entry = next(r for r in lifecycle.gc_plan(workspace) if r["name"] == name)
        assert entry["disposition"] == "protected" and entry["reasons"] == ["unknown_ownership"]
        with pytest.raises(HTTPException):
            lifecycle.gc_delete(workspace, name, "deny")
        assert index.client.collection_exists(name)
    finally:
        index.client.delete_collection(name)  # Exact test collection created immediately above.
