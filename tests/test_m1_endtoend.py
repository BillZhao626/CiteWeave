"""Real PostgreSQL/Qdrant/E5/reranker, simulated LLM to keep regression tests free."""

import json
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from citeweave import answering, catalog, ingestion_state, schemas
from citeweave.api import create_app
from citeweave.db import migrate, transaction
from citeweave.domain import DocumentRow, IngestionJobRow, QueryRunRow, VersionRow
from citeweave.ingestion import run_ingestion
from citeweave.settings import ROOT

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="needs local services/models"),
]
TOKEN = "local-test-owner-token-not-production"


class FakeProvider:
    calls = 0

    async def stream(self, messages):
        FakeProvider.calls += 1
        evidence = json.loads(messages[-1]["content"])["evidence"]
        support = next(e for e in evidence if "30 秒" in e["text"])
        yield {"text": "湖畔站每 30 秒采样，保留 7 天 [" + support["label"] + "]。"}
        yield {"usage": {"prompt_tokens": 100, "completion_tokens": 20}, "model": "test-provider"}


def setup_ready():
    migrate()
    workspace = uuid4()
    kb, _ = catalog.create_kb(workspace, schemas.KnowledgeBaseCreate(name="E2E original"), "kb")
    result = catalog.upload(
        workspace,
        kb.id,
        (ROOT / "apps/web/public/original-handbook.pdf").read_bytes(),
        "original.pdf",
        "original",
        "upload",
        None,
    )
    run_ingestion(str(result.job.id))
    with transaction() as db:
        assert db.get(IngestionJobRow, result.job.id).status == "READY"
    return workspace, kb, result


@pytest.mark.parametrize("profile", ["m2", "m3-context"])
def test_real_pipeline_stream_replay_scope_and_version_provenance(monkeypatch, profile):
    monkeypatch.setattr(answering, "DeepSeekProvider", FakeProvider)
    workspace, kb, uploaded = setup_ready()
    headers = {"Authorization": "Bearer " + TOKEN, "Idempotency-Key": str(uuid4())}
    question = {"kb_id": str(kb.id), "question": "湖畔观测站温度采样频率和数据保留时间？"}
    if profile == "m2":
        question["profile"] = profile
    before = FakeProvider.calls
    with TestClient(create_app(TOKEN, workspace)) as client:
        result = client.post("/v1/queries", headers=headers, json=question)
        events = [json.loads(line[6:]) for line in result.text.splitlines() if line.startswith("data: ")]
        assert events[-1]["type"] == "final"
        answer = events[-1]["answer"]
        assert any(e["type"] == "delta" and e["provisional"] for e in events)
        citation = answer["citations"][0]
        assert citation["document_version_id"] == str(uploaded.version.id)
        assert "30 秒" in citation["span"]["quote"] and citation["span"]["boxes"][0]["page_index"] == 0
        replay = client.post("/v1/queries", headers=headers, json=question)
        assert FakeProvider.calls == before + 1 and '"type":"final"' in replay.text
        resolved = client.get(
            "/v1/evidence/" + citation["evidence_id"], params={"run_id": answer["run_id"]}, headers=headers
        )
        assert resolved.status_code == 200 and resolved.json()["span"] == citation["span"]
        content = client.get(citation["content_url"], headers=headers)
        assert content.content == (ROOT / "apps/web/public/original-handbook.pdf").read_bytes()
        assert (
            client.get(
                "/v1/evidence/" + citation["evidence_id"], params={"run_id": str(uuid4())}, headers=headers
            ).status_code
            == 404
        )
        trace = client.get("/v1/runs/" + answer["run_id"], headers=headers).json()
        assert trace["runtime_config"]["query_profile"] == profile
        if profile == "m3-context":
            assert any(c.get("context_seed") for c in trace["candidates"])
        assert any(c["reranker_score"] is not None and c["retrieval"] for c in trace["candidates"])
        assert client.get("/v1/jobs/" + str(uploaded.job.id), headers=headers).json()["attempt"] == 1
    with TestClient(create_app(TOKEN, uuid4())) as other:
        assert other.get(citation["content_url"], headers=headers).status_code == 404
        assert (
            other.get(
                "/v1/evidence/" + citation["evidence_id"],
                params={"run_id": answer["run_id"]},
                headers=headers,
            ).status_code
            == 404
        )
    # A failed re-upload must preserve the previous valid version and its historical citation.
    new = catalog.upload(
        workspace, kb.id, b"%PDF-broken", "broken.pdf", "original", "new", uploaded.version.document_id
    )
    with transaction() as db:
        assert db.get(DocumentRow, uploaded.version.document_id).active_version_id == uploaded.version.id
        assert db.get(VersionRow, new.version.id).index_collection is None


def test_upload_contract_cookie_csrf_and_idempotency():
    workspace = uuid4()
    headers = {"Authorization": "Bearer " + TOKEN, "Idempotency-Key": "new-kb"}
    with TestClient(create_app(TOKEN, workspace)) as client:
        kb = client.post("/v1/knowledge-bases", json={"name": "Upload"}, headers=headers).json()["id"]
        endpoint = "/v1/knowledge-bases/" + kb + "/documents"
        params = {"filename": "original.pdf", "license": "original"}
        data = (ROOT / "apps/web/public/original-handbook.pdf").read_bytes()
        assert client.post(endpoint, params=params, content=data).status_code == 401
        assert client.post(endpoint, params=params, content=data, headers=headers).status_code == 415
        pdf_headers = dict(headers, **{"Content-Type": "application/pdf"})
        first = client.post(endpoint, params=params, content=data, headers=pdf_headers)
        assert first.status_code == 202
        assert client.post(endpoint, params=params, content=data, headers=pdf_headers).json() == first.json()
        assert (
            client.post(endpoint, params=params, content=b"%PDF-other", headers=pdf_headers).status_code
            == 409
        )
        assert (
            client.get("/v1/documents/" + first.json()["version"]["document_id"], headers=headers).status_code
            == 200
        )
        assert (
            client.post(
                "/v1/auth/session", json={"token": TOKEN}, headers={"Origin": "https://untrusted.invalid"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/v1/auth/session", json={"token": TOKEN}, headers={"Origin": "http://testserver"}
            ).status_code
            == 204
        )
        assert client.get("/v1/knowledge-bases").status_code == 200
        assert (
            client.post(
                "/v1/knowledge-bases", json={"name": "csrf"}, headers={"Idempotency-Key": "csrf"}
            ).status_code
            == 403
        )


def test_abandoned_query_recovery_and_invalid_final_usage(monkeypatch):
    workspace, kb, _ = setup_ready()
    body = schemas.QueryCreate(kb_id=kb.id, question="湖畔站采样频率？")
    run = answering.begin_query(workspace, body, "interrupted")
    with transaction() as db:
        db.get(QueryRunRow, run.id).created_at = ingestion_state.now(db) - timedelta(seconds=121)
    ingestion_state.reconcile(lambda _: None)
    with transaction() as db:
        stored = db.get(QueryRunRow, run.id)
        assert stored.status == "FAILED" and stored.error_code == "api_interrupted"

    class BadProvider:
        async def stream(self, messages):
            yield {"text": "答案 [E99]"}
            yield {"usage": {"prompt_tokens": 10, "completion_tokens": 4}}

    monkeypatch.setattr(answering, "DeepSeekProvider", BadProvider)
    with TestClient(create_app(TOKEN, workspace)) as client:
        r = client.post(
            "/v1/queries",
            json=body.model_dump(mode="json"),
            headers={"Authorization": "Bearer " + TOKEN, "Idempotency-Key": "invalid"},
        )
        events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
        assert events[-1]["type"] == "error" and not any(e["type"] == "final" for e in events)
        assert events[-1]["code"] == "invalid_or_missing_citation"
    with transaction() as db:
        failed = db.scalar(
            select(QueryRunRow).where(QueryRunRow.workspace_id == workspace, QueryRunRow.key == "invalid")
        )
        assert failed.result is None and failed.usage["completion_tokens"] == 4
