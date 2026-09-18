import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text

from citeweave import catalog, schemas
from citeweave import ingestion_state as state
from citeweave.db import migrate, transaction
from citeweave.domain import ChunkRow, IngestionJobRow, VersionRow
from citeweave.settings import ROOT, settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="needs local DB"),
]


def make_upload():
    workspace = uuid4()
    kb, _ = catalog.create_kb(
        workspace, schemas.KnowledgeBaseCreate(name="original integration"), str(uuid4())
    )
    return (
        workspace,
        kb,
        catalog.upload(
            workspace,
            kb.id,
            b"%PDF-1.4\nsynthetic pending fixture",
            "original.pdf",
            "original",
            str(uuid4()),
            None,
        ),
    )


def test_empty_database_migration():
    name = "cw_migration_test_" + uuid4().hex
    admin = create_engine(settings().db_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + name + '"'))
    target = admin.url.set(database=name)
    env = dict(os.environ, CW_DATABASE_URL=target.render_as_string(hide_password=False))
    result = subprocess.run(
        [
            str(ROOT / ".venv/Scripts/python.exe"),
            "-c",
            "from citeweave.db import migrate; migrate(); migrate()",
        ],
        env=env,
        capture_output=True,
        timeout=40,
    )
    assert result.returncode == 0, "migration failed (credentials intentionally not printed)"
    check = create_engine(target)
    assert {
        "cw1_documents",
        "cw1_document_versions",
        "cw1_ingestion_jobs",
        "cw1_query_runs",
        "alembic_version",
    } <= set(inspect(check).get_table_names())
    check.dispose()
    with admin.connect() as connection:
        connection.execute(text('DROP DATABASE "' + name + '"'))  # Exact unique DB created by this test only.
    admin.dispose()


def test_concurrent_idempotency_and_immutable_versions():
    migrate()
    workspace = uuid4()
    body = schemas.KnowledgeBaseCreate(name="concurrent")
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: catalog.create_kb(workspace, body, "same"), range(4)))
    assert sum(created for _, created in results) == 1
    kb = results[0][0]
    first = catalog.upload(workspace, kb.id, b"%PDF-a", "a.pdf", "original", "upload", None)
    repeat = catalog.upload(workspace, kb.id, b"%PDF-a", "a.pdf", "original", "upload", None)
    assert first.version.id == repeat.version.id and first.job.id == repeat.job.id
    new = catalog.upload(
        workspace, kb.id, b"%PDF-b", "a.pdf", "original", "upload-2", first.version.document_id
    )
    assert new.version.document_id == first.version.document_id and new.version.id != first.version.id
    assert new.version.sequence == 2


def test_fencing_visibility_and_bounded_recovery():
    _, _, result = make_upload()
    job_id = result.job.id
    for attempt in range(1, 4):
        lease = state.claim(job_id, "test-worker")
        assert lease and state.claim(job_id, "duplicate") is None
        with transaction() as db:
            job = db.get(IngestionJobRow, job_id)
            assert job.attempt == attempt
            job.lease_until = state.now(db) - timedelta(seconds=1)
        state.reconcile(lambda _: None)
        with pytest.raises(state.StaleAttempt):
            state.stage(job_id, lease["fence"], "CHUNKING")
        with transaction() as db:
            job = db.get(IngestionJobRow, job_id)
            version = db.get(VersionRow, result.version.id)
            assert version.index_collection is None
            assert db.scalar(select(ChunkRow.id).where(ChunkRow.version_id == version.id)) is None
            assert job.status == ("FAILED_FINAL" if attempt == 3 else "RETRY_WAIT")
            assert job.error_code == "worker_lease_expired"
            job.available_at = state.now(db) - timedelta(seconds=1)
    assert state.claim(job_id, "extra") is None
