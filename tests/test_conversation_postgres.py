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
    ProducedResult,
    Scope,
    StateSnapshot,
)
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
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0009"
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
