"""Deterministic contracts; these tests do not claim PostgreSQL locking evidence."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from citeweave.conversation_contract import (
    Admission,
    CoreConflict,
    RunStatus,
    Scope,
    fingerprint,
    require_head,
    require_owner,
    transition,
)


def submission(**changes):
    return Admission(
        question="Original question",
        scope=Scope(kb_id=uuid4(), version_ids=(uuid4(),)),
        expected_head=None,
        **changes,
    )


@pytest.mark.parametrize("target", [s for s in RunStatus if s != RunStatus.ADMITTED])
def test_active_can_finish(target):
    assert transition(RunStatus.ADMITTED, target) == target


@pytest.mark.parametrize(
    "source,target",
    [(s, t) for s in RunStatus for t in RunStatus if s != RunStatus.ADMITTED or t == RunStatus.ADMITTED],
)
def test_no_reopen_or_terminal_rewrite(source, target):
    with pytest.raises(CoreConflict, match="illegal_transition"):
        transition(source, target)


def test_fingerprint_exact_intent_and_canonical_scope():
    body = submission()
    a, b = uuid4(), uuid4()
    first = body.model_copy(update={"scope": Scope(kb_id=body.scope.kb_id, version_ids=(a, b))})
    second = first.model_copy(update={"scope": Scope(kb_id=body.scope.kb_id, version_ids=(b, a))})
    assert fingerprint(first) == fingerprint(second)
    assert fingerprint(body) != fingerprint(body.model_copy(update={"question": body.question + " "}))
    assert fingerprint(body) != fingerprint(body.model_copy(update={"expected_head": uuid4()}))


def test_head_and_ownership_fail_closed():
    owner = uuid4()
    now = datetime.now(timezone.utc)
    require_head(None, None)
    with pytest.raises(CoreConflict, match="head_conflict"):
        require_head(uuid4(), None)
    require_owner(RunStatus.ADMITTED, owner, 1, owner, 1, 1, now + timedelta(seconds=1), now)
    for status, actual_owner, fence, current_fence, deadline in [
        (RunStatus.CANCELLED, owner, 1, 1, now + timedelta(seconds=1)),
        (RunStatus.ADMITTED, uuid4(), 1, 1, now + timedelta(seconds=1)),
        (RunStatus.ADMITTED, owner, 2, 2, now + timedelta(seconds=1)),
        (RunStatus.ADMITTED, owner, 1, 2, now + timedelta(seconds=1)),
        (RunStatus.ADMITTED, owner, 1, 1, now),
    ]:
        with pytest.raises(CoreConflict):
            require_owner(status, actual_owner, fence, owner, 1, current_fence, deadline, now)


def test_durable_schema_rejects_unknown_semantics_and_duplicate_scope():
    with pytest.raises(ValidationError):
        submission(profile="future-intelligence")
    with pytest.raises(ValidationError):
        submission(history=["not authorized"])
    identity = uuid4()
    with pytest.raises(ValidationError):
        Scope(kb_id=uuid4(), version_ids=(identity, identity))
    with pytest.raises(ValidationError):
        Scope(kb_id=uuid4(), version_ids=())


def test_migration_compiles_additive_postgres_ddl():
    import importlib.util
    from io import StringIO

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from citeweave.settings import ROOT

    spec = importlib.util.spec_from_file_location(
        "conversation_migration", ROOT / "migrations/versions/0009_conversation_core.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = StringIO()
    ctx = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    with Operations.context(ctx):
        module.upgrade()
    ddl = output.getvalue()
    assert ddl.count("CREATE TABLE") == 4
    assert "WHERE status = 'ADMITTED'" in ddl
    assert "FOREIGN KEY(id, head_id)" in ddl
    assert not any(word in ddl for word in ("cw1_", "DROP", "DELETE", "UPDATE"))
    with pytest.raises(RuntimeError, match="fix_forward"):
        module.downgrade()


@pytest.fixture
def accept_service(monkeypatch):
    """Exercise production guards without claiming these doubles prove DB atomicity."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from unittest.mock import Mock

    from citeweave import conversations as service
    from citeweave.conversation_contract import ProducedResult, StateSnapshot

    body = submission()
    turn = SimpleNamespace(id=uuid4(), request=body.model_dump(mode="json"), expected_head=None)
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id=uuid4(),
        turn_id=turn.id,
        status=RunStatus.ADMITTED,
        owner=uuid4(),
        fence=1,
        deadline=now + timedelta(seconds=20),
    )
    conversation = SimpleNamespace(id=uuid4(), head_id=None, fence=1)
    db = Mock()
    db.scalar.return_value = None  # No provider phase exists in this local control fixture.
    writes = []
    db.add.side_effect = writes.append
    db.flush.side_effect = lambda: [setattr(row, "created_at", now) for row in writes]
    outcomes = []

    @contextmanager
    def tx():
        try:
            yield db
        except Exception:
            outcomes.append("rollback")
            raise
        else:
            outcomes.append("commit")

    monkeypatch.setattr(service, "transaction", tx)
    for name, value in [
        ("_conversation", conversation),
        ("_turn", turn),
        ("_run", run),
        ("_accepted", None),
        ("_clock", now),
        ("_scope", None),
    ]:
        monkeypatch.setattr(service, name, Mock(return_value=value))
    args = dict(
        workspace=uuid4(),
        conversation_id=conversation.id,
        turn_id=turn.id,
        run_id=run.id,
        owner=run.owner,
        fence=1,
        result=ProducedResult(kind="clarification", text="Which document?"),
        state=StateSnapshot(source_turn_id=turn.id, previous_snapshot_id=None),
    )
    return service, args, conversation, run, writes, outcomes, db


@pytest.mark.parametrize("failure", ["head", "owner", "fence", "duplicate", "snapshot", "deadline", "scope"])
def test_acceptance_service_rejects_before_any_write(accept_service, failure):
    service, args, conversation, run, writes, outcomes, _ = accept_service
    if failure == "head":
        conversation.head_id = uuid4()
    elif failure == "owner":
        args["owner"] = uuid4()
    elif failure == "fence":
        conversation.fence += 1
    elif failure == "duplicate":
        service._accepted.return_value = object()
    elif failure == "snapshot":
        args["state"] = args["state"].model_copy(update={"source_turn_id": uuid4()})
    elif failure == "deadline":
        run.deadline -= timedelta(seconds=30)
    else:
        service._scope.side_effect = CoreConflict("scope_changed")
    with pytest.raises(CoreConflict):
        service.accept(**args)
    assert writes == [] and outcomes == ["rollback"]
    assert run.status == RunStatus.ADMITTED


def test_acceptance_service_one_transaction(accept_service):
    service, args, conversation, run, writes, outcomes, _ = accept_service
    accepted = service.accept(**args)
    assert len(writes) == 2 and outcomes == ["commit"]
    assert writes[1].kind == "accepted" and writes[1].run_id == run.id
    assert conversation.head_id == accepted.id and run.status == RunStatus.ACCEPTED
    assert accepted.state.source_turn_id == args["turn_id"]
    assert accepted.state.previous_snapshot_id is None
    assert conversation.fence == 2


def test_acceptance_service_flush_failure_is_visible(accept_service):
    service, args, _, _, _, outcomes, db = accept_service
    db.flush.side_effect = RuntimeError("injected_storage_failure")
    with pytest.raises(RuntimeError, match="injected_storage_failure"):
        service.accept(**args)
    assert outcomes == ["rollback"]


def test_same_key_different_fingerprint_is_not_retry():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from citeweave.conversations import _replay

    existing = SimpleNamespace(fingerprint="original")
    db = Mock()
    db.scalar.return_value = existing
    assert _replay(db, uuid4(), "key", "original") is existing
    with pytest.raises(CoreConflict, match="idempotency_conflict"):
        _replay(db, uuid4(), "key", "changed")


def test_admission_replay_observes_original_identity_even_after_head_advance(accept_service, monkeypatch):
    from unittest.mock import Mock

    from citeweave.conversation_contract import Execution

    service, args, conversation, run, writes, outcomes, _ = accept_service
    conversation.head_id = uuid4()
    monkeypatch.setattr(service, "_replay", Mock(return_value=run))
    monkeypatch.setattr(service, "_run_view", Mock(return_value="original_identity"))
    body = submission()
    fresh_owner = Execution(owner=uuid4(), deadline=run.deadline)
    assert service.admit(args["workspace"], conversation.id, "same", body, fresh_owner) == "original_identity"
    assert writes == [] and outcomes == ["commit"]


@pytest.mark.parametrize("conflict", ["head_conflict", "conversation_busy"])
def test_admission_conflict_has_no_new_turn(accept_service, monkeypatch, conflict):
    from unittest.mock import Mock

    from citeweave.conversation_contract import Execution

    service, args, conversation, run, writes, outcomes, _ = accept_service
    monkeypatch.setattr(service, "_replay", Mock(return_value=None))
    monkeypatch.setattr(service, "_active", Mock(return_value=run))
    if conflict == "head_conflict":
        conversation.head_id = uuid4()
    with pytest.raises(CoreConflict, match=conflict):
        service.admit(
            args["workspace"],
            conversation.id,
            "different",
            submission(),
            Execution(owner=uuid4(), deadline=run.deadline),
        )
    assert writes == [] and outcomes == ["rollback"]


def test_late_unknown_can_be_recorded_without_acceptance(accept_service, monkeypatch):
    from unittest.mock import Mock

    service, args, conversation, run, writes, outcomes, _ = accept_service
    run.deadline -= timedelta(seconds=30)
    monkeypatch.setattr(service, "_run_view", Mock(return_value="unknown_receipt"))
    assert (
        service.finish(
            args["workspace"],
            conversation.id,
            args["turn_id"],
            run.id,
            run.owner,
            run.fence,
            RunStatus.UNKNOWN,
        )
        == "unknown_receipt"
    )
    assert run.status == RunStatus.UNKNOWN and conversation.head_id is None
    assert len(writes) == 1 and writes[0].kind == "finished" and outcomes == ["commit"]


def test_deadline_expiring_during_acceptance_rolls_back(accept_service):
    service, args, _, run, _, outcomes, _ = accept_service
    service._clock.side_effect = [run.deadline - timedelta(seconds=1), run.deadline]
    with pytest.raises(CoreConflict, match="deadline_elapsed"):
        service.accept(**args)
    assert outcomes == ["rollback"]


def test_control_dto_cannot_masquerade_as_documentary_answer_or_semantic_state():
    from citeweave.conversation_contract import Execution, ProducedResult, StateSnapshot

    with pytest.raises(ValidationError):
        ProducedResult(kind="answer", text="Unverified technical claim")
    with pytest.raises(ValidationError):
        StateSnapshot(source_turn_id=uuid4(), previous_snapshot_id=None, entities=["guessed"])
    with pytest.raises(ValidationError):
        Execution(owner=uuid4(), deadline=datetime(2026, 1, 1))
