"""Real PG transitions; broker/process fault matrix additionally runs through Celery."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from citeweave.db import migrate, transaction
from citeweave.domain import EvalCaseRow, EvalRunRow, KnowledgeBaseRow, ProviderPhaseRow, QueryRunRow
from citeweave.evaluation import lifecycle as lc
from citeweave.evaluation import outbox
from citeweave.provider_phases import complete, dispatch, prepare

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="isolated PG required"),
]

CREATED = []


@pytest.fixture(autouse=True)
def cleanup_cases(monkeypatch):
    # Earlier integration fixtures deliberately leave metadata ingestion jobs and
    # abandoned queries. They are not part of this focused evaluator workload.
    monkeypatch.setattr(lc, "LIVE", [])
    with transaction() as db:
        from citeweave.query_runtime import expire_queries

        expire_queries(db, lc.lock(db) + timedelta(seconds=180))
    yield
    for identity, workspace in CREATED:
        lc.cancel(workspace, identity)
        with transaction() as db:
            run = db.get(EvalRunRow, identity)
            for q in db.scalars(
                select(QueryRunRow).where(
                    QueryRunRow.workspace_id == run.workspace_id, QueryRunRow.status == "RUNNING"
                )
            ):
                q.status = "FAILED"
    CREATED.clear()


def make_case():
    migrate()
    with transaction() as db:
        now = lc.lock(db)
        # Tests own their DB. Finish prior fixtures so the single-case scheduler is isolated.
        for run in db.scalars(
            select(EvalRunRow).where(
                EvalRunRow.runtime_policy == lc.POLICY, EvalRunRow.status.not_in(lc.RUN_TERMINAL)
            )
        ):
            for c in db.scalars(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == run.id)):
                lc.terminal(db, c, "CANCELLED", now)
            lc.summarize(db, run, now)
        workspace, kb, identity = uuid4(), uuid4(), uuid4()
        db.add(
            KnowledgeBaseRow(
                id=kb,
                workspace_id=workspace,
                name="Original recovery fixture",
                key=str(kb),
                fingerprint="0" * 64,
            )
        )
        db.flush()
        db.add(
            EvalRunRow(
                id=identity,
                workspace_id=workspace,
                kb_id=kb,
                key=str(identity),
                dataset_id="fixture",
                dataset_hash="0" * 64,
                split="dev",
                versions={},
                runtime_config={},
                total_deadline=now + timedelta(hours=4),
            )
        )
        db.flush()
        db.add(
            EvalCaseRow(eval_run_id=identity, case_id="original", absolute_deadline=now + timedelta(hours=4))
        )
    CREATED.append((identity, workspace))
    return identity, workspace


def get(identity):
    with transaction() as db:
        return db.get(EvalCaseRow, (identity, "original"))


def start(identity):
    lc.sweep()
    c = get(identity)
    token = lc.claim(identity, "original", c.dispatch_generation)
    assert token
    return token


def query(token):
    with transaction() as db:
        c, r, now = lc.owned(db, token)
        q = QueryRunRow(
            id=uuid4(),
            workspace_id=r.workspace_id,
            kb_id=r.kb_id,
            key=str(uuid4()),
            fingerprint="0" * 64,
            question="Original fixture?",
            owner=uuid4(),
            fence=1,
            absolute_deadline=now + timedelta(seconds=60),
            runtime_policy="provider-phases-v1",
        )
        db.add(q)
        db.flush()
        c.query_run_id = q.id
        return q


def due(identity, **values):
    with transaction() as db:
        c = db.get(EvalCaseRow, (identity, "original"))
        now = lc.lock(db)
        for key, value in values.items():
            setattr(c, key, now - timedelta(seconds=1) if value == "past" else value)


def test_duplicate_ack_loss_and_terminal_old_delivery():
    identity, _ = make_case()
    lc.sweep()
    a = outbox.acquire()
    assert a
    # No ACK (simulated successful send followed by transaction outage).
    with transaction() as db:
        from citeweave.domain import EvalOutboxRow

        o = db.get(EvalOutboxRow, a[:3])
        o.publish_lease = lc.lock(db) - timedelta(seconds=1)
    b = outbox.acquire()
    assert b[:3] == a[:3] and b[3] > a[3]
    outbox.acknowledge(a, "stale-ack")
    token = lc.claim(identity, "original", a[2])
    assert token and lc.claim(identity, "original", a[2]) is None
    lc.save(token, status="COMPLETED")
    assert lc.claim(identity, "original", a[2]) is None
    assert get(identity).execution_attempt == 1 and get(identity).dispatch_count == 2


@pytest.mark.parametrize("phase", ["answer", "judge"])
def test_unknown_never_resends_and_retains_reservation(phase):
    identity, _ = make_case()
    token = start(identity)
    q = query(token)
    p = prepare(q.id, q.owner, q.fence, phase, token)
    dispatch(p.id, q.owner, q.fence, token)
    due(identity, lease_until="past")
    lc.sweep()
    assert get(identity).status == "OUTCOME_UNKNOWN"
    for _ in range(3):
        lc.sweep()
        assert lc.claim(identity, "original", get(identity).dispatch_generation) is None
    assert not complete(p.id, q.owner, q.fence, token, [{"text": "late"}])
    with transaction() as db:
        phase_row = db.get(ProviderPhaseRow, p.id)
        assert phase_row.state == "UNKNOWN" and phase_row.reserved_yuan > 0
        assert phase_row.result is None


def test_three_owner_losses_before_dispatch_are_finite():
    identity, _ = make_case()
    for attempt in range(1, 4):
        token = start(identity)
        assert get(identity).execution_attempt == attempt
        due(identity, lease_until="past")
        lc.sweep()
        with pytest.raises(ValueError):
            lc.save(token, status="COMPLETED")
        if attempt < 3:
            due(identity, next_attempt_at="past")
    assert get(identity).status == "FAILED"


@pytest.mark.parametrize("field", ["absolute_deadline", "active_deadline"])
def test_deadline_precedes_dispatch(field):
    identity, _ = make_case()
    due(identity, **{field: "past"})
    sent = []
    outbox.reconcile(lambda *args: sent.append(args))
    assert not sent and get(identity).status == "FAILED"


def test_cancel_and_completion_commit_order():
    identity, workspace = make_case()
    token = start(identity)
    q = query(token)
    p = prepare(q.id, q.owner, q.fence, "answer", token)
    dispatch(p.id, q.owner, q.fence, token)
    lc.cancel(workspace, identity)
    assert get(identity).status == "CANCELLED"
    with pytest.raises(ValueError):
        lc.save(token, status="COMPLETED")
    assert not complete(p.id, q.owner, q.fence, token, [{"text": "late"}])
    identity, workspace = make_case()
    token = start(identity)
    lc.save(token, status="COMPLETED")
    lc.cancel(workspace, identity)
    assert get(identity).status == "COMPLETED"


def test_rejection_two_phase_attempts_are_network_limit():
    identity, _ = make_case()
    token = start(identity)
    q = query(token)
    for _ in range(2):
        p = prepare(q.id, q.owner, q.fence, "answer", token)
        dispatch(p.id, q.owner, q.fence, token)
        complete(p.id, q.owner, q.fence, token, code="llm_http_429")
    with pytest.raises(ValueError, match="attempts_exhausted"):
        prepare(q.id, q.owner, q.fence, "answer", token)


def test_completed_transport_replay_is_not_new_dispatch():
    identity, _ = make_case()
    token = start(identity)
    q = query(token)
    p = prepare(q.id, q.owner, q.fence, "answer", token)
    dispatch(p.id, q.owner, q.fence, token)
    complete(p.id, q.owner, q.fence, token, [{"text": "original"}])
    replay = prepare(q.id, q.owner, q.fence, "answer", token)
    assert replay.id == p.id and replay.result == [{"text": "original"}]
    with pytest.raises(ValueError, match="not_dispatchable"):
        dispatch(p.id, q.owner, q.fence, token)


def test_concurrent_cancel_completion_race_has_one_terminal_winner():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    for _ in range(4):
        identity, workspace = make_case()
        token = start(identity)
        barrier = threading.Barrier(2)

        def finish():
            barrier.wait(timeout=5)
            try:
                lc.save(token, status="COMPLETED")
                return "COMPLETED"
            except ValueError:
                return "CANCELLED"

        def cancel():
            barrier.wait(timeout=5)
            return lc.cancel(workspace, identity).status

        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(finish), pool.submit(cancel)
            expected = a.result(timeout=10)
            assert b.result(timeout=10) == expected
        assert get(identity).status == expected
        assert lc.claim(identity, "original", get(identity).dispatch_generation) is None


def test_last_allowed_successful_dispatch_can_still_execute():
    identity, _ = make_case()
    lc.sweep()
    due(identity, dispatch_count=29)
    ticket = outbox.acquire()
    outbox.acknowledge(ticket, "thirtieth-delivery")
    lc.sweep()
    token = lc.claim(identity, "original", ticket[2])
    assert token and get(identity).dispatch_count == 30
    lc.sweep()
    assert get(identity).status == "RUNNING"
    lc.save(token, status="COMPLETED")
