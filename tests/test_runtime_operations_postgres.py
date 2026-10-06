"""Real UUID-isolated PostgreSQL scope/read-only proof; service probes are synthetic."""

from uuid import uuid4

import test_conversation_postgres as pg
from fastapi.testclient import TestClient
from pydantic import SecretStr

from citeweave import conversations as core
from citeweave import runtime_operations as operations
from citeweave.api import create_app
from citeweave.db import transaction
from citeweave.domain import IngestionJobRow, VersionRow
from citeweave.settings import settings

isolated_pg = pg.isolated_pg
sample = pg.sample
pytestmark = pg.pytestmark


def test_operations_owner_scope_and_reads_never_mutate_business_state(sample, monkeypatch):
    workspace, conversation_id, request = sample
    other_workspace, other_scope = pg.metadata()
    run, _ = core.admit_once(workspace, conversation_id, "original-operations-test", request, pg.execution)
    version_id = request.scope.version_ids[0]
    job_id = uuid4()
    with transaction() as db:
        db.get(VersionRow, version_id).index_collection = "owned-fixture-collection"
        db.get(VersionRow, other_scope.version_ids[0]).index_collection = "other-fixture-collection"
        db.add(
            IngestionJobRow(
                id=job_id,
                document_version_id=version_id,
                status="READY",
                attempt=1,
                pipeline_version="original-test-pipeline",
            )
        )
    monkeypatch.setattr(settings(), "deepseek_api_key", SecretStr("synthetic-secret-never-exposed"))
    monkeypatch.setattr(
        operations,
        "observe_broker",
        lambda _: operations.ServiceObservation(
            component="Redis", status="unavailable", detail="Synthetic unavailable broker"
        ),
    )
    monkeypatch.setattr(
        operations,
        "observe_model",
        lambda _: operations.ServiceObservation(
            component="Model gateway", status="not_checked", detail="Synthetic test skips model"
        ),
    )

    def inspect_collections(config, rows):
        assert all(row.document_version_id == version_id for row in rows)
        return operations.ServiceObservation(
            component="Qdrant", status="not_checked", detail="Synthetic test skips index"
        )

    def forbidden_worker_ping():
        raise AssertionError("Broker unavailable must skip worker PING")

    monkeypatch.setattr(operations, "observe_collections", inspect_collections)
    monkeypatch.setattr(operations, "observe_workers", forbidden_worker_ping)
    token = "original-operations-http-test-token"
    headers = {"Authorization": "Bearer " + token}
    client = TestClient(create_app(token, workspace))
    assert client.get("/v1/runtime/operations").status_code == 401
    response = client.get("/v1/runtime/operations", headers=headers)
    assert response.status_code == 200
    value = response.json()
    assert [row["document_version_id"] for row in value["collections"]] == [str(version_id)]
    assert value["latest_job"]["id"] == str(job_id) and value["latest_run"]["id"] == str(run.id)
    assert "synthetic-secret" not in response.text
    assert value["services"][-1]["status"] == "not_checked"
    other = TestClient(create_app(token, uuid4())).get("/v1/runtime/operations", headers=headers).json()
    assert other["collections"] == [] and other["latest_job"] is None and other["latest_run"] is None
    with transaction() as db:
        assert db.get(VersionRow, version_id).status == "READY"
        assert db.get(IngestionJobRow, job_id).status == "READY"
    assert core.read_run_id(workspace, conversation_id, run.id).run.status == "ADMITTED"
