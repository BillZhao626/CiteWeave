"""Redis task configuration and PG-authoritative dispatch boundaries."""

import os
from datetime import timedelta

import pytest
from redis import Redis
from sqlalchemy import text

from citeweave import ingestion_state as state
from citeweave.celery_app import app, evaluate_case, ingest
from citeweave.db import transaction
from citeweave.domain import IngestionJobRow, OutboxRow
from citeweave.settings import settings


def test_task_routes_and_limits():
    assert ingest.soft_time_limit == 1800 and ingest.time_limit == 1860
    assert evaluate_case.soft_time_limit == 180 and evaluate_case.time_limit == 210
    assert app.conf.broker_transport_options["visibility_timeout"] == 2100
    assert app.conf.task_routes[ingest.name]["queue"] == "cw-ingestion"
    assert app.conf.task_routes[evaluate_case.name]["queue"] == "cw-evaluation"
    assert app.conf.task_acks_late and app.conf.task_reject_on_worker_lost
    assert app.conf.task_publish_retry is False


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="needs Redis and isolated PG")
def test_actual_redis_identity():
    broker = Redis.from_url(settings().broker_url, socket_timeout=3, socket_connect_timeout=3)
    assert broker.ping()
    info = broker.info("server")
    assert info["redis_version"] == "8.2.9"
    assert "valkey_version" not in info and "valkey" not in info.get("server_name", "").lower()


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="needs isolated PG")
def test_dispatch_outside_transaction_and_deadline():
    from test_m1_database import make_upload

    _, _, uploaded = make_upload()
    job_id = uploaded.job.id
    sent = []

    def send(identity):
        # This would block and fail if reconcile held the row lock across broker I/O.
        with transaction() as db:
            db.execute(text("SET LOCAL lock_timeout='200ms'"))
            db.execute(text("SELECT id FROM cw1_ingestion_jobs WHERE id=:id FOR UPDATE"), {"id": identity})
        sent.append(identity)

    state.reconcile(send)
    assert str(job_id) in sent
    with transaction() as db:
        db.get(OutboxRow, job_id).published_at = state.now(db) - timedelta(seconds=16)
    state.reconcile(send)
    assert sent.count(str(job_id)) == 2
    lease = state.claim(job_id, "first")
    assert lease and state.claim(job_id, "duplicate") is None
    with transaction() as db:
        db.get(IngestionJobRow, job_id).absolute_deadline = state.now(db) - timedelta(seconds=1)
    with pytest.raises(state.StaleAttempt):
        state.heartbeat(job_id, lease["fence"])
    state.reconcile(send)
    assert state.claim(job_id, "late") is None
    with transaction() as db:
        row = db.get(IngestionJobRow, job_id)
        assert row.status == "FAILED_FINAL" and row.error_code == "ingestion_deadline_exhausted"
