"""Fault injection on HTTP -> ProductionRuntime -> actual isolated PG authority."""

import json
import os
import pickle
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event
from types import SimpleNamespace

import httpx
import pytest
from conversation_evidence_fixtures import FakeModel
from pydantic import SecretStr
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_conversation_api import client
from test_conversation_api_postgres import paths, submit
from test_conversation_postgres import execution, finalize
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark
from test_conversation_runtime_postgres import SyntheticAccounting, policy
from test_conversation_runtime_postgres import evidence_case as evidence_case

from citeweave import conversation_provider as ledger
from citeweave import conversations as core
from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_models import ConversationAcceptanceRow as Accepted
from citeweave.conversation_models import ConversationRunEventRow as RunEvent
from citeweave.conversation_models import ConversationRunRow as Run
from citeweave.conversation_models import ConversationTurnRow as Turn
from citeweave.conversation_runtime import ProductionRuntime
from citeweave.db import engine, transaction
from citeweave.domain import ProviderPhaseRow
from citeweave.llm import DeepSeekProvider
from citeweave.settings import ROOT, settings


def production(case, monkeypatch, *, attempts=1, handler=None):
    sample, fixture = case
    monkeypatch.setattr(settings(), "deepseek_api_key", SecretStr("synthetic-never-sent"))
    calls = []

    def transport(request):
        calls.append(json.loads(request.content))
        with transaction() as db:
            row = db.scalar(
                select(ProviderPhaseRow)
                .join(Run, Run.id == ProviderPhaseRow.conversation_run_id)
                .where(Run.conversation_id == sample[1])
            )
            assert row.state == "DISPATCHED" and row.transport_attempt == len(calls)
        if handler:
            response = handler(request, len(calls))
            if response is not None:
                return response
        chunks = [
            dict(
                id="synthetic-receipt",
                choices=[dict(delta={"content": fixture.atom.text + " [E1]"}, finish_reason="stop")],
            ),
            dict(choices=[], usage={"prompt_tokens": 73, "completion_tokens": 20}),
        ]
        return httpx.Response(
            200, text="".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
        )

    p = policy(sample)
    p = p.model_copy(
        update={
            "phases": tuple(
                v.model_copy(update={"max_attempts": attempts}) if v.purpose == "generation" else v
                for v in p.phases
            )
        }
    )
    value = ProductionRuntime(
        p,
        SyntheticAccounting(),
        model=FakeModel(),
        provider_factory=lambda: DeepSeekProvider(
            transport=httpx.MockTransport(transport), circuit=SimpleNamespace(change=lambda *a: None)
        ),
    )
    value.retriever = StructuralEvidenceRetriever(model=FakeModel(), branch_query=fixture.branch)
    return client(sample[0], value), value, calls


def counts(sample):
    with transaction() as db:
        runs = list(db.scalars(select(Run).where(Run.conversation_id == sample[1])))
        ids = [r.id for r in runs]
        return (
            len(runs),
            db.scalar(select(func.count()).select_from(Turn).where(Turn.conversation_id == sample[1])),
            db.scalar(
                select(func.count())
                .select_from(ProviderPhaseRow)
                .where(ProviderPhaseRow.conversation_run_id.in_(ids))
            ),
            db.scalar(select(func.count()).select_from(Accepted).where(Accepted.run_id.in_(ids))),
        )


def expire(run):
    with transaction() as db:
        db.get(Run, run.id).deadline = datetime.now(timezone.utc) - timedelta(seconds=1)


def test_cancel_before_execution_claim(evidence_case):
    from test_conversation_api import client
    from test_conversation_api_postgres import Runtime, paths, submit

    sample, fixture = evidence_case
    api = client(sample[0], Runtime(fixture, "pending"))
    response = submit(api, sample)
    run_id = response.json()["id"]
    root = paths(sample) + "/runs/" + run_id
    cancelled = api.post(root + "/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert api.post(root + "/cancel").json() == cancelled.json()
    assert api.get(root + "/result").status_code == 409
    assert core.read_conversation(*sample[:2]).head is None


def test_http_sequential_completed_and_restart_duplicate_count(evidence_case, monkeypatch, tmp_path):
    sample, fixture = evidence_case
    api, _, calls = production(evidence_case, monkeypatch)
    first = submit(api, sample)
    assert first.status_code == 200 and first.json()["status"] == "ACCEPTED"
    assert submit(api, sample).json() == first.json()
    engine().dispose()
    restarted = client(sample[0])
    assert submit(restarted, sample).json() == first.json()
    payload = tmp_path / "replay.pkl"
    with payload.open("wb") as stream:
        pickle.dump((sample, {k: v for k, v in vars(fixture).items() if k != "repository"}), stream)
    env = dict(
        os.environ,
        CW_DATABASE_URL=engine().url.render_as_string(hide_password=False),
        DEEPSEEK_API_KEY="",
        CW_CONVERSATION_RUNTIME_POLICY="",
        CW_CONVERSATION_TOKENIZER="",
    )
    replay = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/runtime_reliability_worker.py"),
            str(payload),
            str(tmp_path / "unused"),
            "replay",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert replay.returncode == 0
    assert json.loads(replay.stdout) == {"id": first.json()["id"], "status": "ACCEPTED"}
    assert counts(sample) == (1, 1, 1, 1) and len(calls) == 1


def test_http_concurrent_and_in_progress_duplicate_count(evidence_case, monkeypatch):
    sample, _ = evidence_case
    entered, release, barrier = Event(), Event(), Barrier(2)

    def hold(request, count):
        entered.set()
        assert release.wait(15)

    api, _, calls = production(evidence_case, monkeypatch, handler=hold)

    def send():
        barrier.wait(10)
        return submit(api, sample)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(send) for _ in range(2)]
        try:
            assert entered.wait(10)
            duplicate = submit(api, sample)
            assert duplicate.status_code == 202
            assert counts(sample) == (1, 1, 1, 0)
        finally:
            release.set()
        responses = [f.result(15) for f in futures]
    assert {r.status_code for r in responses} <= {200, 202}
    assert len({r.json()["id"] for r in responses}) == 1
    assert counts(sample) == (1, 1, 1, 1) and len(calls) == 1


@pytest.mark.parametrize(
    "code,retry,terminal", [(429, True, "ACCEPTED"), (503, False, "UNKNOWN"), (401, False, "FAILED")]
)
def test_active_http_bounded_retry_or_prohibited_retry(evidence_case, monkeypatch, code, retry, terminal):
    sample, _ = evidence_case
    api, _, calls = production(
        evidence_case,
        monkeypatch,
        attempts=2,
        handler=lambda request, count: httpx.Response(code) if count == 1 else None,
    )
    response = submit(api, sample)
    run = core.read_run(*sample[:2], "answer").run
    assert run.status == terminal and len(calls) == (2 if retry else 1)
    assert response.status_code == (200 if retry else 503)
    root = paths(sample) + "/runs/" + str(run.id)
    trace = api.get(root + "/trace").json()
    failures = [e for e in trace["reliability_events"] if e["kind"] == "provider_failure"]
    assert (
        failures[0]["retry_classification"]
        == {429: "RETRYABLE_KNOWN", 503: "UNKNOWN", 401: "PERMANENT"}[code]
    )
    assert trace["request_fingerprint"] == run.fingerprint
    assert counts(sample)[2] == 1
    assert submit(api, sample).json()["status"] == terminal
    assert len(calls) == (2 if retry else 1)


def test_retry_exhaustion_persisted_and_no_extra_attempt(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, _, calls = production(evidence_case, monkeypatch, attempts=2, handler=lambda *a: httpx.Response(429))
    assert submit(api, sample).status_code == 503
    run = core.read_run(*sample[:2], "answer").run
    assert run.status == "FAILED" and len(calls) == 2
    assert submit(api, sample).json()["status"] == "FAILED"
    with transaction() as db:
        row = db.scalar(select(ProviderPhaseRow).where(ProviderPhaseRow.conversation_run_id == run.id))
        assert row.transport_attempt == row.transport_limit == 2


def test_retry_requires_full_aggregate_reservation(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, runtime, calls = production(evidence_case, monkeypatch, attempts=2)
    runtime.policy = runtime.policy.model_copy(update={"max_calls": 1})
    assert submit(api, sample).status_code == 503
    assert calls == [] and counts(sample) == (1, 1, 0, 0)


@pytest.mark.parametrize("after_dispatch", [False, True])
def test_timeout_classification_on_active_path(evidence_case, monkeypatch, after_dispatch):
    sample, _ = evidence_case
    api, runtime, calls = production(evidence_case, monkeypatch, attempts=2)

    class TimeoutProvider:
        async def stream_request(self, body, *, before_send):
            if after_dispatch:
                before_send()
            raise TimeoutError("synthetic")
            yield

    runtime.provider_factory = TimeoutProvider
    assert submit(api, sample).status_code == 503
    read = core.read_run(*sample[:2], "answer")
    assert read.run.status == ("UNKNOWN" if after_dispatch else "FAILED")
    failures = [e for e in read.reliability_events if e["kind"] == "provider_failure"]
    expected = "UNKNOWN" if after_dispatch else "BEFORE_DISPATCH"
    assert len(failures) == 1 and failures[0]["retry_classification"] == expected
    with transaction() as db:
        row = db.scalar(select(ProviderPhaseRow).where(ProviderPhaseRow.conversation_run_id == read.run.id))
        assert row.retry_classification == expected and row.transport_attempt == 1
    assert calls == [] and counts(sample)[2] == 1


def test_known_connection_failure_can_retry(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, _, calls = production(
        evidence_case,
        monkeypatch,
        attempts=2,
        handler=lambda request, count: (
            (_ for _ in ()).throw(httpx.ConnectTimeout("synthetic")) if count == 1 else None
        ),
    )
    assert submit(api, sample).json()["status"] == "ACCEPTED" and len(calls) == 2


def test_cancel_local_processing_blocks_generation(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, runtime, calls = production(evidence_case, monkeypatch)
    entered, release = Event(), Event()
    retrieve = runtime.retriever.retrieve

    def hold(*args):
        entered.set()
        assert release.wait(15)
        return retrieve(*args)

    runtime.retriever.retrieve = hold
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(submit, api, sample)
        try:
            assert entered.wait(10)
            run = core.read_run(*sample[:2], "answer").run
            assert (
                api.post(paths(sample) + "/runs/" + str(run.id) + "/cancel").json()["status"] == "CANCELLED"
            )
        finally:
            release.set()
        assert future.result(15).status_code == 503
    assert calls == [] and counts(sample) == (1, 1, 0, 0)


def test_cancel_inflight_late_response_never_publishes(evidence_case, monkeypatch):
    sample, _ = evidence_case
    entered, release = Event(), Event()

    def hold(*args):
        entered.set()
        assert release.wait(15)

    api, _, calls = production(evidence_case, monkeypatch, handler=hold)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(submit, api, sample)
        try:
            assert entered.wait(10)
            run = core.read_run(*sample[:2], "answer").run
            root = paths(sample) + "/runs/" + str(run.id)
            assert api.post(root + "/cancel").json()["status"] == "CANCELLED"
            assert api.post(root + "/cancel").json()["status"] == "CANCELLED"
        finally:
            release.set()
        assert future.result(15).status_code == 503
    assert api.get(root + "/result").status_code == 409
    assert '"type":"result"' not in api.get(root + "/events").text
    assert counts(sample) == (1, 1, 1, 0) and len(calls) == 1
    with transaction() as db:
        row = db.scalar(select(ProviderPhaseRow).where(ProviderPhaseRow.conversation_run_id == run.id))
        assert row.state == "UNKNOWN" and row.reserved_yuan > 0 and ledger.blocks_retry(db, run.id)
    with pytest.raises(CoreConflict, match="retry_not_allowed"):
        core.retry(*sample[:2], run.turn_id, run.id, "new", execution())


@pytest.mark.parametrize("winner", ["cancel", "accept"])
def test_cancel_completion_race_pg_lock_decides(evidence_case, winner):
    sample, _ = evidence_case
    run = core.admit(*sample[:2], "race", sample[2], execution())
    entered, release = Event(), Event()
    original = core._conversation

    def locked(*args):
        value = original(*args)
        if not entered.is_set():
            entered.set()
            assert release.wait(15)
        return value

    def accept():
        try:
            return finalize(sample, run)
        except CoreConflict:
            return None

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core, "_conversation", locked)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = (
                pool.submit(core.cancel, *sample[:2], run.id) if winner == "cancel" else pool.submit(accept)
            )
            try:
                assert entered.wait(10)
                second = (
                    pool.submit(accept)
                    if winner == "cancel"
                    else pool.submit(core.cancel, *sample[:2], run.id)
                )
            finally:
                release.set()
            first.result(15)
            second.result(15)
    assert core.read_run_id(*sample[:2], run.id).run.status == (
        "CANCELLED" if winner == "cancel" else "ACCEPTED"
    )
    assert counts(sample)[3] == (0 if winner == "cancel" else 1)


def test_duplicate_executor_claim_fences_paid_work(evidence_case, monkeypatch):
    sample, _ = evidence_case
    _, runtime, calls = production(evidence_case, monkeypatch)
    run = core.admit(*sample[:2], "claim", sample[2], runtime.prepare())
    core.start_execution(sample[0], run)
    with pytest.raises(CoreConflict, match="execution_already_started"):
        runtime.execute(sample[0], run)
    assert calls == [] and core.read_run_id(*sample[:2], run.id).run.status == "ADMITTED"


def test_stale_worker_after_recovery_and_new_fence(evidence_case):
    sample, _ = evidence_case
    old = core.admit(*sample[:2], "old", sample[2], execution())
    expire(old)
    assert core.reconcile_batch(sample[0], limit=1)[0].active is None
    fresh = core.retry(*sample[:2], old.turn_id, old.id, "retry", execution())
    with pytest.raises(CoreConflict):
        finalize(sample, old)
    assert finalize(sample, fresh).run_id == fresh.id
    assert counts(sample) == (2, 1, 0, 1)


def test_stale_transport_attempt_cannot_complete_new_attempt(evidence_case):
    from test_conversation_provider_postgres import admit, authorization

    sample, _ = evidence_case
    run = admit(sample)
    phase = ledger.prepare(sample[0], run, authorization(run).model_copy(update={"max_attempts": 2}))
    first = ledger.begin_attempt(sample[0], run, phase.id)
    ledger.dispatch(sample[0], run, phase.id, attempt=first)
    with transaction() as db:
        first_dispatch = db.get(ProviderPhaseRow, phase.id).dispatched_at
    ledger.fail_attempt(sample[0], run, phase.id, first, "llm_http_429", dispatched=True, latency_ms=0)
    ledger.schedule_retry(sample[0], run, phase.id, first, 0)
    with pytest.raises(CoreConflict, match="provider_phase_not_dispatchable"):
        ledger.dispatch(sample[0], run, phase.id, attempt=first)
    second = ledger.begin_attempt(sample[0], run, phase.id)
    ledger.dispatch(sample[0], run, phase.id, attempt=second)
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase.id).dispatched_at > first_dispatch
    with pytest.raises(CoreConflict, match="stale_provider_attempt"):
        ledger.complete(sample[0], run, phase.id, ledger.Observation(result_hash="b" * 64), attempt=first)


def test_pg_acceptance_transaction_failure_rolls_back_bundle(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, _, calls = production(evidence_case, monkeypatch)

    def fail(session, context, instances):
        if any(isinstance(row, Accepted) for row in session.new):
            raise RuntimeError("synthetic transaction failure")

    event.listen(Session, "before_flush", fail)
    try:
        assert submit(api, sample).status_code == 503
    finally:
        event.remove(Session, "before_flush", fail)
    read = core.read_run(*sample[:2], "answer")
    assert read.run.status == "UNKNOWN" and read.accepted is None and read.conversation.head is None
    assert counts(sample) == (1, 1, 1, 0) and len(calls) == 1


def test_acceptance_final_write_cannot_cross_deadline(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, _, calls = production(evidence_case, monkeypatch)
    accept = core.accept
    delayed = Event()

    def shortly_expiring(*args, **kwargs):
        with transaction() as db:
            db.get(Run, args[3]).deadline = core._clock(db) + timedelta(seconds=30)
        return accept(*args, **kwargs)

    def slow_final_write(session, context, instances):
        for row in session.dirty:
            if isinstance(row, Run) and row.status == "ACCEPTED":
                # Deterministically cross the DB deadline at the final flush,
                # after prior guards passed. No host-clock/sleep margin assumption.
                row.deadline = datetime(2000, 1, 1, tzinfo=timezone.utc)
                delayed.set()

    monkeypatch.setattr(core, "accept", shortly_expiring)
    event.listen(Session, "before_flush", slow_final_write)
    try:
        assert submit(api, sample).status_code == 503
    finally:
        event.remove(Session, "before_flush", slow_final_write)
    assert delayed.is_set(), "injection must reach the final write after validation"
    read = core.read_run(*sample[:2], "answer")
    assert read.run.status == "UNKNOWN" and read.accepted is None and read.conversation.head is None
    assert counts(sample) == (1, 1, 1, 0) and len(calls) == 1


def test_database_rejects_completed_without_result_and_retains_events(evidence_case):
    sample, _ = evidence_case
    run = core.admit(*sample[:2], "invalid", sample[2], execution())
    with pytest.raises(IntegrityError, match="conversation_result_status_conflict"):
        with transaction() as db:
            row = db.get(Run, run.id)
            row.status, row.completed_at = "ACCEPTED", datetime.now(timezone.utc)
    with pytest.raises(IntegrityError, match="conversation_run_event_retained"):
        with transaction() as db:
            row = db.scalar(select(RunEvent).where(RunEvent.run_id == run.id))
            db.delete(row)
    assert core.read_run_id(*sample[:2], run.id).run.status == "ADMITTED"


def test_cancellation_authentication_and_workspace_scope(evidence_case):
    sample, _ = evidence_case
    run = core.admit(*sample[:2], "auth", sample[2], execution())
    root = paths(sample) + "/runs/" + str(run.id) + "/cancel"
    assert client().post(root).status_code == 404
    assert client(sample[0]).post(root, headers={"Authorization": "Bearer forged"}).status_code == 401
    assert core.read_run_id(*sample[:2], run.id).run.status == "ADMITTED"


@pytest.mark.parametrize("stage", ["before_dispatch", "after_dispatch", "after_result"])
def test_real_process_kill_restart_reconcile(evidence_case, tmp_path, stage):
    sample, fixture = evidence_case
    # Pickle only original synthetic fixture fields, no lambda repository, secrets
    # or provider payload. This is a test-only local child-process contract.
    payload = tmp_path / "synthetic.pkl"
    with payload.open("wb") as stream:
        pickle.dump((sample, {k: v for k, v in vars(fixture).items() if k != "repository"}), stream)
    marker = tmp_path / "crash-boundary"
    env = dict(
        os.environ,
        CW_DATABASE_URL=engine().url.render_as_string(hide_password=False),
        DEEPSEEK_API_KEY="",
        PYTHONIOENCODING="utf-8",
    )
    worker = subprocess.Popen(
        [sys.executable, str(ROOT / "tests/runtime_reliability_worker.py"), str(payload), str(marker), stage],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        while not marker.exists() and worker.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "child did not reach durable crash boundary"
        worker.kill()
        worker.wait(timeout=10)
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=10)
    run = core.read_run(*sample[:2], "crash").run
    assert run.status == "ADMITTED"
    expire(run)
    recovered = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/reconcile_conversations.py"),
            "--workspace",
            str(sample[0]),
            "--limit",
            "1",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert recovered.returncode == 0 and json.loads(recovered.stdout)["scanned"] == 1
    truth = core.read_run_id(*sample[:2], run.id)
    assert truth.run.status == ("INTERRUPTED" if stage == "before_dispatch" else "UNKNOWN")
    assert counts(sample) == (1, 1, 1, 0)
    if stage != "before_dispatch":
        with pytest.raises(CoreConflict, match="retry_not_allowed"):
            core.retry(*sample[:2], run.turn_id, run.id, "retry", execution())
    else:
        fresh = core.retry(*sample[:2], run.turn_id, run.id, "retry", execution())
        assert fresh.id != run.id


def test_permanent_failure_survives_crash_before_run_finish(evidence_case):
    from test_conversation_provider_postgres import admit, authorization

    sample, _ = evidence_case
    run = admit(sample)
    phase = ledger.prepare(sample[0], run, authorization(run))
    attempt = ledger.begin_attempt(sample[0], run, phase.id)
    ledger.dispatch(sample[0], run, phase.id, attempt=attempt)
    ledger.fail_attempt(sample[0], run, phase.id, attempt, "llm_http_401", dispatched=True, latency_ms=0)
    expire(run)
    core.reconcile_batch(sample[0], limit=1)
    assert core.read_run_id(*sample[:2], run.id).run.status == "FAILED"


def test_cancel_during_retry_backoff_no_second_send(evidence_case, monkeypatch):
    sample, _ = evidence_case
    entered, release = Event(), Event()
    schedule = ledger.schedule_retry

    def hold(*args):
        schedule(*args)
        entered.set()
        assert release.wait(15)

    monkeypatch.setattr(ledger, "schedule_retry", hold)
    api, _, calls = production(evidence_case, monkeypatch, attempts=2, handler=lambda *a: httpx.Response(429))
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(submit, api, sample)
        try:
            assert entered.wait(10)
            run = core.read_run(*sample[:2], "answer").run
            assert (
                api.post(paths(sample) + "/runs/" + str(run.id) + "/cancel").json()["status"] == "CANCELLED"
            )
        finally:
            release.set()
        assert future.result(15).status_code == 503
    assert len(calls) == 1 and counts(sample) == (1, 1, 1, 0)


def test_success_http_then_connection_error_is_unknown(evidence_case, monkeypatch):
    sample, _ = evidence_case

    class LostStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ConnectTimeout("synthetic after HTTP200")
            yield b""

    api, _, calls = production(
        evidence_case, monkeypatch, attempts=2, handler=lambda *a: httpx.Response(200, stream=LostStream())
    )
    assert submit(api, sample).status_code == 503
    read = core.read_run(*sample[:2], "answer")
    assert read.run.status == "UNKNOWN" and len(calls) == 1
    assert [
        e["retry_classification"] for e in read.reliability_events if e["kind"] == "provider_failure"
    ] == ["UNKNOWN"]


def test_http_error_then_close_connection_failure_is_unknown(evidence_case, monkeypatch):
    sample, _ = evidence_case

    class ClosingLoss(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b""

        async def aclose(self):
            raise httpx.ConnectError("synthetic close failure after HTTP503")

    api, _, calls = production(
        evidence_case, monkeypatch, attempts=2, handler=lambda *a: httpx.Response(503, stream=ClosingLoss())
    )
    assert submit(api, sample).status_code == 503
    read = core.read_run(*sample[:2], "answer")
    assert read.run.status == "UNKNOWN" and len(calls) == 1
    assert read.accepted is None
    with transaction() as db:
        row = db.scalar(select(ProviderPhaseRow).where(ProviderPhaseRow.conversation_run_id == read.run.id))
        assert row.state == "UNKNOWN" and row.transport_attempt == 1
        assert row.retry_classification == "UNKNOWN" and row.reserved_yuan > 0
    assert submit(api, sample).json()["status"] == "UNKNOWN" and len(calls) == 1
    with pytest.raises(CoreConflict, match="retry_not_allowed"):
        core.retry(*sample[:2], read.run.turn_id, read.run.id, "retry", execution())


def test_recovery_is_bounded_and_idempotent(evidence_case):
    sample, _ = evidence_case
    run = core.admit(*sample[:2], "recover", sample[2], execution())
    expire(run)
    assert len(core.reconcile_batch(sample[0], limit=1)) == 1
    assert core.reconcile_batch(sample[0], limit=1) == ()
    assert core.read_run_id(*sample[:2], run.id).run.status == "INTERRUPTED"
    for invalid in (0, 129, True):
        with pytest.raises(ValueError):
            core.reconcile_batch(sample[0], limit=invalid)


def test_active_query_does_not_depend_on_redis_or_celery(evidence_case, monkeypatch):
    import celery
    import redis

    def unavailable(*args, **kwargs):
        pytest.fail("query runtime contacted inactive broker/worker")

    monkeypatch.setattr(redis.Redis, "execute_command", unavailable)
    monkeypatch.setattr(celery.Celery, "send_task", unavailable)
    sample, _ = evidence_case
    api, _, calls = production(evidence_case, monkeypatch)
    assert submit(api, sample).json()["status"] == "ACCEPTED" and len(calls) == 1
