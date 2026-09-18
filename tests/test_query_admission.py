"""Real PG concurrency, deadline, legacy compatibility and late-result fencing."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from citeweave import answering, catalog, ingestion_state, schemas
from citeweave.db import migrate, transaction
from citeweave.domain import DocumentRow, QueryRunRow, VersionRow
from citeweave.query_runtime import remaining
from citeweave.settings import settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="needs isolated PostgreSQL"),
]


def ready_metadata():
    migrate()
    workspace = uuid4()
    kb, _ = catalog.create_kb(workspace, schemas.KnowledgeBaseCreate(name="admission fixture"), str(uuid4()))
    uploaded = catalog.upload(
        workspace, kb.id, b"%PDF-metadata-only", "original.pdf", "original", str(uuid4()), None
    )
    with transaction() as db:
        v = db.get(VersionRow, uploaded.version.id)
        v.status, v.index_collection = "READY", "admission_metadata_only"
        db.get(DocumentRow, v.document_id).active_version_id = v.id
    return workspace, schemas.QueryCreate(kb_id=kb.id, question="Admission test")


def test_atomic_capacity_and_duplicate_key(monkeypatch):
    workspace, body = ready_metadata()
    monkeypatch.setattr(settings(), "max_active_queries", 2)

    def start(i):
        try:
            return answering.begin_query(workspace, body, str(i))
        except HTTPException as exc:
            assert exc.status_code == 429 and exc.headers["Retry-After"] == "2"
            return None

    with ThreadPoolExecutor(8) as pool:
        rows = [r for r in pool.map(start, range(8)) if r]
    assert len(rows) == 2
    for row in rows:
        assert 0 < remaining(row.id, row.owner, row.fence) <= settings().query_deadline_seconds
        answering.failed(row.id, "fixture_complete", False)
    replay = answering.begin_query(workspace, body, rows[0].key)
    assert replay.id == rows[0].id and replay.status == "FAILED"


def test_expiry_fences_late_result_and_preserves_terminal():
    workspace, body = ready_metadata()
    run = answering.begin_query(workspace, body, "deadline")
    with transaction() as db:
        db.get(QueryRunRow, run.id).absolute_deadline = ingestion_state.now(db) - timedelta(seconds=1)
    ingestion_state.reconcile(lambda _: None)
    with pytest.raises(ValueError, match="run_no_longer_active"):
        answering.save_trace(run.id, [{"late": True}], run.owner, run.fence)
    with transaction() as db:
        row = db.get(QueryRunRow, run.id)
        assert row.status == "FAILED" and row.fence == run.fence + 1 and not row.candidates
    replacement = answering.begin_query(workspace, body, "after_expiry")
    answering.failed(replacement.id, "fixture_complete", False)


def test_legacy_null_deadline_and_terminal_rows():
    workspace, body = ready_metadata()
    run = answering.begin_query(workspace, body, "legacy")
    with transaction() as db:
        row = db.get(QueryRunRow, run.id)
        row.absolute_deadline = row.owner = row.fence = row.runtime_policy = None
        row.created_at = ingestion_state.now(db) - timedelta(seconds=121)
    ingestion_state.reconcile(lambda _: None)
    with transaction() as db:
        row = db.get(QueryRunRow, run.id)
        assert row.status == "FAILED" and row.fence is None
        row.result = {"historical": True}
    ingestion_state.reconcile(lambda _: None)
    with transaction() as db:
        assert db.scalar(select(QueryRunRow).where(QueryRunRow.id == run.id)).result == {"historical": True}


def test_finish_and_cancel_cannot_overwrite_each_other():
    workspace, body = ready_metadata()
    for i in range(6):
        run = answering.begin_query(workspace, body, "race-" + str(i))
        answer = schemas.Answer(
            run_id=run.id,
            text=answering.REFUSAL,
            citations=[],
            prompt_version="fixture",
            usage=None,
            estimated_yuan=0,
        )

        def complete():
            try:
                answering.finish(run.id, answer, run.owner, run.fence)
            except ValueError as exc:
                assert str(exc) == "run_no_longer_active"

        with ThreadPoolExecutor(2) as pool:
            futures = [
                pool.submit(complete),
                pool.submit(answering.failed, run.id, "client_cancelled", False),
            ]
            for future in futures:
                future.result()
        with transaction() as db:
            row = db.get(QueryRunRow, run.id)
            assert (row.status == "COMPLETED") == (row.result is not None)
