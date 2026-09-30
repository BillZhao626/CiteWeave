"""Explicit synthetic aggregate grants, isolated real PG, no provider I/O."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_conversation_postgres import execution, finish_args
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark
from test_conversation_postgres import sample as sample
from test_conversation_provider_postgres import authorization

from citeweave import conversation_provider as ledger
from citeweave import conversations as core
from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_provider import RunAuthorization
from citeweave.db import transaction
from citeweave.domain import ProviderPhaseRow


def aggregate(run, **changes):
    return RunAuthorization.model_validate(
        dict(
            id=uuid4(),
            run_id=run.id,
            expires_at=run.deadline,
            max_calls=3,
            max_input_tokens=300,
            max_output_tokens=300,
            max_yuan=Decimal("0.003"),
            **changes,
        )
    )


def fresh(sample):
    return core.admit(*sample[:2], "aggregate", sample[2], execution())


def test_absent_grant_is_zero_and_grant_is_immutable(sample):
    run = fresh(sample)
    with pytest.raises(CoreConflict, match="run_authorization_required"):
        ledger.prepare(sample[0], run, authorization(run))
    grant = aggregate(run)
    ledger.authorize_run(sample[0], run, grant)
    ledger.authorize_run(sample[0], run, grant)
    with pytest.raises(CoreConflict, match="run_authorization_conflict"):
        ledger.authorize_run(sample[0], run, grant.model_copy(update={"max_calls": 4}))
    for assignment in ("authorization_max_calls=4", "authorization_id=NULL", "authorization_yuan=0.004"):
        with pytest.raises(IntegrityError), transaction() as db:
            db.execute(text(f"UPDATE cw5_runs SET {assignment} WHERE id=:id"), {"id": run.id})


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_calls", 1),
        ("max_input_tokens", 199),
        ("max_output_tokens", 199),
        ("max_yuan", Decimal("0.00199999")),
    ],
)
def test_prepare_rejects_each_aggregate_dimension(sample, field, value):
    run = fresh(sample)
    grant = aggregate(run).model_copy(update={field: value})
    ledger.authorize_run(sample[0], run, grant)
    ledger.prepare(sample[0], run, authorization(run, "interpretation"))
    with pytest.raises(CoreConflict, match="run_authorization_exceeded"):
        ledger.prepare(sample[0], run, authorization(run))
    with transaction() as db:
        assert (
            len(
                list(
                    db.scalars(select(ProviderPhaseRow).where(ProviderPhaseRow.conversation_run_id == run.id))
                )
            )
            == 1
        )


def test_concurrent_reservations_cannot_overdraw(sample):
    run = fresh(sample)
    ledger.authorize_run(sample[0], run, aggregate(run).model_copy(update={"max_calls": 1}))

    def reserve(purpose):
        try:
            ledger.prepare(sample[0], run, authorization(run, purpose))
            return "prepared"
        except CoreConflict as exc:
            return str(exc)

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(reserve, ["interpretation", "generation"]))
    assert sorted(outcomes) == ["prepared", "run_authorization_exceeded"]


@pytest.mark.parametrize("state", ["COMPLETED", "UNKNOWN", "REJECTED"])
def test_reservations_are_never_released(sample, state):
    run = fresh(sample)
    ledger.authorize_run(sample[0], run, aggregate(run).model_copy(update={"max_calls": 1}))
    phase = ledger.prepare(sample[0], run, authorization(run, "interpretation"))
    ledger.dispatch(sample[0], run, phase.id)
    if state == "COMPLETED":
        ledger.complete(sample[0], run, phase.id, ledger.Observation(result_hash="c" * 64))
    elif state == "UNKNOWN":
        ledger.record_unknown(sample[0], run, phase.id, "response_lost")
    else:
        ledger.reject_dispatched(sample[0], run, phase.id, "llm_http_429")
    with pytest.raises(CoreConflict):
        ledger.prepare(sample[0], run, authorization(run))


def test_dispatch_rechecks_durable_sum_and_retry_needs_new_grant(sample):
    run = fresh(sample)
    ledger.authorize_run(sample[0], run, aggregate(run).model_copy(update={"max_calls": 1}))
    phase = ledger.prepare(sample[0], run, authorization(run))
    # Simulate a writer bypassing the adapter: dispatch still enforces the sum.
    with transaction() as db:
        row = db.get(ProviderPhaseRow, phase.id)
        values = {
            c.name: getattr(row, c.name)
            for c in row.__table__.columns
            if c.name not in {"id", "created_at", "updated_at"}
        }
        values.update(
            phase="interpretation",
            logical_key=f"conversation:{run.id}:interpretation",
            authorization_id=uuid4(),
        )
        db.add(ProviderPhaseRow(**values))
    with pytest.raises(CoreConflict, match="run_authorization_exceeded"):
        ledger.dispatch(sample[0], run, phase.id)
    core.finish(*finish_args(sample, run), "FAILED")
    retry = core.retry(*sample[:2], run.turn_id, run.id, "new-grant", execution())
    with pytest.raises(CoreConflict, match="run_authorization_required"):
        ledger.prepare(sample[0], retry, authorization(retry))


def test_stale_and_expired_grants_fail(sample):
    run = fresh(sample)
    for supplied in (
        run.model_copy(update={"owner": uuid4()}),
        run.model_copy(update={"fence": run.fence + 1}),
    ):
        with pytest.raises(CoreConflict):
            ledger.authorize_run(sample[0], supplied, aggregate(run))
    with pytest.raises(CoreConflict, match="authorization_deadline"):
        ledger.authorize_run(
            sample[0],
            run,
            aggregate(run).model_copy(
                update={"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
            ),
        )
