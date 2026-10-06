"""Real isolated PG, original atoms, fake embedding/BGE/branch/generation only."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event
from uuid import uuid4

import pytest
import test_conversation_postgres as pg
from conversation_evidence_fixtures import FakeGenerator, FakeModel, Fixture, require_isolated_database
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from test_conversation_postgres import (
    execution,
    finish_args,
    history_accept,
    metadata,
)

from citeweave import conversations as core
from citeweave.conversation_contract import (
    Admission,
    CoreConflict,
    DocumentaryResult,
    ResolvedSignals,
    RunStatus,
    StateSnapshot,
    StateValue,
)
from citeweave.conversation_evidence import execute, produce
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_history import HistoryQuery
from citeweave.conversation_history_pg import LocalHistoryRead, read_history
from citeweave.conversation_interpretation import (
    IntentFact,
    InterpretationDraft,
    InterpretationInput,
    RetrievalRewrite,
)
from citeweave.conversation_models import ConversationAcceptanceRow as Accepted
from citeweave.conversation_models import ConversationRow as Conversation
from citeweave.conversation_models import ConversationRunRow as Run
from citeweave.db import engine, transaction
from citeweave.domain import KnowledgeBaseRow, VersionRow

isolated_pg = pg.isolated_pg
pytestmark = pg.pytestmark


@pytest.fixture
def evidence_case():
    with engine().connect() as connection:
        require_isolated_database(connection)
    workspace, scope = metadata()
    with transaction() as db:
        document = db.get(VersionRow, scope.version_ids[0]).document_id
    fixture = Fixture(workspace, scope, document)
    fixture.persist()
    conversation = core.create(workspace, "create")
    body = Admission(question="What does the receiver do?", scope=scope, expected_head=None)
    return (workspace, conversation.id, body), fixture


def draft():
    return InterpretationDraft(topic_relation="continue", dependency="none")


def prepare(evidence_case):
    sample, fixture = evidence_case
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "answer", body, execution())
    history = read_history(
        workspace,
        conversation_id,
        HistoryQuery(scope=body.scope, expected_head=body.expected_head),
        permit=LocalHistoryRead(),
    )
    context = InterpretationInput(
        conversation_id=conversation_id, turn_id=run.turn_id, request=body, history=history
    )
    result, decision = produce(
        workspace,
        run.id,
        context,
        draft=draft(),
        retriever=StructuralEvidenceRetriever(model=FakeModel(), branch_query=fixture.branch),
        generator=FakeGenerator(),
        max_input_bytes=131072,
    )
    return run, context, result, decision


def accept(evidence_case, prepared, *, result=None, delta=None):
    sample, _ = evidence_case
    run, context, produced, decision = prepared
    return core.accept(
        *finish_args(sample, run),
        result or produced,
        StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=run.expected_head),
        delta=delta or decision.delta,
        interpretation=(context, draft()),
    )


def test_documentary_real_rag_atomic_readback_and_lost_receipt(evidence_case):
    sample, fixture = evidence_case
    prepared = prepare(evidence_case)
    accepted = accept(evidence_case, prepared)
    engine().dispose()  # Reconnect; readback must use durable truth.
    truth = core.read_run(*sample[:2], "answer")
    assert truth.accepted == accepted and truth.conversation.head == accepted
    assert truth.run.status == "ACCEPTED" and truth.conversation.active is None
    assert accepted.result.answer.citations == [fixture.citation]
    assert accepted.state.source.acceptance_id == accepted.id
    assert DocumentaryResult.model_validate(accepted.result.model_dump(mode="json")) == accepted.result
    with pytest.raises(CoreConflict, match="already_accepted"):
        accept(evidence_case, prepared)
    with transaction() as db:
        assert len(list(db.scalars(select(Accepted).where(Accepted.turn_id == prepared[0].turn_id)))) == 1


def test_large_documentary_result_is_excluded_before_history_byte_cap(evidence_case):
    """Synthetic isolated persisted bundle follows the observed Citation/boxes shape.

    Geometry expansion is fixture setup, not a real accepted-run mutation or a
    claim that duplicated geometry would pass the production evidence validator.
    """
    import json

    from citeweave.conversation_history import MAX_BYTES, AcceptedHistory

    sample, _ = evidence_case
    prepared = prepare(evidence_case)
    result = prepared[2].model_dump(mode="json")
    span = result["answer"]["citations"][0]["span"]
    span["boxes"] = span["boxes"] * 6000

    # Insert an original synthetic large-row fixture; immutable rows are never
    # updated and the production immutability trigger stays enabled.
    def large_fixture(session, flush_context, instances):
        for row in session.new:
            if isinstance(row, Accepted) and row.run_id == prepared[0].id:
                row.result = result

    event.listen(Session, "before_flush", large_fixture)
    try:
        accepted = accept(evidence_case, prepared)
    finally:
        event.remove(Session, "before_flush", large_fixture)
    before = json.dumps(result, sort_keys=True)
    query = HistoryQuery(scope=sample[2].scope, expected_head=accepted.id, explicit=(accepted.state.source,))
    selected = read_history(*sample[:2], query, permit=LocalHistoryRead())
    assert len(before.encode()) > 206083 > MAX_BYTES
    assert selected.failure is None and selected.materialized_rows == 1
    assert selected.payload_bytes < 4096 < MAX_BYTES
    source = selected.selected[0].sources[0]
    assert isinstance(source.acceptance, AcceptedHistory)
    assert source.ref == accepted.state.source
    assert source.request.scope == sample[2].scope
    assert source.acceptance.state == accepted.state
    wire = source.model_dump_json()
    assert all(
        key not in json.loads(wire)["acceptance"] for key in ["result", "answer", "trace", "evidence_pack"]
    )
    assert '"boxes"' not in wire
    assert selected == read_history(*sample[:2], query, permit=LocalHistoryRead())
    with transaction() as db:
        assert json.dumps(db.get(Accepted, accepted.id).result, sort_keys=True) == before


def test_documentary_invisible_until_transaction_commits(evidence_case):
    prepared = prepare(evidence_case)
    flushed, release = Event(), Event()

    def pause(session, _):
        if any(isinstance(row, Accepted) for row in session.new):
            flushed.set()
            assert release.wait(5)

    event.listen(Session, "after_flush", pause)
    try:
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(accept, evidence_case, prepared)
            assert flushed.wait(5)
            with engine().connect() as connection:
                row = connection.execute(
                    text("""
                    SELECT c.head_id, a.result, a.state, r.status FROM cw5_conversations c
                    JOIN cw5_runs r ON r.conversation_id=c.id
                    LEFT JOIN cw5_acceptances a ON a.run_id=r.id WHERE c.id=:id
                """),
                    {"id": evidence_case[0][1]},
                ).one()
                assert tuple(row) == (None, None, None, "ADMITTED")
            release.set()
            assert future.result(timeout=10).result.kind == "documentary_answer"
    finally:
        release.set()
        event.remove(Session, "after_flush", pause)


def test_documentary_precommit_rollback_has_no_partial_result(evidence_case):
    prepared = prepare(evidence_case)

    def abort(session):
        if any(isinstance(row, Accepted) for row in session.identity_map.values()):
            raise RuntimeError("synthetic precommit loss")

    event.listen(Session, "before_commit", abort)
    try:
        with pytest.raises(RuntimeError, match="precommit"):
            accept(evidence_case, prepared)
    finally:
        event.remove(Session, "before_commit", abort)
    truth = core.read_run(*evidence_case[0][:2], "answer")
    assert truth.accepted is None and truth.conversation.head is None and truth.unfinished
    assert accept(evidence_case, prepared).result.kind == "documentary_answer"


@pytest.mark.parametrize(
    "fault",
    [
        "owner",
        "fence",
        "deadline",
        "head",
        "cancel",
        "delta",
        "scope",
        "source",
        "old_run",
        "document",
        "pack",
        "interpretation",
    ],
)
def test_documentary_commit_guards_reject_and_publish_nothing(evidence_case, fault):
    sample, fixture = evidence_case
    prepared = prepare(evidence_case)
    run, context, result, decision = prepared
    with transaction() as db:
        if fault == "owner":
            db.get(Run, run.id).owner = uuid4()
        elif fault == "fence":
            db.get(Conversation, run.conversation_id).fence += 1
        elif fault == "deadline":
            db.get(Run, run.id).deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        elif fault == "scope":
            db.get(KnowledgeBaseRow, fixture.scope.kb_id).workspace_id = uuid4()
    if fault == "head":
        context = context.model_copy(
            update={"request": context.request.model_copy(update={"expected_head": uuid4()})}
        )
    elif fault == "cancel":
        core.finish(*finish_args(sample, run), RunStatus.CANCELLED)
    elif fault == "delta":
        decision = decision.model_copy(
            update={"delta": decision.delta.model_copy(update={"deactivate": (uuid4(),)})}
        )
    elif fault == "old_run":
        result.answer.run_id = uuid4()
    elif fault == "document":
        result.snapshot.bindings[0].document_id = str(uuid4())
    elif fault == "pack":
        result.evidence_pack.spans[0].evidence_id = str(uuid4())
    elif fault == "interpretation":
        result = result.model_copy(
            update={"trace": result.trace.model_copy(update={"selected_query": "forged query"})}
        )
    elif fault == "source":
        result.answer.citations[0].span = result.answer.citations[0].span.model_copy(
            update={"quote": "forged"}
        )
    from fastapi import HTTPException

    with pytest.raises((ValueError, HTTPException)):
        accept(evidence_case, (run, context, result, decision))
    with transaction() as db:
        assert db.scalar(select(Accepted).where(Accepted.turn_id == run.turn_id)) is None
        assert db.get(Conversation, run.conversation_id).head_id is None


def test_documentary_retry_rejects_previous_run_answer(evidence_case):
    prepared = prepare(evidence_case)
    sample, _ = evidence_case
    run, context, result, decision = prepared
    core.finish(*finish_args(sample, run), RunStatus.FAILED)
    retried = core.retry(*sample[:2], run.turn_id, run.id, "retry", execution())
    with pytest.raises(CoreConflict, match="answer_identity"):
        accept(evidence_case, (retried, context, result, decision))
    with pytest.raises(CoreConflict, match="run_not_active"):
        accept(evidence_case, prepared)
    fixture = evidence_case[1]
    fresh_result, fresh_decision = produce(
        sample[0],
        retried.id,
        context,
        draft=draft(),
        retriever=StructuralEvidenceRetriever(model=FakeModel(), branch_query=fixture.branch),
        generator=FakeGenerator(),
        max_input_bytes=131072,
    )
    accepted = accept(evidence_case, (retried, context, fresh_result, fresh_decision))
    assert core.read_run(*sample[:2], "answer").accepted == accepted
    assert core.read_run(*sample[:2], "retry").accepted == accepted


def test_full_execute_reads_existing_history_rewrites_and_accepts(evidence_case):
    sample, fixture = evidence_case
    item = StateValue(id=uuid4(), kind="entity", key="receiver", value="receiver")
    previous = history_accept(sample, put=(item,), signals=ResolvedSignals(entities=("receiver",)))
    workspace, conversation_id, body = sample
    body = body.model_copy(update={"expected_head": previous.id, "question": "What does it do?"})
    run = core.admit(workspace, conversation_id, "rewrite", body, execution())
    resolved = InterpretationDraft(
        topic_relation="continue",
        dependency="required",
        facts=(
            IntentFact(kind="entity", value="receiver", source=previous.state.source, state_item_id=item.id),
        ),
        rewrite=RetrievalRewrite(text=body.question + "\nreceiver", scope=body.scope),
    )
    generator = FakeGenerator()
    accepted = execute(
        workspace,
        run,
        HistoryQuery(scope=body.scope, expected_head=previous.id, explicit=(previous.state.source,)),
        draft=resolved,
        retriever=StructuralEvidenceRetriever(model=FakeModel(), branch_query=fixture.branch),
        generator=generator,
        max_input_bytes=131072,
        permit=LocalHistoryRead(),
    )
    assert accepted.result.trace.selected_query == resolved.rewrite.text
    assert accepted.result.trace.state_item_ids == (item.id,)
    assert generator.inputs[0].working_state[0].item == item
    assert accepted.state.previous_snapshot_id == previous.id


def test_execute_production_history_stays_disabled(evidence_case):
    sample, fixture = evidence_case
    run = core.admit(*sample[:2], "disabled", sample[2], execution())
    with pytest.raises(CoreConflict, match="history_unavailable"):
        execute(
            sample[0],
            run,
            HistoryQuery(scope=fixture.scope, expected_head=None),
            draft=draft(),
            retriever=fixture,
            generator=FakeGenerator(),
            max_input_bytes=131072,
        )
    assert not fixture.calls


def test_execute_clarification_skips_documentary_adapters(evidence_case):
    sample, fixture = evidence_case
    run = core.admit(*sample[:2], "clarify", sample[2], execution())
    generator = FakeGenerator()
    accepted = execute(
        sample[0],
        run,
        HistoryQuery(scope=fixture.scope, expected_head=None),
        draft=InterpretationDraft(topic_relation="continue", dependency="unresolved"),
        retriever=fixture,
        generator=generator,
        max_input_bytes=131072,
        permit=LocalHistoryRead(),
    )
    assert accepted.result.kind == "clarification" and not fixture.calls and not generator.inputs


def test_actual_moved_head_blocks_old_documentary_result(evidence_case):
    prepared = prepare(evidence_case)
    sample, fixture = evidence_case
    core.finish(*finish_args(sample, prepared[0]), RunStatus.CANCELLED)
    run = core.admit(*sample[:2], "new-head", sample[2], execution())
    accepted = execute(
        sample[0],
        run,
        HistoryQuery(scope=fixture.scope, expected_head=None),
        draft=draft(),
        retriever=StructuralEvidenceRetriever(model=FakeModel(), branch_query=fixture.branch),
        generator=FakeGenerator(),
        max_input_bytes=131072,
        permit=LocalHistoryRead(),
    )
    with pytest.raises(CoreConflict, match="head_conflict"):
        accept(evidence_case, prepared)
    assert core.read_conversation(*sample[:2]).head == accepted


def test_frozen_documentary_atoms_cannot_be_modified(evidence_case):
    from sqlalchemy.exc import DBAPIError

    from citeweave.domain import ChunkRow

    fixture = evidence_case[1]
    with pytest.raises(DBAPIError, match="immutable"):
        with transaction() as db:
            db.get(ChunkRow, fixture.atom.id).text = "changed"


def test_no_current_hits_publishes_insufficiency_without_generation(evidence_case):
    sample, fixture = evidence_case
    run = core.admit(*sample[:2], "empty", sample[2], execution())
    generator = FakeGenerator()
    accepted = execute(
        sample[0],
        run,
        HistoryQuery(scope=fixture.scope, expected_head=None),
        draft=draft(),
        retriever=StructuralEvidenceRetriever(model=FakeModel(), branch_query=lambda *args: []),
        generator=generator,
        max_input_bytes=131072,
        permit=LocalHistoryRead(),
    )
    assert accepted.result.kind == "evidence_insufficient" and not generator.inputs
    assert not accepted.result.answer.citations and not accepted.result.evidence_pack.spans
