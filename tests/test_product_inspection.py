import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_eval_recovery import cleanup_cases  # noqa: F401
from test_structural_ingestion import fixture_models, upload  # noqa: F401

from citeweave.api import create_app
from citeweave.db import transaction
from citeweave.domain import RetrievalChildRow, StructureNodeRow
from citeweave.ingestion import run_ingestion

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="isolated PostgreSQL/Qdrant required"),
]
TOKEN = "original-inspection-test-token-only"
HEADERS = {"Authorization": "Bearer " + TOKEN}


def test_pdf_module_worker_mime_ignores_host_registry(tmp_path, monkeypatch):
    import mimetypes

    from citeweave.settings import settings

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "worker.mjs").write_text("export const original = true;", encoding="utf-8")
    monkeypatch.setattr(settings(), "web_root", tmp_path)
    mimetypes.init()
    mimetypes.add_type("text/plain", ".mjs")
    with TestClient(create_app(TOKEN, uuid4())) as client:
        response = client.get("/assets/worker.mjs")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/javascript")
        assert response.headers["x-content-type-options"] == "nosniff"


def test_structure_inspection_scopes_pagination_and_original_spans(fixture_models):  # noqa: F811
    workspace, _, result = upload()
    run_ingestion(str(result.job.id))
    with TestClient(create_app(TOKEN, workspace)) as client:
        base = f"/v1/versions/{result.version.id}/structure"
        artifact = client.get(base, headers=HEADERS).json()
        with transaction() as db:
            nodes = list(
                db.scalars(select(StructureNodeRow).where(StructureNodeRow.artifact_id == artifact["id"]))
            )
            parent_id = db.scalar(
                select(RetrievalChildRow.parent_node_id)
                .where(RetrievalChildRow.artifact_id == artifact["id"])
                .limit(1)
            )
            parent = next(node for node in nodes if node.id == parent_id)
            original_ids = set(parent.content_ids + parent.heading_ids)
        url = base + "/nodes/" + str(parent.id)
        value = client.get(url, headers=HEADERS, params={"limit": 1}).json()
        assert value["node"]["is_parent"] is True
        assert len(value["spans"]) == 1 and value["total_spans"] == len(original_ids)
        assert value["spans"][0]["evidence_id"] in original_ids
        assert value["spans"][0]["span"]["quote"]
        assert client.get(url, headers=HEADERS, params={"limit": 101}).status_code == 422
        assert client.get(url, headers=HEADERS, params={"artifact_id": str(uuid4())}).status_code == 409
        assert client.get(base + "/nodes/" + str(uuid4()), headers=HEADERS).status_code == 404
        assert client.get(url).status_code == 401
    with TestClient(create_app(TOKEN, uuid4())) as other:
        assert other.get(url, headers=HEADERS).status_code == 404


def test_unknown_provider_read_model_never_exposes_result_or_changes_case():
    from test_eval_recovery import due, get, make_case, query, start

    from citeweave.evaluation import lifecycle as lc
    from citeweave.provider_phases import dispatch, prepare

    identity, workspace = make_case()
    token = start(identity)
    q = query(token)
    phase = prepare(q.id, q.owner, q.fence, "answer", token)
    dispatch(phase.id, q.owner, q.fence, token)
    due(identity, lease_until="past")
    lc.sweep()
    before = get(identity)
    with TestClient(create_app(TOKEN, workspace)) as client:
        url = f"/v1/evaluations/{identity}/cases/original/runtime"
        value = client.get(url, headers=HEADERS).json()
        assert value["retry_state"] == "not_eligible"
        assert value["phases"][0]["state"] == "UNKNOWN"
        assert "result" not in value["phases"][0] and "owner" not in value["phases"][0]
        assert client.get(url.replace("original", "absent"), headers=HEADERS).status_code == 404
    after = get(identity)
    assert (before.status, before.fence, before.execution_attempt) == (
        after.status,
        after.fence,
        after.execution_attempt,
    )
    with TestClient(create_app(TOKEN, uuid4())) as other:
        assert other.get(url, headers=HEADERS).status_code == 404
