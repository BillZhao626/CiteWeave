"""UUID-isolated PostgreSQL inspection proof; all execution fixtures are synthetic."""

from uuid import uuid4

import pytest
import test_conversation_postgres as pg
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from citeweave import conversations as core
from citeweave.api import create_app
from citeweave.conversation_contract import (
    ProducedResult,
    ResolvedConversationDelta,
    ResolvedSignals,
    StateSnapshot,
)
from citeweave.db import transaction
from citeweave.domain import KnowledgeBaseRow
from citeweave.runtime_inspection import inspection_view, list_runs

isolated_pg = pg.isolated_pg
sample = pg.sample
pytestmark = pg.pytestmark


def test_published_bundle_and_advanced_head_are_coherent_and_reads_preserve_facts(sample):
    workspace, conversation_id, body = sample
    first = core.admit(workspace, conversation_id, "first", body, pg.execution())
    accepted = core.accept(
        *pg.finish_args(sample, first),
        ProducedResult(kind="clarification", text="Original synthetic clarification"),
        StateSnapshot(source_turn_id=first.turn_id, previous_snapshot_id=None),
        delta=ResolvedConversationDelta(
            source_turn_id=first.turn_id,
            previous_snapshot_id=None,
            signals=ResolvedSignals(topic="Original synthetic topic"),
        ),
    )
    value = inspection_view(core.read_run_id(workspace, conversation_id, first.id))
    assert value.publication.head_relation == "CURRENT"
    assert value.run.accepted.acceptance_id == value.publication.working_state.snapshot_id == accepted.id
    assert value.publication.conversation_head_id == accepted.id
    assert value.publication.working_state.topic_signal == "Original synthetic topic"
    assert value.publication.working_state.active_entries == 0
    second = core.admit(
        workspace,
        conversation_id,
        "second",
        body.model_copy(update={"expected_head": accepted.id}),
        pg.execution(),
    )
    newer = core.accept(
        *pg.finish_args(sample, second),
        ProducedResult(kind="clarification", text="Second original clarification"),
        StateSnapshot(source_turn_id=second.turn_id, previous_snapshot_id=accepted.id),
        delta=ResolvedConversationDelta(source_turn_id=second.turn_id, previous_snapshot_id=accepted.id),
    )
    before = core.read_run_id(workspace, conversation_id, first.id)
    historical = inspection_view(before)
    assert historical.publication.head_relation == "ADVANCED"
    assert historical.publication.acceptance_id == accepted.id
    assert historical.publication.conversation_head_id == newer.id
    assert historical.publication.decision == "PUBLISHED"
    assert len(list_runs(workspace, 25, 0)) == 2
    assert core.read_run_id(workspace, conversation_id, first.id) == before


def test_failed_attempt_never_inherits_retry_acceptance_and_legacy_state_is_not_invented(sample):
    workspace, conversation_id, body = sample
    failed = core.admit(workspace, conversation_id, "failed", body, pg.execution())
    core.finish(*pg.finish_args(sample, failed), "FAILED")
    retry = core.retry(workspace, conversation_id, failed.turn_id, failed.id, "retry", pg.execution())
    accepted = pg.finalize(sample, retry)
    prior = inspection_view(core.read_run_id(workspace, conversation_id, failed.id))
    assert prior.publication.decision == "NOT_PUBLISHED"
    assert prior.run.accepted is None and prior.publication.working_state is None
    assert prior.publication.acceptance_id is None
    assert prior.publication.conversation_head_id == accepted.id
    current = inspection_view(core.read_run_id(workspace, conversation_id, retry.id))
    assert current.publication.working_state.revision == "conversation-core-v1"
    assert current.publication.working_state.active_entries is None
    assert current.publication.working_state.topic_signal is None


def test_unknown_readback_is_unpublished_and_does_not_redispatch_or_reconcile(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "unknown", body, pg.execution())
    core.finish(*pg.finish_args(sample, run), "UNKNOWN", error_class="original_unknown_failure")
    before = core.read_run_id(workspace, conversation_id, run.id)
    value = inspection_view(before)
    assert value.trace.operational.retry_decision == "BLOCKED_UNKNOWN"
    assert value.trace.operational.unknown_reason == "LEGACY_REASON_UNAVAILABLE"
    assert value.publication.decision == "NOT_PUBLISHED" and value.publication.acceptance_id is None
    assert value.publication.conversation_head_id is None
    summaries = list_runs(workspace, 25, 0)
    assert summaries[0].reason_code == "original_unknown_failure"
    assert core.read_run_id(workspace, conversation_id, run.id) == before


def test_http_ownership_fixed_version_scope_and_bounded_catalog(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "original-http", body, pg.execution())
    token = "synthetic-inspection-auth-token"
    path = f"/v1/conversations/{conversation_id}/runs/{run.id}/inspection"
    client = TestClient(create_app(token, workspace))
    headers = {"Authorization": "Bearer " + token}
    assert client.get(path).status_code == 401
    assert client.get("/v1/runtime/conversation-runs").status_code == 401
    response = client.get(path, headers=headers)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert not {"owner", "fence", "key", "authorization_id"} & response.json()["run"].keys()
    assert client.get("/v1/runtime/conversation-runs?limit=26", headers=headers).status_code == 422
    assert client.get("/v1/runtime/conversation-runs?offset=-1", headers=headers).status_code == 422
    assert client.get("/v1/runtime/conversation-runs?offset=1", headers=headers).json() == []
    stranger = TestClient(create_app(token, uuid4()))
    assert stranger.get(path, headers=headers).status_code == 404
    assert stranger.get("/v1/runtime/conversation-runs", headers=headers).json() == []
    with transaction() as db:
        db.get(KnowledgeBaseRow, body.scope.kb_id).workspace_id = uuid4()
    assert client.get(path, headers=headers).status_code == 404
    with pytest.raises(HTTPException):
        list_runs(workspace, 25, 0)
    with transaction() as db:
        assert db.scalar(select(pg.Run.status).where(pg.Run.id == run.id)) == "ADMITTED"
