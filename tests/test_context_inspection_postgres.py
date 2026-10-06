"""Own UUID PostgreSQL fixture; no live runtime or provider dispatch."""

import json
from types import SimpleNamespace
from uuid import uuid4

import test_conversation_postgres as pg
from fastapi.testclient import TestClient
from test_conversation_runtime_postgres import evidence_case as evidence_case
from test_conversation_runtime_postgres import runtime

from citeweave import context_inspection
from citeweave import conversations as core
from citeweave.api import create_app
from citeweave.db import transaction
from citeweave.domain import KnowledgeBaseRow
from citeweave.settings import ROOT

isolated_pg = pg.isolated_pg
sample = pg.sample
pytestmark = pg.pytestmark


def test_context_get_authenticates_scope_and_preserves_durable_records(sample, monkeypatch, tmp_path):
    monkeypatch.setattr(context_inspection, "ROOT", tmp_path)
    workspace, cv, body = sample
    run = core.admit(workspace, cv, "synthetic-context-read", body, pg.execution())
    pg.finalize(sample, run)
    before = core.read_run_id(workspace, cv, run.id)
    token = "synthetic-context-postgres-auth-token"
    client = TestClient(create_app(token, workspace))
    headers = {"Authorization": "Bearer " + token}
    path = f"/v1/conversations/{cv}/runs/{run.id}/context"
    assert client.get(path).status_code == 401
    result = client.get(path, headers=headers)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["availability"] == "NOT_RECORDED"
    assert result.json()["working_state"] is None  # Unavailable is not empty.
    assert core.read_run_id(workspace, cv, run.id) == before
    stranger = TestClient(create_app(token, uuid4()))
    assert stranger.get(path, headers=headers).status_code == 404
    with transaction() as db:
        db.get(KnowledgeBaseRow, body.scope.kb_id).workspace_id = uuid4()
    assert client.get(path, headers=headers).status_code == 404


def test_corrupt_local_receipt_has_explicit_unverifiable_status(sample, monkeypatch, tmp_path):
    monkeypatch.setattr(context_inspection, "ROOT", tmp_path)
    workspace, cv, body = sample
    run = core.admit(workspace, cv, "synthetic-context-corrupt", body, pg.execution())
    pg.finalize(sample, run)
    folder = tmp_path / ".runtime/interpretation-context" / str(run.id)
    folder.mkdir(parents=True)
    (folder / "receipt.json").write_text("{broken", "utf8")
    before = core.read_run_id(workspace, cv, run.id)
    value = context_inspection.observe_context(workspace, cv, run.id)
    assert value.availability == "UNVERIFIABLE" and value.candidates is None
    assert core.read_run_id(workspace, cv, run.id) == before


def test_verified_phase_binding_and_non_text_receipt_remain_read_only(evidence_case, monkeypatch, tmp_path):
    from citeweave import history_relevance

    prompt = (ROOT / "prompts/conversation-interpretation-relevance-v1.txt").read_bytes()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/conversation-interpretation-relevance-v1.txt").write_bytes(prompt)
    monkeypatch.setattr(history_relevance, "ROOT", tmp_path)
    monkeypatch.setattr(context_inspection, "ROOT", tmp_path)
    monkeypatch.setenv("CW_INTERPRETATION_CONTEXT_RECEIPTS", "1")
    sample, fixture = evidence_case
    response = json.dumps(dict(topic_relation="continue", dependency="none", relevant_sources=[]))
    # The production adapter and phase ledger run against real isolated PG.
    # HTTP transport and document/model fixtures are explicitly synthetic.
    value, run, calls = runtime(evidence_case, monkeypatch, draft=False, response=response)
    value.retriever = SimpleNamespace(retrieve=lambda *args: fixture.material(empty=True))
    value.execute(sample[0], run)
    assert len(calls) == 1
    token = "synthetic-context-verified-http-token"
    client = TestClient(create_app(token, sample[0]))
    headers = {"Authorization": "Bearer " + token}
    path = f"/v1/conversations/{sample[1]}/runs/{run.id}/context"
    before = core.read_run_id(*sample[:2], run.id)
    verified = client.get(path, headers=headers)
    assert verified.status_code == 200
    assert verified.json()["availability"] == "VERIFIED_LOCAL_RECEIPT"
    assert verified.json()["candidates"] == []
    receipt_path = tmp_path / ".runtime/interpretation-context" / str(run.id) / "receipt.json"
    receipt = json.loads(receipt_path.read_text("utf8"))
    receipt["raw_interpretation_response"] = {"invalid": "non-text response"}
    receipt_path.write_text(json.dumps(receipt), "utf8")
    invalid = client.get(path, headers=headers)
    assert invalid.status_code == 200
    assert invalid.json()["availability"] == "UNVERIFIABLE"
    assert invalid.json()["candidates"] is None
    assert core.read_run_id(*sample[:2], run.id) == before and len(calls) == 1
