"""Synthetic ledger receipts only; UUID-isolated real PG, no external execution."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_conversation_postgres import (
    execution,
    finalize,
    finish_args,
    metadata,
)
from test_conversation_postgres import (
    isolated_pg as isolated_pg,
)
from test_conversation_postgres import (
    pytestmark as pytestmark,
)
from test_conversation_postgres import (
    sample as sample,
)

from citeweave import conversation_provider as ledger
from citeweave import conversations as core
from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_models import ConversationRunRow
from citeweave.costs import RATE_CARD, estimated_cost
from citeweave.db import transaction
from citeweave.domain import ProviderPhaseRow


def authorization(run, purpose="generation"):
    # Explicit synthetic test capacity, never a product policy or spending grant.
    return ledger.CallAuthorization(
        id=uuid4(),
        run_id=run.id,
        purpose=purpose,
        provider="deepseek",
        model="deepseek-flash",
        price_revision=RATE_CARD,
        prompt_revision="synthetic-v1",
        request_hash="a" * 64,
        input_tokens=100,
        output_tokens=100,
        max_yuan=Decimal("0.001"),
        expires_at=run.deadline,
    )


def admit(sample):
    return core.admit(*sample[:2], "run", sample[2], execution())


def expire(run):
    with transaction() as db:
        db.get(ConversationRunRow, run.id).deadline = datetime.now(timezone.utc) - timedelta(seconds=1)


def phase(identity):
    with transaction() as db:
        return db.get(ProviderPhaseRow, identity)


def test_prepared_identity_and_immutable_replay(sample):
    run = admit(sample)
    grant = authorization(run)
    p = ledger.prepare(sample[0], run, grant)
    assert p.conversation_run_id == run.id and p.query_run_id is None and p.eval_run_id is None
    assert p.state == "PREPARED" and p.dispatched_at is None
    assert p.authorization_id == grant.id and p.price_revision == RATE_CARD
    assert p.reserved_yuan == grant.max_yuan
    assert ledger.prepare(sample[0], run, grant).id == p.id
    with pytest.raises(CoreConflict):
        ledger.prepare(sample[0], run, grant.model_copy(update={"request_hash": "b" * 64}))
    with pytest.raises(CoreConflict):
        ledger.prepare(sample[0], run, authorization(run))


@pytest.mark.parametrize(
    "state", ["none", "PREPARED", "REJECTED", "REJECTED_AFTER_DISPATCH", "DISPATCHED", "UNKNOWN", "COMPLETED"]
)
def test_expiry_and_retry_are_driven_by_durable_dispatch(sample, state):
    run = admit(sample)
    if state != "none":
        p = ledger.prepare(sample[0], run, authorization(run))
        if state == "REJECTED":
            ledger.reject_prepared(sample[0], run, p.id, "local_validation_failed")
        elif state != "PREPARED":
            ledger.dispatch(sample[0], run, p.id)
            if state == "UNKNOWN":
                ledger.record_unknown(sample[0], run, p.id, "response_lost")
            elif state == "COMPLETED":
                ledger.complete(sample[0], run, p.id, ledger.Observation(result_hash="b" * 64))
            elif state == "REJECTED_AFTER_DISPATCH":
                with pytest.raises(CoreConflict, match="rejection_not_proven"):
                    ledger.reject_dispatched(sample[0], run, p.id, "llm_timeout")
                ledger.reject_dispatched(sample[0], run, p.id, "llm_http_429")
    expire(run)
    for _ in range(2):
        assert core.reconcile_expired(*sample[:2]).active is None
    status = core.read_run_id(*sample[:2], run.id).run.status
    if state in {"DISPATCHED", "UNKNOWN", "COMPLETED"}:
        assert status == "UNKNOWN"
        with pytest.raises(CoreConflict, match="retry_not_allowed"):
            core.retry(*sample[:2], run.turn_id, run.id, "retry", execution())
    else:
        assert status == "INTERRUPTED"
        assert core.retry(*sample[:2], run.turn_id, run.id, "retry", execution()).retry_of == run.id


def test_dispatch_commit_duplicate_and_usage(sample):
    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))
    ledger.dispatch(sample[0], run, p.id)
    assert phase(p.id).state == "DISPATCHED" and phase(p.id).dispatched_at is not None
    with pytest.raises(CoreConflict):
        ledger.dispatch(sample[0], run, p.id)
    usage = {"prompt_tokens": 25, "completion_tokens": 12, "total_tokens": 37}
    receipt = ledger.Observation(request_id="synthetic-response", result_hash="b" * 64, usage=usage)
    ledger.complete(sample[0], run, p.id, receipt)
    observed = phase(p.id)
    assert observed.usage == usage and observed.request_id == receipt.request_id
    assert observed.estimated_yuan == estimated_cost(usage, observed.dispatched_at)
    assert observed.result_hash == receipt.result_hash and observed.result is None
    with pytest.raises(CoreConflict):
        ledger.complete(sample[0], run, p.id, receipt)
    finalize(sample, run)
    expire(run)
    core.reconcile_expired(*sample[:2])
    assert core.read_run_id(*sample[:2], run.id).run.status == "ACCEPTED"


@pytest.mark.parametrize("change", ["owner", "fence", "deadline", "scope", "workspace"])
def test_stale_or_unauthorized_cannot_mutate(sample, change):
    from fastapi import HTTPException

    from citeweave.domain import VersionRow

    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))
    ledger.dispatch(sample[0], run, p.id)
    supplied, workspace = run, sample[0]
    if change == "owner":
        supplied = run.model_copy(update={"owner": uuid4()})
    elif change == "fence":
        supplied = run.model_copy(update={"fence": run.fence + 1})
    elif change == "deadline":
        expire(run)
    elif change == "scope":
        with transaction() as db:
            db.get(VersionRow, sample[2].scope.version_ids[0]).status = "FAILED"
    else:
        workspace = uuid4()
    for operation in (
        lambda: ledger.prepare(workspace, supplied, authorization(run, "interpretation")),
        lambda: ledger.dispatch(workspace, supplied, p.id),
        lambda: ledger.complete(workspace, supplied, p.id, ledger.Observation(result_hash="b" * 64)),
    ):
        with pytest.raises((CoreConflict, HTTPException)):
            operation()
    assert phase(p.id).state == "DISPATCHED" and phase(p.id).usage is None


def test_cross_run_attribution_and_database_constraints(sample):
    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))
    other_workspace, scope = metadata()
    other_conv = core.create(other_workspace, "other")
    other_run = core.admit(
        other_workspace, other_conv.id, "other", sample[2].model_copy(update={"scope": scope}), execution()
    )
    with pytest.raises(CoreConflict):
        ledger.dispatch(other_workspace, other_run, p.id)
    with pytest.raises(CoreConflict):
        ledger.prepare(sample[0], run, authorization(other_run))
    for statement, params in (
        ("UPDATE cw4_provider_phases SET conversation_run_id=:value WHERE id=:id", {"value": uuid4()}),
        ("UPDATE cw4_provider_phases SET query_run_id=:value WHERE id=:id", {"value": uuid4()}),
    ):
        with pytest.raises(IntegrityError), transaction() as db:
            db.execute(text(statement), dict(params, id=p.id))
    with transaction() as db:
        assert (
            len(
                list(
                    db.scalars(select(ProviderPhaseRow).where(ProviderPhaseRow.conversation_run_id == run.id))
                )
            )
            == 1
        )


def test_uncertain_phase_cannot_be_hidden_by_finish_or_accept(sample):
    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))
    ledger.dispatch(sample[0], run, p.id)
    with pytest.raises(CoreConflict):
        finalize(sample, run)
    with pytest.raises(CoreConflict):
        core.finish(*finish_args(sample, run), "FAILED")
    core.finish(*finish_args(sample, run), "UNKNOWN")
    with pytest.raises(CoreConflict):
        core.retry(*sample[:2], run.turn_id, run.id, "retry", execution())


def test_legacy_helpers_cannot_bypass_conversation_fence(sample):
    from citeweave import provider_phases as legacy

    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))
    with pytest.raises(ValueError, match="requires_conversation_guard"):
        legacy.dispatch(p.id, run.owner, run.fence)
    ledger.dispatch(sample[0], run, p.id)
    with pytest.raises(ValueError, match="requires_conversation_guard"):
        legacy.complete(p.id, run.owner, run.fence, None, [{"text": "untrusted"}])
    assert phase(p.id).state == "DISPATCHED"


def test_missing_usage_is_not_invented_and_authorization_is_immutable(sample):
    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))
    with pytest.raises(IntegrityError), transaction() as db:
        db.execute(text("UPDATE cw4_provider_phases SET price_revision='changed' WHERE id=:id"), {"id": p.id})
    ledger.dispatch(sample[0], run, p.id)
    ledger.complete(sample[0], run, p.id, ledger.Observation(result_hash="c" * 64))
    assert phase(p.id).usage is None and phase(p.id).estimated_yuan is None


def test_concurrent_dispatch_commits_only_once(sample):
    from test_conversation_postgres import race

    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))
    outcomes = race(
        lambda: ledger.dispatch(sample[0], run, p.id), lambda: ledger.dispatch(sample[0], run, p.id)
    )
    assert outcomes.count(None) == 1 and outcomes.count("provider_phase_not_dispatchable") == 1


def test_phase_transition_rolls_back_and_lost_receipt_is_readable(sample, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))

    def fail_commit(db):
        raise RuntimeError("synthetic commit failure")

    event.listen(Session, "before_commit", fail_commit)
    try:
        with pytest.raises(RuntimeError, match="synthetic commit failure"):
            ledger.dispatch(sample[0], run, p.id)
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert phase(p.id).state == "PREPARED" and phase(p.id).dispatched_at is None
    ledger.dispatch(sample[0], run, p.id)  # Discard receipt; a repeated request cannot dispatch again.
    assert (
        ledger.prepare(
            sample[0],
            run,
            authorization(run).model_copy(
                update={
                    "id": p.authorization_id,
                }
            ),
        ).id
        == p.id
    )
    with pytest.raises(CoreConflict):
        ledger.dispatch(sample[0], run, p.id)


def test_partial_observation_retains_reservation_and_blocks_next_dispatch(sample):
    run = admit(sample)
    interpretation = ledger.prepare(sample[0], run, authorization(run, "interpretation"))
    generation = ledger.prepare(sample[0], run, authorization(run))
    ledger.dispatch(sample[0], run, interpretation.id)
    ledger.record_unknown(
        sample[0],
        run,
        interpretation.id,
        "response_lost",
        ledger.Observation(request_id="partial", usage={"prompt_tokens": 10}),
    )
    row = phase(interpretation.id)
    assert row.usage == {"prompt_tokens": 10} and row.estimated_yuan is None
    assert row.result_hash is None and row.reserved_yuan == Decimal("0.001")
    with pytest.raises(CoreConflict, match="provider_outcome_unknown"):
        ledger.dispatch(sample[0], run, generation.id)


def test_terminal_owner_cannot_write_receipt_and_phase_expiry_is_stricter(sample):
    run = admit(sample)
    grant = authorization(run).model_copy(
        update={"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    with pytest.raises(CoreConflict, match="authorization_deadline"):
        ledger.prepare(sample[0], run, grant)
    p = ledger.prepare(sample[0], run, authorization(run))
    ledger.dispatch(sample[0], run, p.id)
    core.finish(*finish_args(sample, run), "UNKNOWN")
    with pytest.raises(CoreConflict):
        ledger.complete(sample[0], run, p.id, ledger.Observation(result_hash="b" * 64))
    assert phase(p.id).result_hash is None


def test_slow_dispatch_flush_past_deadline_rolls_back(sample, monkeypatch):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    run = admit(sample)
    p = ledger.prepare(sample[0], run, authorization(run))
    real_clock = core._clock

    def elapsed_after_flush(db, flush_context):
        monkeypatch.setattr(core, "_clock", lambda db: run.deadline)

    event.listen(Session, "after_flush", elapsed_after_flush)
    try:
        with pytest.raises(CoreConflict, match="deadline_elapsed"):
            ledger.dispatch(sample[0], run, p.id)
    finally:
        event.remove(Session, "after_flush", elapsed_after_flush)
        monkeypatch.setattr(core, "_clock", real_clock)
    assert phase(p.id).state == "PREPARED" and phase(p.id).dispatched_at is None
