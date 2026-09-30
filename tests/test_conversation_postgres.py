"""Real PG only. Creates/drops its own UUID-named DB, never migrates the configured DB.

Opt in: CW_RUN_INTEGRATION=1 pytest tests/test_conversation_postgres.py.
No broker, index, model, corpus or provider is contacted by this module.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from citeweave import conversations as core
from citeweave import schemas
from citeweave.conversation_contract import (
    Admission,
    CoreConflict,
    Execution,
    HistoryRelation,
    ProducedResult,
    ResolvedConversationDelta,
    ResolvedSignals,
    Scope,
    SourceRef,
    StateSnapshot,
    StateValue,
)
from citeweave.conversation_history import HistoryQuery
from citeweave.conversation_history_pg import LocalHistoryRead, read_history
from citeweave.conversation_models import (
    ConversationAcceptanceRow as Accepted,
)
from citeweave.conversation_models import (
    ConversationRow as Conversation,
)
from citeweave.conversation_models import (
    ConversationRunRow as Run,
)
from citeweave.db import engine, migrate, transaction
from citeweave.domain import DocumentRow, KnowledgeBaseRow, QueryRunRow, VersionRow
from citeweave.query_evidence import read_query
from citeweave.settings import ROOT, settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("CW_RUN_INTEGRATION"), reason="needs isolated real PostgreSQL; no mock substitute"
    ),
]


@pytest.fixture(scope="module", autouse=True)
def isolated_pg():
    from sqlalchemy.engine import make_url

    config = settings()
    original = config.database_url
    url = make_url(config.db_url())
    assert url.host in {"127.0.0.1", "localhost", "::1"}, "local PostgreSQL required"
    database = "cw_conversation_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text('CREATE DATABASE "' + database + '"'))
        created = True
        engine.cache_clear()
        config.database_url = SecretStr(url.set(database=database).render_as_string(hide_password=False))
        cfg = Config(str(ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(cfg, "0008")
        # Persist a real v0.1 reader record before applying the additive migration.
        workspace, scope = metadata()
        legacy = uuid4()
        with transaction() as db:
            db.add(
                QueryRunRow(
                    id=legacy,
                    workspace_id=workspace,
                    kb_id=scope.kb_id,
                    key="legacy",
                    fingerprint="0" * 64,
                    question="Original legacy question",
                    status="FAILED",
                )
            )
        with transaction() as db:
            before = schemas.Run.model_validate(read_query(db.get(QueryRunRow, legacy))).model_dump(
                mode="json"
            )
        migrate()
        migrate()
        yield legacy, before
    finally:
        if created:
            engine().dispose()
            engine.cache_clear()
            config.database_url = original
            with admin.connect() as connection:
                connection.execute(text('DROP DATABASE "' + database + '"'))
        admin.dispose()


def metadata():
    workspace, kb, document, version = (uuid4() for _ in range(4))
    with transaction() as db:
        db.add(
            KnowledgeBaseRow(
                id=kb,
                workspace_id=workspace,
                name="Original synthetic core fixture",
                key=str(kb),
                fingerprint="0" * 64,
            )
        )
        db.flush()
        db.add(DocumentRow(id=document, kb_id=kb, title="Synthetic metadata", active_version_id=version))
        db.flush()
        db.add(
            VersionRow(
                id=version,
                document_id=document,
                kb_id=kb,
                sequence=1,
                filename="synthetic.pdf",
                license="original",
                source_sha256="0" * 64,
                blob_key="0" * 64,
                status="READY",
                profile={},
                key=str(version),
                fingerprint="0" * 64,
            )
        )
    return workspace, Scope(kb_id=kb, version_ids=(version,))


@pytest.fixture
def sample():
    workspace, scope = metadata()
    conversation = core.create(workspace, "create")
    return (
        workspace,
        conversation.id,
        Admission(question="Original synthetic question", scope=scope, expected_head=None),
    )


def execution():
    return Execution(owner=uuid4(), deadline=datetime.now(timezone.utc) + timedelta(minutes=5))


def finish_args(sample, run):
    workspace, conversation_id, _ = sample
    return workspace, conversation_id, run.turn_id, run.id, run.owner, run.fence


def finalize(sample, run):
    return core.accept(
        *finish_args(sample, run),
        ProducedResult(kind="clarification", text="Which source do you mean?"),
        StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=run.expected_head),
    )


def race(first, second):
    barrier = Barrier(2)

    def invoke(fn):
        barrier.wait(timeout=5)
        try:
            return fn()
        except CoreConflict as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke, fn) for fn in (first, second)]
        return [f.result(timeout=15) for f in futures]


def test_upgrade_preserves_legacy_reader_and_schema(isolated_pg):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from citeweave.domain import Base

    legacy, before = isolated_pg
    with transaction() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0010"
        after = schemas.Run.model_validate(read_query(db.get(QueryRunRow, legacy))).model_dump(mode="json")
        assert after == before
        assert db.scalar(select(func.count()).select_from(Conversation)) == 0
    with engine().connect() as connection:
        context = MigrationContext.configure(
            connection,
            opts={
                "include_object": lambda obj, name, type_, reflected, compare_to: (
                    name.startswith("cw5_") if type_ == "table" else True
                )
            },
        )
        assert compare_metadata(context, Base.metadata) == []


def test_concurrent_admission_and_busy(sample):
    workspace, conversation_id, body = sample
    results = race(
        lambda: core.admit(workspace, conversation_id, "a", body, execution()),
        lambda: core.admit(workspace, conversation_id, "b", body, execution()),
    )
    assert sum(not isinstance(r, str) for r in results) == 1
    assert results.count("conversation_busy") == 1
    assert core.read_conversation(workspace, conversation_id).active is not None


def test_concurrent_idempotency_replay_and_conflict(sample):
    workspace, conversation_id, body = sample
    results = race(
        lambda: core.admit(workspace, conversation_id, "same", body, execution()),
        lambda: core.admit(workspace, conversation_id, "same", body, execution()),
    )
    assert results[0].id == results[1].id and results[0].owner == results[1].owner
    changed = body.model_copy(update={"question": "Different question"})
    with pytest.raises(CoreConflict, match="idempotency_conflict"):
        core.admit(workspace, conversation_id, "same", changed, execution())
    assert core.create(workspace, "create").id == conversation_id


def test_duplicate_finalize_and_lost_receipt_readback(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "a", body, execution())
    results = race(lambda: finalize(sample, run), lambda: finalize(sample, run))
    assert results.count("already_accepted") == 1
    accepted = next(r for r in results if not isinstance(r, str))
    # The caller lost the commit receipt: discard the execution engine/pool and reread PG.
    engine().dispose()
    truth = core.read_run(workspace, conversation_id, "a")
    assert truth.accepted.id == accepted.id == truth.conversation.head.id
    assert truth.run.status == "ACCEPTED" and not truth.unfinished and truth.conversation.active is None
    assert core.admit(workspace, conversation_id, "a", body, execution()).id == run.id
    with pytest.raises(CoreConflict, match="already_accepted"):
        finalize(sample, run)


def test_retry_preserves_turn_and_fences_old_owner(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "a", body, execution())
    core.finish(*finish_args(sample, run), "FAILED")
    retried = core.retry(workspace, conversation_id, run.turn_id, run.id, "retry", execution())
    assert retried.turn_id == run.turn_id and retried.id != run.id and retried.fence > run.fence
    assert core.retry(workspace, conversation_id, run.turn_id, run.id, "retry", execution()).id == retried.id
    with pytest.raises(CoreConflict):
        finalize(sample, run)
    with pytest.raises(CoreConflict):
        core.finish(*finish_args(sample, run), "CANCELLED")
    assert core.read_conversation(workspace, conversation_id).active.id == retried.id
    finalize(sample, retried)


def test_unknown_never_redispatches(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "a", body, execution())
    with transaction() as db:
        db.get(Run, run.id).deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    core.finish(*finish_args(sample, run), "UNKNOWN")
    with pytest.raises(CoreConflict, match="retry_not_allowed"):
        core.retry(workspace, conversation_id, run.turn_id, run.id, "retry", execution())
    core.reconcile_expired(workspace, conversation_id)
    assert core.read_run(workspace, conversation_id, "a").run.status == "UNKNOWN"
    assert core.admit(workspace, conversation_id, "a", body, execution()).id == run.id


def test_expiry_is_bounded_idempotent_and_not_socket_death(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "a", body, execution())
    assert core.reconcile_expired(workspace, conversation_id).active.id == run.id
    with transaction() as db:
        db.get(Run, run.id).deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert core.read_run(workspace, conversation_id, "a").deadline_elapsed
    with pytest.raises(CoreConflict, match="deadline_elapsed"):
        finalize(sample, run)
    assert core.reconcile_expired(workspace, conversation_id).active is None
    assert core.reconcile_expired(workspace, conversation_id).active is None
    assert core.read_run(workspace, conversation_id, "a").run.status == "INTERRUPTED"


def test_expected_head_two_connections(sample):
    workspace, conversation_id, body = sample
    stale = core.admit(workspace, conversation_id, "a", body, execution())
    observed, advance = Event(), Event()

    def stale_observer():
        with engine().connect() as connection:
            assert (
                connection.scalar(select(Conversation.head_id).where(Conversation.id == conversation_id))
                is None
            )
            observed.set()
            assert advance.wait(5)
            with pytest.raises(CoreConflict, match="head_conflict"):
                finalize(sample, stale)
            with pytest.raises(CoreConflict, match="head_conflict"):
                core.admit(workspace, conversation_id, "old-head", body, execution())

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(stale_observer)
        assert observed.wait(5)
        core.finish(*finish_args(sample, stale), "CANCELLED")
        winner = core.admit(workspace, conversation_id, "b", body, execution())
        accepted = finalize(sample, winner)
        advance.set()
        future.result(timeout=10)
    assert core.read_conversation(workspace, conversation_id).head.id == accepted.id
    with pytest.raises(CoreConflict, match="head_conflict"):
        core.retry(workspace, conversation_id, stale.turn_id, stale.id, "retry", execution())


def test_atomic_visibility_and_rollback(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "a", body, execution())
    flushed, release = Event(), Event()

    def barrier_after_flush(session, context):
        if any(isinstance(row, Accepted) for row in session.new):
            flushed.set()
            assert release.wait(5)

    event.listen(Session, "after_flush", barrier_after_flush)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(finalize, sample, run)
            assert flushed.wait(5)
            # One SQL statement is one observation snapshot; do not fabricate mixed
            # views by comparing separate READ COMMITTED statements across a commit.
            with engine().connect() as connection:
                row = connection.execute(
                    text("""
                    SELECT c.head_id, a.id, a.state, r.status
                    FROM cw5_conversations c JOIN cw5_runs r ON r.conversation_id = c.id
                    LEFT JOIN cw5_acceptances a ON a.run_id = r.id WHERE c.id = :id
                """),
                    {"id": conversation_id},
                ).one()
                assert tuple(row) == (None, None, None, "ADMITTED")
            release.set()
            accepted = pending.result(timeout=10)
    finally:
        release.set()
        event.remove(Session, "after_flush", barrier_after_flush)
    truth = core.read_run(workspace, conversation_id, "a")
    assert truth.accepted.id == truth.conversation.head.id == accepted.id
    assert truth.accepted.state.source_turn_id == run.turn_id and truth.conversation.active is None

    next_body = body.model_copy(update={"expected_head": accepted.id})
    next_run = core.admit(workspace, conversation_id, "b", next_body, execution())

    def abort_commit(session):
        raise RuntimeError("injected_precommit_loss")

    event.listen(Session, "before_commit", abort_commit)
    try:
        with pytest.raises(RuntimeError, match="injected_precommit_loss"):
            finalize(sample, next_run)
    finally:
        event.remove(Session, "before_commit", abort_commit)
    truth = core.read_run(workspace, conversation_id, "b")
    assert truth.accepted is None and truth.unfinished and truth.conversation.head.id == accepted.id


def test_cancel_commit_race_and_scope_authorization(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "a", body, execution())
    results = race(lambda: finalize(sample, run), lambda: core.finish(*finish_args(sample, run), "CANCELLED"))
    assert sum(not isinstance(r, str) for r in results) == 1
    truth = core.read_run(workspace, conversation_id, "a")
    assert (truth.accepted is not None) == (truth.run.status == "ACCEPTED")
    assert truth.conversation.active is None
    with pytest.raises(HTTPException) as error:
        core.read_run(uuid4(), conversation_id, "a")
    assert error.value.status_code == 404


def test_scope_revocation_and_snapshot_identity_fail_closed(sample):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "a", body, execution())
    with pytest.raises(CoreConflict, match="snapshot_identity_conflict"):
        core.accept(
            *finish_args(sample, run),
            ProducedResult(kind="clarification", text="Which?"),
            StateSnapshot(source_turn_id=uuid4(), previous_snapshot_id=None),
        )
    with transaction() as db:
        db.get(KnowledgeBaseRow, body.scope.kb_id).workspace_id = uuid4()
    with pytest.raises(HTTPException):
        finalize(sample, run)
    with pytest.raises(HTTPException):
        core.read_run(workspace, conversation_id, "a")
    with transaction() as db:
        assert db.scalar(select(Accepted.id).where(Accepted.turn_id == run.turn_id)) is None
        assert db.get(Conversation, conversation_id).head_id is None


def test_database_constraints_reject_second_slot_and_foreign_head(sample):
    from sqlalchemy.exc import IntegrityError

    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "a", body, execution())
    with pytest.raises(IntegrityError):
        with transaction() as db:
            db.add(
                Run(
                    id=uuid4(),
                    conversation_id=conversation_id,
                    turn_id=run.turn_id,
                    key="bypass-service",
                    fingerprint="0" * 64,
                    owner=uuid4(),
                    fence=2,
                    deadline=execution().deadline,
                    status="ADMITTED",
                )
            )
    accepted = finalize(sample, run)
    other = core.create(workspace, "other")
    with pytest.raises(IntegrityError):
        with transaction() as db:
            db.get(Conversation, other.id).head_id = accepted.id
    with pytest.raises(IntegrityError):
        with transaction() as db:
            row = db.get(Accepted, accepted.id)
            db.add(
                Accepted(
                    id=uuid4(),
                    conversation_id=conversation_id,
                    turn_id=run.turn_id,
                    run_id=run.id,
                    result=row.result,
                    state=row.state,
                )
            )


# Implementation #2 L1 envelope: original synthetic fixtures only; <=512 Turns /
# acceptances and <=1024 Runs in this UUID DB, 1000ms per history statement.
# These finite test ceilings are enforced by the adapter, not product defaults.
def history_accept(sample, *, signals=None, put=(), deactivate=(), relations=(), question=None):
    workspace, conversation_id, body = sample
    head = core.read_conversation(workspace, conversation_id).head
    body = body.model_copy(
        update={"expected_head": head.id if head else None, "question": question or body.question}
    )
    run = core.admit(workspace, conversation_id, uuid4().hex, body, execution())
    delta = ResolvedConversationDelta(
        source_turn_id=run.turn_id,
        previous_snapshot_id=run.expected_head,
        signals=signals or ResolvedSignals(),
        put=put,
        deactivate=deactivate,
        relations=relations,
    )
    return core.accept(
        *finish_args(sample, run),
        ProducedResult(kind="clarification", text="Original control"),
        StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=run.expected_head),
        delta=delta,
    )


def history_read(sample, head, **kwargs):
    workspace, conversation_id, body = sample
    return read_history(
        workspace,
        conversation_id,
        HistoryQuery(expected_head=head.id if head else None, scope=body.scope, **kwargs),
        permit=LocalHistoryRead(),
    )


@pytest.mark.parametrize("count", [0, 1, 2, 5])
def test_history_recent_committed_only_and_stable(sample, count):
    accepted = [history_accept(sample) for _ in range(count)]
    head = accepted[-1] if accepted else None
    result = history_read(sample, head)
    assert result.failure is None
    assert {r.acceptance_id for r in result.a_inputs} == {a.id for a in accepted[-2:]}
    assert not result.selected  # Recent alone is not relevance.
    assert result == history_read(sample, head)
    assert result.round_trips == 6


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED", "UNKNOWN", "STALE", "ADMITTED", "INTERRUPTED"])
def test_history_nonaccepted_runs_excluded(sample, status):
    workspace, conversation_id, body = sample
    run = core.admit(workspace, conversation_id, "noise", body, execution())
    if status == "INTERRUPTED":
        with transaction() as db:
            db.get(Run, run.id).deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        core.reconcile_expired(workspace, conversation_id)
    elif status != "ADMITTED":
        core.finish(*finish_args(sample, run), status)
    result = history_read(sample, None, explicit=(SourceRef(acceptance_id=uuid4(), turn_id=run.turn_id),))
    assert not result.a_inputs and not result.selected
    assert result.failure == "mandatory_source_unavailable"


def test_history_B_old_structured_matches_and_restart(sample):
    signals = ResolvedSignals(
        topic="original-topic", task="original-task", entities=("entity-1",), constraints=("not-version-2",)
    )
    old = history_accept(sample, signals=signals)
    for _ in range(3):
        head = history_accept(sample, signals=ResolvedSignals(topic="noise", task="noise"))
    result = history_read(sample, head, signals=signals)
    assert result.failure is None and result.selected[0].identity == (old.id,)
    assert old.id not in {r.acceptance_id for r in result.a_inputs}
    assert result.selected[0].reasons == ("entity_constraints", "task", "topic")
    engine().dispose()
    assert history_read(sample, head, signals=signals) == result
    assert history_read(sample, head, explicit=(old.state.source,)).selected[0].identity == (old.id,)
    assert not history_read(sample, head, signals=signals.model_copy(update={"task": "other"})).selected


def test_history_correction_state_and_head_readback(sample):
    first_item = StateValue(id=uuid4(), kind="constraint", key="limit", value="old")
    first = history_accept(sample, put=(first_item,), signals=ResolvedSignals(topic="old"))
    second_item = StateValue(
        id=uuid4(), kind="constraint", key="limit", value="new", replaces=(first_item.id,)
    )
    second = history_accept(
        sample,
        put=(second_item,),
        signals=ResolvedSignals(topic="new"),
        relations=(HistoryRelation(target=first.state.source, kind="correction"),),
    )
    engine().dispose()
    result = history_read(sample, second, explicit=(first.state.source,))
    assert result.failure is None and len(result.selected) == 1
    assert set(result.selected[0].identity) == {first.id, second.id}
    assert result.selected[0].superseded == (first.state.source,)
    assert [e.item.value for e in result.state_projection] == ["new"]
    assert result.state_projection[0].introduced_by == second.state.source
    assert not core.read_conversation(sample[0], sample[1]).head.state.entries[0].active
    with pytest.raises(CoreConflict, match="head_conflict"):
        history_read(sample, first)


def test_history_atomic_visibility_and_stale_delta(sample):
    first = history_accept(sample)
    workspace, conversation_id, body = sample
    run = core.admit(
        workspace, conversation_id, "next", body.model_copy(update={"expected_head": first.id}), execution()
    )
    item = StateValue(id=uuid4(), kind="entity", key="resolved", value="synthetic")
    delta = ResolvedConversationDelta(source_turn_id=run.turn_id, previous_snapshot_id=first.id, put=(item,))

    def accept():
        return core.accept(
            *finish_args(sample, run),
            ProducedResult(kind="clarification", text="Control"),
            StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=first.id),
            delta=delta,
        )

    flushed, release = Event(), Event()

    def pause(session, context):
        if any(isinstance(row, Accepted) for row in session.new):
            flushed.set()
            assert release.wait(5)

    event.listen(Session, "after_flush", pause)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            writing = pool.submit(accept)
            assert flushed.wait(5)
            reading = pool.submit(history_read, sample, first)
            # An independent statement cannot observe the uncommitted semantic state.
            with engine().connect() as connection:
                row = connection.execute(
                    text("""
                    SELECT c.head_id, count(a.id) FROM cw5_conversations c
                    JOIN cw5_acceptances a ON a.conversation_id=c.id
                    WHERE c.id=:id GROUP BY c.head_id
                """),
                    {"id": conversation_id},
                ).one()
                assert tuple(row) == (first.id, 1)
            release.set()
            second = writing.result(timeout=10)
            with pytest.raises(CoreConflict, match="head_conflict"):
                reading.result(timeout=10)
    finally:
        release.set()
        event.remove(Session, "after_flush", pause)
    assert [e.item.id for e in history_read(sample, second).state_projection] == [item.id]
    next_run = core.admit(
        workspace, conversation_id, "third", body.model_copy(update={"expected_head": second.id}), execution()
    )
    with pytest.raises(CoreConflict, match="head_conflict"):
        core.accept(
            *finish_args(sample, next_run),
            ProducedResult(kind="clarification", text="Control"),
            StateSnapshot(source_turn_id=next_run.turn_id, previous_snapshot_id=second.id),
            delta=delta.model_copy(update={"source_turn_id": next_run.turn_id}),
        )
    assert core.read_conversation(workspace, conversation_id).head.id == second.id


def test_history_scope_narrowing_and_revocation(sample):
    workspace, conversation_id, body = sample
    # A second immutable version on its own document, in the same KB.
    document, version = uuid4(), uuid4()
    with transaction() as db:
        db.add(
            DocumentRow(
                id=document, kb_id=body.scope.kb_id, title="Second original", active_version_id=version
            )
        )
        db.flush()
        db.add(
            VersionRow(
                id=version,
                document_id=document,
                kb_id=body.scope.kb_id,
                sequence=1,
                filename="original.pdf",
                license="original",
                source_sha256="1" * 64,
                blob_key="1" * 64,
                status="READY",
                profile={},
                key=str(version),
                fingerprint="1" * 64,
            )
        )
    wide = body.model_copy(
        update={"scope": Scope(kb_id=body.scope.kb_id, version_ids=body.scope.version_ids + (version,))}
    )
    wide_sample = workspace, conversation_id, wide
    first = history_accept(
        wide_sample,
        put=(StateValue(id=uuid4(), kind="entity", key="e", value="e"),),
        signals=ResolvedSignals(topic="old"),
    )
    second = history_accept(sample)
    result = history_read(sample, second, signals=ResolvedSignals(topic="old"))
    assert not result.selected and not result.state_projection
    assert second.state.entries[0].change == "scope_narrowed"
    assert (
        history_read(sample, second, explicit=(first.state.source,)).failure == "mandatory_scope_unavailable"
    )
    with transaction() as db:
        db.get(KnowledgeBaseRow, body.scope.kb_id).workspace_id = uuid4()
    with pytest.raises(HTTPException):
        history_read(sample, second)


def test_history_cross_conversation_and_forged_provenance_rejected(sample):
    accepted = history_accept(sample)
    other = core.create(sample[0], "other-history")
    other_sample = sample[0], other.id, sample[2]
    result = history_read(other_sample, None, explicit=(accepted.state.source,))
    assert result.failure == "mandatory_source_unavailable"
    with pytest.raises(CoreConflict, match="accepted_provenance_unavailable"):
        history_accept(
            other_sample, relations=(HistoryRelation(target=accepted.state.source, kind="correction"),)
        )


def test_history_legacy_transition_and_no_silent_downgrade(sample):
    workspace, conversation_id, body = sample
    legacy = finalize(sample, core.admit(workspace, conversation_id, "v1", body, execution()))
    assert history_read(
        sample, legacy, explicit=(SourceRef(acceptance_id=legacy.id, turn_id=legacy.turn_id),)
    ).selected
    current = history_accept(sample)
    assert current.state.previous_snapshot_id == legacy.id
    run = core.admit(
        workspace,
        conversation_id,
        "downgrade",
        body.model_copy(update={"expected_head": current.id}),
        execution(),
    )
    with pytest.raises(CoreConflict, match="state_revision_downgrade"):
        finalize(sample, run)


def test_history_real_branch_and_payload_limits(sample):
    for _ in range(9):
        head = history_accept(sample, signals=ResolvedSignals(topic="crowded"))
    result = history_read(sample, head, signals=ResolvedSignals(topic="crowded"))
    assert result.search_incomplete and "branch_cap" in result.cutoff and not result.selected
    head = history_accept(sample, question="界" * 50000)
    result = history_read(sample, head)
    assert result.search_incomplete and "payload_cap" in result.cutoff
    assert result.payload_bytes == 0 and result.materialized_rows == 0


def test_history_runtime_disabled_without_explicit_l1_permit(sample):
    result = read_history(sample[0], sample[1], HistoryQuery(expected_head=None, scope=sample[2].scope))
    assert result.failure == "history_query_disabled"


def test_history_real_group_row_and_projection_caps(sample):
    previous = None
    for i in range(65):
        relations = (HistoryRelation(target=previous.state.source, kind="correction"),) if previous else ()
        previous = history_accept(sample, relations=relations)
        if i == 8:
            result = history_read(sample, previous, explicit=(previous.state.source,))
            assert result.failure == "group_member_cap" and result.search_incomplete
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    event.listen(engine(), "before_cursor_execute", capture)
    try:
        result = history_read(sample, previous, explicit=(previous.state.source,))
    finally:
        event.remove(engine(), "before_cursor_execute", capture)
    assert result.search_incomplete and "row_cap" in result.cutoff
    assert result.materialized_rows == 0
    statement, parameters = statements[-1]
    with engine().connect() as connection:
        connection.execute(text("SELECT set_config('statement_timeout', '1000', true)"))
        plan = connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, FORMAT JSON) " + statement, parameters
        ).scalar_one()[0]
    originals = next(p for p in plan["Plan"]["Plans"] if p.get("Subplan Name") == "CTE originals")
    assert originals["Actual Rows"] == 0  # Server-side original materialization is gated too.
    other = core.create(sample[0], "projection-limit")
    other_sample = sample[0], other.id, sample[2]
    head = history_accept(
        other_sample,
        put=tuple(StateValue(id=uuid4(), kind="entity", key=str(i), value="original") for i in range(17)),
    )
    result = history_read(other_sample, head)
    assert result.search_incomplete and "state_projection_cap" in result.cutoff


def test_history_real_query_plan_and_round_trips(sample):
    head = history_accept(sample, signals=ResolvedSignals(topic="plan-topic"))
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append((statement, parameters))

    event.listen(engine(), "before_cursor_execute", capture)
    try:
        result = history_read(sample, head, signals=ResolvedSignals(topic="plan-topic"))
    finally:
        event.remove(engine(), "before_cursor_execute", capture)
    assert result.failure is None and len(statements) == result.round_trips == 6
    statement, parameters = statements[-1]
    with engine().connect() as connection:
        connection.execute(text("SELECT set_config('statement_timeout', '1000', true)"))
        plan = connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
        ).scalar_one()[0]
    nodes = []

    def walk(node):
        nodes.append(node)
        for child in node.get("Plans", []):
            walk(child)

    walk(plan["Plan"])
    scans = [n for n in nodes if n.get("Relation Name", "").startswith("cw5_")]
    examined = sum((n["Actual Rows"] + n.get("Rows Removed by Filter", 0)) * n["Actual Loops"] for n in scans)
    assert scans and examined <= 2048 and plan["Execution Time"] < 1000
    print(
        f"L1 history plan: base scan tuple visits={examined}, execution_ms={plan['Execution Time']}, trips=6"
    )


def test_history_statement_deadline_is_explicit_bounded_failure(sample):
    head = history_accept(sample)
    with transaction() as db:
        db.scalar(select(Conversation).where(Conversation.id == sample[1]).with_for_update())
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(history_read, sample, head).result(timeout=5)
    assert result.search_incomplete and result.cutoff == ("statement_timeout",)


def test_history_semantic_state_rolls_back_with_acceptance(sample):
    first = history_accept(sample)

    def abort(session):
        raise RuntimeError("injected_semantic_precommit_failure")

    # Admit before fault injection so this test fails the acceptance transaction.
    workspace, conversation_id, body = sample
    run = core.admit(
        workspace,
        conversation_id,
        "rollback-state",
        body.model_copy(update={"expected_head": first.id}),
        execution(),
    )
    event.listen(Session, "before_commit", abort)
    try:
        with pytest.raises(RuntimeError, match="injected_semantic"):
            core.accept(
                *finish_args(sample, run),
                ProducedResult(kind="clarification", text="Original"),
                StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=first.id),
                delta=ResolvedConversationDelta(
                    source_turn_id=run.turn_id,
                    previous_snapshot_id=first.id,
                    put=(StateValue(id=uuid4(), kind="topic", key="topic", value="uncommitted"),),
                ),
            )
    finally:
        event.remove(Session, "before_commit", abort)
    result = history_read(sample, first)
    assert not result.state_projection and result.head == first.id
    assert core.read_run(workspace, conversation_id, "rollback-state").accepted is None


def test_history_real_round_trip_guard_stops_before_ninth_statement(sample, monkeypatch):
    original = core._scope

    def extra_reads(db, *args, **kwargs):
        original(db, *args, **kwargs)
        for _ in range(3):
            db.execute(text("SELECT 1"))

    monkeypatch.setattr(core, "_scope", extra_reads)
    result = history_read(sample, None)
    assert result.search_incomplete and result.cutoff == ("round_trip_cap",)
    assert result.round_trips == 8 and result.materialized_rows == 0


# Implementation #3 uses the same isolated database and finite L1 history permit.
def interpretation_case(sample):
    from citeweave.conversation_interpretation import (
        IntentFact,
        InterpretationDraft,
        InterpretationInput,
        ReferenceDraft,
        TextSpan,
        interpret,
    )

    item = StateValue(id=uuid4(), kind="entity", key="device", value="A")
    first = history_accept(sample, put=(item,), signals=ResolvedSignals(entities=("A", "B")))
    workspace, conversation_id, body = sample
    body = body.model_copy(update={"expected_head": first.id, "question": "Which device?"})
    run = core.admit(workspace, conversation_id, "interpret", body, execution())
    context = InterpretationInput(
        conversation_id=conversation_id,
        turn_id=run.turn_id,
        request=body,
        previous=first,
        history=history_read(sample, first, explicit=(first.state.source,)),
    )
    draft = InterpretationDraft(
        topic_relation="continue",
        dependency="required",
        references=(
            ReferenceDraft(
                mention=TextSpan(start=0, end=5),
                candidates=tuple(
                    IntentFact(kind="entity", value=v, source=first.state.source) for v in ("A", "B")
                ),
            ),
        ),
    )
    return run, context, draft, interpret(context, draft=draft)


def interpretation_accept(sample, run, context, draft, result):
    return core.accept(
        *finish_args(sample, run),
        result.control_result or ProducedResult(kind="evidence_insufficient", text="Synthetic control only"),
        StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=run.expected_head),
        delta=result.delta,
        interpretation=(context, draft),
    )


def test_interpretation_clarification_atomic_and_correction_durable(sample):
    from citeweave.conversation_interpretation import (
        AmbiguityBundle,
        IntentFact,
        InterpretationDraft,
        InterpretationInput,
        StateCorrection,
        TextSpan,
        interpret,
    )

    run, context, draft, result = interpretation_case(sample)
    flushed, release = Event(), Event()

    def pause(session, flush_context):
        if any(isinstance(row, Accepted) for row in session.new):
            flushed.set()
            assert release.wait(5)

    event.listen(Session, "after_flush", pause)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(interpretation_accept, sample, run, context, draft, result)
            assert flushed.wait(5)
            with engine().connect() as connection:
                row = connection.execute(
                    text("""
                    SELECT c.head_id, a.result, a.state, r.status
                    FROM cw5_conversations c JOIN cw5_runs r ON r.conversation_id=c.id
                    LEFT JOIN cw5_acceptances a ON a.run_id=r.id WHERE r.id=:run
                """),
                    {"run": run.id},
                ).one()
                assert tuple(row) == (context.previous.id, None, None, "ADMITTED")
            release.set()
            accepted = pending.result(timeout=10)
    finally:
        release.set()
        event.remove(Session, "after_flush", pause)
    engine().dispose()
    truth = core.read_run(sample[0], sample[1], "interpret")
    assert truth.accepted == accepted and truth.conversation.head == accepted
    assert truth.run.status == "ACCEPTED" and truth.conversation.active is None
    ambiguity = next(e for e in accepted.state.entries if e.item.kind == "ambiguity" and e.active)
    assert AmbiguityBundle.model_validate_json(ambiguity.item.value).items[0].reason == "multiple_candidates"
    assert [e.item.value for e in accepted.state.entries if e.active and e.item.kind == "entity"] == ["A"]

    body = context.request.model_copy(update={"expected_head": accepted.id, "question": "Use X"})
    next_run = core.admit(sample[0], sample[1], "resolve", body, execution())
    next_context = InterpretationInput(
        conversation_id=sample[1],
        turn_id=next_run.turn_id,
        request=body,
        previous=accepted,
        history=history_read(sample, accepted),
    )
    old_entity = next(e for e in accepted.state.entries if e.item.kind == "entity" and e.active)
    next_draft = InterpretationDraft(
        topic_relation="continue",
        dependency="none",
        facts=(IntentFact(kind="entity", value="X", span=TextSpan(start=4, end=5)),),
        corrections=tuple(
            StateCorrection(item_id=i, mention=TextSpan(start=0, end=5))
            for i in (old_entity.item.id, ambiguity.item.id)
        ),
        put=(StateValue(id=uuid4(), kind="entity", key="device", value="X", replaces=(old_entity.item.id,)),),
    )
    next_result = interpret(next_context, draft=next_draft)
    resolved = interpretation_accept(sample, next_run, next_context, next_draft, next_result)
    engine().dispose()
    assert core.read_run(sample[0], sample[1], "resolve").accepted == resolved
    active = history_read(sample, resolved).state_projection
    assert [(e.item.kind, e.item.value) for e in active] == [("entity", "X")]
    assert not resolved.state.entries[0].active and not resolved.state.entries[1].active


def test_interpretation_rollback_publishes_nothing(sample):
    run, context, draft, result = interpretation_case(sample)

    def abort(session):
        raise RuntimeError("interpretation_precommit_loss")

    event.listen(Session, "before_commit", abort)
    try:
        with pytest.raises(RuntimeError, match="interpretation_precommit_loss"):
            interpretation_accept(sample, run, context, draft, result)
    finally:
        event.remove(Session, "before_commit", abort)
    truth = core.read_run(sample[0], sample[1], "interpret")
    assert truth.accepted is None and truth.conversation.head == context.previous
    assert truth.run.status == "ADMITTED" and truth.conversation.active.id == run.id


def test_interpretation_stale_input_cannot_publish(sample):
    run, context, draft, result = interpretation_case(sample)
    accepted = interpretation_accept(sample, run, context, draft, result)
    body = context.request.model_copy(update={"expected_head": accepted.id})
    next_run = core.admit(sample[0], sample[1], "stale-interpretation", body, execution())
    with pytest.raises(CoreConflict, match="interpretation_input_conflict"):
        interpretation_accept(sample, next_run, context, draft, result)
    truth = core.read_run(sample[0], sample[1], "stale-interpretation")
    assert truth.accepted is None and truth.conversation.head == accepted


def test_interpretation_scope_change_invalidates_binding_at_commit(sample):
    run, context, draft, result = interpretation_case(sample)
    with transaction() as db:
        db.get(VersionRow, sample[2].scope.version_ids[0]).status = "RETIRED"
    with pytest.raises(CoreConflict, match="scope_changed"):
        interpretation_accept(sample, run, context, draft, result)
    with transaction() as db:
        assert db.scalar(select(Accepted).where(Accepted.run_id == run.id)) is None
        assert db.get(Conversation, sample[1]).head_id == context.previous.id
        assert db.get(Run, run.id).status == "ADMITTED"


@pytest.mark.parametrize("fault", ["fabricated", "pending", "failed", "UNKNOWN"])
def test_interpretation_rechecks_actual_accepted_sources(sample, fault):
    from citeweave.conversation_interpretation import interpret

    run, context, draft, result = interpretation_case(sample)
    if fault == "fabricated":
        group = context.history.selected[0]
        old = group.sources[0]
        changed = old.model_copy(
            update={"request": old.request.model_copy(update={"question": "fabricated accepted original"})}
        )
        group = group.model_copy(update={"sources": (changed,)})
        context = context.model_copy(
            update={"history": context.history.model_copy(update={"selected": (group,)})}
        )
        result = interpret(context, draft=draft)
    else:
        # Corrupt an accepted source's terminal status to test the trust boundary.
        # Normal core commands cannot create this combination.
        with transaction() as db:
            if fault == "pending":
                # Keep the database single-active invariant while simulating loss.
                current = db.get(Run, run.id)
                current.status = "CANCELLED"
                current.completed_at = datetime.now(timezone.utc)
                db.flush()
            old = db.get(Run, context.previous.run_id)
            old.status = {"pending": "ADMITTED", "failed": "FAILED"}.get(fault, fault)
            if fault == "pending":
                old.completed_at = None
    with pytest.raises(CoreConflict, match="run_not_active|interpretation_durable_provenance_conflict"):
        interpretation_accept(sample, run, context, draft, result)
    with transaction() as db:
        assert db.scalar(select(Accepted).where(Accepted.run_id == run.id)) is None
        assert db.get(Conversation, sample[1]).head_id == context.previous.id
