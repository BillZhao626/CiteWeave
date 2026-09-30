"""HTTP against UUID-isolated real PostgreSQL; deterministic runtime only."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
import test_conversation_evidence_postgres as evidence_pg
import test_conversation_postgres as pg
from conversation_evidence_fixtures import FakeGenerator, FakeModel, require_isolated_database
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_conversation_api import client

from citeweave import conversations as core
from citeweave.conversation_contract import ResolvedSignals, RunStatus, StateValue
from citeweave.conversation_evidence import execute
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_history import HistoryQuery
from citeweave.conversation_history_pg import LocalHistoryRead
from citeweave.conversation_interpretation import IntentFact, InterpretationDraft, RetrievalRewrite
from citeweave.conversation_models import ConversationAcceptanceRow as Accepted
from citeweave.conversation_models import ConversationRunRow as Run
from citeweave.conversation_public import AcceptedResult, ConversationEvent, ConversationTrace
from citeweave.db import engine, transaction
from citeweave.domain import KnowledgeBaseRow

isolated_pg = pg.isolated_pg
evidence_case = evidence_pg.evidence_case
pytestmark = pg.pytestmark


class Runtime:
    def __init__(self, fixture, kind="documentary_answer", draft=None, explicit=()):
        self.fixture, self.kind = fixture, kind
        self.draft, self.explicit = draft, explicit
        self.calls = 0
        self.generator = FakeGenerator()

    def prepare(self):
        return pg.execution()  # Synthetic test deadline only; no product default.

    def execute(self, workspace, run):
        self.calls += 1
        if self.kind == "pending":
            return
        if self.kind == "failed":
            core.finish(workspace, run.conversation_id, run.turn_id, run.id, run.owner, run.fence, "FAILED")
            return
        if self.kind == "exception":
            raise RuntimeError("raw-provider secret private-prompt must-never-appear")
        body, _ = core.execution_input(workspace, run)
        execute(
            workspace,
            run,
            HistoryQuery(scope=body.scope, expected_head=body.expected_head, explicit=self.explicit),
            draft=self.draft
            or InterpretationDraft(
                topic_relation="continue",
                dependency="unresolved" if self.kind == "clarification" else "none",
            ),
            retriever=StructuralEvidenceRetriever(
                model=FakeModel(),
                branch_query=(lambda *args: [])
                if self.kind == "evidence_insufficient"
                else self.fixture.branch,
            ),
            generator=self.generator,
            max_input_bytes=131072,
            permit=LocalHistoryRead(),
        )
        if self.kind == "lost_receipt":
            raise RuntimeError("synthetic lost receipt after commit")


def paths(sample):
    return f"/v1/conversations/{sample[1]}"


def submit(api, sample, key="answer", **updates):
    body = sample[2].model_dump(mode="json", exclude={"profile"})
    body.update(updates)
    return api.post(paths(sample) + "/turns", json=body, headers={"Idempotency-Key": key})


def test_create_read_replay_and_workspace_isolation(evidence_case):
    sample, _ = evidence_case
    api = client(sample[0])
    created = api.post("/v1/conversations")
    assert created.status_code == 200
    assert api.post("/v1/conversations").json() == created.json()
    path = "/v1/conversations/" + created.json()["id"]
    assert api.get(path).json() == created.json()
    assert client().get(path).status_code == 404


def test_default_runtime_fail_closed_and_no_durable_admission(evidence_case):
    sample, _ = evidence_case
    response = submit(client(sample[0]), sample)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "conversation_runtime_unavailable"
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(Run).where(Run.conversation_id == sample[1])) == 0
    assert core.read_conversation(*sample[:2]).active is None


@pytest.mark.parametrize("kind", ["clarification", "evidence_insufficient", "documentary_answer"])
def test_result_trace_roundtrip_reconnect_and_events(evidence_case, kind):
    sample, fixture = evidence_case
    runtime = Runtime(fixture, kind)
    api = client(sample[0], runtime)
    response = submit(api, sample)
    assert response.status_code == 200
    value = response.json()
    result = value["accepted"]
    assert result["result"]["kind"] == kind
    assert AcceptedResult.model_validate(result).model_dump(mode="json") == result
    root = paths(sample) + "/runs/" + value["id"]
    engine().dispose()
    fresh = client(sample[0])  # Runtime unavailable; durable read/replay still works.
    assert fresh.get(root).json() == value
    assert submit(fresh, sample).json() == value
    assert runtime.calls == 1
    assert fresh.get(root + "/result").json() == result
    assert fresh.get(paths(sample)).json()["head_id"] == result["acceptance_id"]
    trace = fresh.get(root + "/trace").json()
    assert ConversationTrace.model_validate(trace).model_dump(mode="json") == trace
    assert trace["acceptance_id"] == trace["output_state_id"] == result["acceptance_id"]
    assert trace["semantic_support"] == "NOT_ASSESSED"
    if kind == "clarification":
        assert trace["metadata_availability"] == "control_bundle"
        assert trace["interpretation_mode"] is None and trace["selected_query"] is None
        assert trace["evidence_ids"] is None and not runtime.generator.inputs
    else:
        assert trace["interpretation_mode"] == "USE_ORIGINAL"
        assert trace["selected_query"] == sample[2].question
        assert trace["history_sources"] == trace["input_state_item_ids"] == []
        assert trace["validation"] == "CURRENT_PACK_PHYSICAL_ONLY"
        assert trace["documents"] == [
            {"document_id": str(fixture.document), "document_version_id": str(fixture.version)}
        ]
        if kind == "documentary_answer":
            assert result["result"]["citations"] == [fixture.citation.model_dump(mode="json")]
            assert trace["evidence_ids"] == [str(fixture.citation.evidence_id)]
        else:
            assert trace["evidence_ids"] == trace["citations"] == []
    stream = fresh.get(root + "/events")
    assert stream.headers["content-type"].startswith("text/event-stream")
    events = [ConversationEvent.model_validate_json(line[6:]) for line in stream.text.splitlines() if line]
    assert [v.event.type for v in events] == ["lifecycle", "result"]
    assert events[1].event.accepted.model_dump(mode="json") == result
    assert fresh.get(root).json() == value  # Observation never cancels/changes it.


def test_idempotency_head_busy_and_valid_followup(evidence_case):
    sample, fixture = evidence_case
    runtime = Runtime(fixture, "pending")
    api = client(sample[0], runtime)
    first = submit(api, sample)
    assert first.status_code == 202 and first.json()["accepted"] is None
    assert submit(api, sample).json() == first.json()
    for key, updates, code in (
        ("answer", {"question": "changed"}, "idempotency_conflict"),
        ("other", {"expected_head": str(uuid4())}, "head_conflict"),
        ("other", {}, "conversation_busy"),
    ):
        conflict = submit(api, sample, key, **updates)
        assert conflict.status_code == 409 and conflict.json()["error"]["code"] == code
    run = core.read_run(*sample[:2], "answer").run
    Runtime(fixture).execute(sample[0], run)
    assert submit(api, sample).json()["status"] == "ACCEPTED"
    assert submit(api, sample, "stale").json()["error"]["code"] == "head_conflict"
    head = core.read_conversation(*sample[:2]).head.id
    next_response = submit(api, sample, "followup", expected_head=str(head))
    assert next_response.status_code == 202 and next_response.json()["expected_head"] == str(head)
    assert runtime.calls == 2


@pytest.mark.parametrize("kind", ["pending", "failed", "exception"])
def test_no_accepted_result_for_pending_or_failed_and_no_error_payload(evidence_case, kind):
    sample, fixture = evidence_case
    runtime = Runtime(fixture, kind)
    api = client(sample[0], runtime)
    response = submit(api, sample)
    assert response.status_code == {"pending": 202, "failed": 200, "exception": 503}[kind]
    assert "raw-provider" not in response.text and "private-prompt" not in response.text
    read = core.read_run(*sample[:2], "answer")
    root = paths(sample) + "/runs/" + str(read.run.id)
    assert api.get(root).json()["accepted"] is None
    assert api.get(root + "/result").status_code == 409
    trace = api.get(root + "/trace").json()
    assert trace["metadata_availability"] == "no_accepted_bundle"
    assert trace["acceptance_id"] is None and trace["validation"] is None
    assert submit(api, sample).status_code in (200, 202) and runtime.calls == 1


@pytest.mark.parametrize("suffix", ["", "/result", "/trace", "/events"])
def test_read_authorization_conversation_and_scope_isolation(evidence_case, suffix):
    sample, fixture = evidence_case
    api = client(sample[0], Runtime(fixture))
    identity = submit(api, sample).json()["id"]
    root = paths(sample) + "/runs/" + identity
    assert client().get(root + suffix).status_code == 404
    other = core.create(sample[0], "other")
    assert api.get(f"/v1/conversations/{other.id}/runs/{identity}" + suffix).status_code == 404
    with transaction() as db:
        db.get(KnowledgeBaseRow, fixture.scope.kb_id).workspace_id = uuid4()
    assert api.get(root + suffix).status_code == 404


def test_submit_rejects_cross_workspace_and_scope_before_runtime(evidence_case):
    sample, fixture = evidence_case
    runtime = Runtime(fixture)
    assert submit(client(uuid4(), runtime), sample).status_code == 404
    forged = {"kb_id": str(uuid4()), "version_ids": [str(fixture.version)]}
    assert submit(client(sample[0], runtime), sample, scope=forged).status_code == 404
    assert runtime.calls == 0


def test_lost_response_replay_recovers_single_acceptance(evidence_case):
    sample, fixture = evidence_case
    runtime = Runtime(fixture, "lost_receipt")
    api = client(sample[0], runtime)
    assert submit(api, sample).status_code == 503
    engine().dispose()
    replay = submit(client(sample[0]), sample)
    assert replay.status_code == 200 and replay.json()["accepted"]
    assert runtime.calls == 1
    with transaction() as db:
        assert (
            db.scalar(select(func.count()).select_from(Accepted).where(Accepted.conversation_id == sample[1]))
            == 1
        )


def test_failed_transaction_no_partial_trace_or_result(evidence_case):
    sample, fixture = evidence_case

    def abort(session):
        if any(isinstance(row, Accepted) for row in session.identity_map.values()):
            raise RuntimeError("synthetic acceptance rollback")

    api = client(sample[0], Runtime(fixture))
    event.listen(Session, "before_commit", abort)
    try:
        assert submit(api, sample).status_code == 503
    finally:
        event.remove(Session, "before_commit", abort)
    read = core.read_run(*sample[:2], "answer")
    root = paths(sample) + "/runs/" + str(read.run.id)
    assert api.get(root).json()["accepted"] is None
    assert api.get(root + "/trace").json()["evidence_pack_identity"] is None
    assert api.get(paths(sample)).json()["head_id"] is None


def test_http_read_waits_for_atomic_acceptance(evidence_case):
    sample, fixture = evidence_case
    run = core.admit(*sample[:2], "answer", sample[2], pg.execution())
    flushed, release, reading = Event(), Event(), Event()

    def pause(session, _):
        if any(isinstance(row, Accepted) for row in session.new):
            flushed.set()
            assert release.wait(10)

    def read():
        reading.set()
        return client(sample[0]).get(paths(sample) + "/runs/" + str(run.id))

    event.listen(Session, "after_flush", pause)
    try:
        with ThreadPoolExecutor(2) as pool:
            writer = pool.submit(Runtime(fixture).execute, sample[0], run)
            assert flushed.wait(10)
            reader = pool.submit(read)
            assert reading.wait(5)
            assert not reader.done()
            release.set()
            writer.result(timeout=10)
            value = reader.result(timeout=10).json()
            assert value["status"] == "ACCEPTED" and value["accepted"]
    finally:
        release.set()
        event.remove(Session, "after_flush", pause)


def test_failed_attempt_never_exposes_successful_retry_as_its_result(evidence_case):
    sample, fixture = evidence_case
    api = client(sample[0], Runtime(fixture, "failed"))
    original = submit(api, sample).json()
    retried = core.retry(
        *sample[:2], UUID(original["turn_id"]), UUID(original["id"]), "retry", pg.execution()
    )
    Runtime(fixture).execute(sample[0], retried)
    root = paths(sample) + "/runs/" + original["id"]
    assert api.get(root).json()["accepted"] is None
    assert api.get(root + "/trace").json()["acceptance_id"] is None
    assert api.get(root + "/result").status_code == 409
    assert api.get(paths(sample) + "/runs/" + str(retried.id)).json()["accepted"]["run_id"] == str(retried.id)


def test_rewrite_trace_exact_durable_history_state_without_historical_text(evidence_case):
    sample, fixture = evidence_case
    item = StateValue(id=uuid4(), kind="entity", key="receiver", value="receiver")
    previous = pg.history_accept(
        sample,
        put=(item,),
        signals=ResolvedSignals(entities=("receiver",)),
        question="Unrelated historical text must not be copied into Trace",
    )
    question = "What does it do?"
    draft = InterpretationDraft(
        topic_relation="continue",
        dependency="required",
        facts=(
            IntentFact(kind="entity", value="receiver", source=previous.state.source, state_item_id=item.id),
        ),
        rewrite=RetrievalRewrite(text=question + "\nreceiver", scope=sample[2].scope),
    )
    runtime = Runtime(fixture, draft=draft, explicit=(previous.state.source,))
    api = client(sample[0], runtime)
    response = submit(api, sample, question=question, expected_head=str(previous.id))
    assert response.status_code == 200
    root = paths(sample) + "/runs/" + response.json()["id"]
    trace = api.get(root + "/trace")
    value = trace.json()
    assert value["interpretation_mode"] == "USE_REWRITE"
    assert value["selected_query"] == draft.rewrite.text
    assert value["history_sources"] == [previous.state.source.model_dump(mode="json")]
    assert value["input_state_item_ids"] == [str(item.id)]
    assert "Unrelated historical text" not in trace.text
    durable = core.read_run(*sample[:2], "answer").accepted.result.trace
    assert value["interpretation_identity"] == durable.interpretation_identity
    assert value["evidence_pack_identity"] == durable.evidence_identity


def test_stale_run_cannot_publish_after_head_moves(evidence_case):
    sample, fixture = evidence_case
    prepared = evidence_pg.prepare(evidence_case)
    core.finish(*pg.finish_args(sample, prepared[0]), RunStatus.CANCELLED)
    response = submit(client(sample[0], Runtime(fixture)), sample, "new")
    assert response.status_code == 200
    with pytest.raises(ValueError, match="head_conflict"):
        evidence_pg.accept(evidence_case, prepared)
    root = paths(sample) + "/runs/" + str(prepared[0].id)
    assert client(sample[0]).get(root + "/result").status_code == 409


def test_isolation_fixture_is_registered():
    with engine().connect() as connection:
        require_isolated_database(connection)


def test_concurrent_replay_dispatches_once(evidence_case):
    sample, fixture = evidence_case
    runtime = Runtime(fixture, "pending")
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(submit, client(sample[0], runtime), sample) for _ in range(2)]
        responses = [future.result(timeout=15) for future in futures]
    assert all(response.status_code == 202 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert runtime.calls == 1


def test_public_projection_does_not_export_internal_answer_metadata(evidence_case):
    sample, fixture = evidence_case

    class Generator(FakeGenerator):
        def generate(self, context):
            answer = super().generate(context)
            answer.usage = {"raw_provider": "private-payload-sentinel", "reasoning": "hidden-sentinel"}
            answer.prompt_version = "private-prompt-sentinel"
            return answer

    runtime = Runtime(fixture)
    runtime.generator = Generator()
    api = client(sample[0], runtime)
    response = submit(api, sample)
    assert response.status_code == 200
    root = paths(sample) + "/runs/" + response.json()["id"]
    for suffix in ("", "/result", "/trace", "/events"):
        text = api.get(root + suffix).text
        for forbidden in (
            "private-payload-sentinel",
            "hidden-sentinel",
            "private-prompt-sentinel",
            '"usage"',
            '"prompt_version"',
            '"raw_provider"',
            '"owner"',
            '"fence"',
        ):
            assert forbidden not in text


def test_control_insufficiency_has_no_fabricated_documentary_trace(evidence_case):
    from citeweave.conversation_contract import ProducedResult, StateSnapshot

    sample, _ = evidence_case
    run = core.admit(*sample[:2], "control", sample[2], pg.execution())
    core.accept(
        *pg.finish_args(sample, run),
        ProducedResult(kind="evidence_insufficient", text="Original control result"),
        StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=None),
    )
    api = client(sample[0])
    root = paths(sample) + "/runs/" + str(run.id)
    assert api.get(root + "/result").json()["result"]["kind"] == "evidence_insufficient"
    trace = api.get(root + "/trace").json()
    assert trace["metadata_availability"] == "control_bundle"
    assert trace["evidence_pack_identity"] is None and trace["selected_query"] is None
