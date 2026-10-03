"""Acceptance must finish with one available connection, not borrow recursively."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from threading import Barrier, Event, Lock, Timer

from sqlalchemy import create_engine, event
from test_conversation_api_postgres import submit
from test_conversation_evidence_postgres import accept, prepare
from test_conversation_evidence_postgres import evidence_case as evidence_case
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark
from test_runtime_reliability_postgres import production

from citeweave import conversations as core
from citeweave import db as database
from citeweave.db import engine
from citeweave.structural_repository import StructuralRepository


def test_documentary_acceptance_does_not_require_second_pool_connection(evidence_case, monkeypatch):
    sample, fixture = evidence_case
    prepared = prepare(evidence_case)
    single = create_engine(engine().url, pool_size=1, max_overflow=0, pool_timeout=0.1)
    monkeypatch.setattr(database, "engine", lambda: single)
    try:
        accepted = accept(evidence_case, prepared)
        assert accepted.result.answer.citations == [fixture.citation]
        truth = core.read_run_id(*sample[:2], prepared[0].id)
        assert truth.run.status == "ACCEPTED" and truth.accepted.id == accepted.id
    finally:
        single.dispose()


def test_parallel_acceptances_finish_with_all_pool_slots_occupied(evidence_case, monkeypatch):
    sample, fixture = evidence_case
    cases = [(sample, fixture)]
    for i in range(5):
        conversation = core.create(sample[0], f"pool-proof-{i}")
        cases.append(((sample[0], conversation.id, sample[2]), fixture))
    prepared = [prepare(case) for case in cases]
    bounded = create_engine(engine().url, pool_size=6, max_overflow=0, pool_timeout=0.1)
    barrier, lock, arrivals = Barrier(6), Lock(), []

    @event.listens_for(bounded, "checkout")
    def occupy_all_slots(connection, record, proxy):
        with lock:
            arrivals.append(1)
            first_wave = len(arrivals) <= 6
        if first_wave:
            barrier.wait(5)

    monkeypatch.setattr(database, "engine", lambda: bounded)
    try:
        with ThreadPoolExecutor(6) as pool:
            futures = [pool.submit(accept, case, item) for case, item in zip(cases, prepared, strict=True)]
            accepted = [f.result(10) for f in futures]
        assert len({a.id for a in accepted}) == 6
        for case, item, result in zip(cases, prepared, accepted, strict=True):
            truth = core.read_run_id(*case[0][:2], item[0].id)
            assert truth.run.status == "ACCEPTED" and truth.accepted.id == result.id
            assert truth.accepted.result.answer.citations == [fixture.citation]
    finally:
        bounded.dispose()


def test_binding_budget_exhaustion_under_pool_pressure_is_failed_without_dispatch(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, _, calls = production(evidence_case, monkeypatch)
    original = StructuralRepository.builds
    held, release = Event(), Event()

    def occupy():
        with ExitStack() as stack:
            for _ in range(6):
                stack.enter_context(engine().connect())
            held.set()
            assert release.wait(10)

    def pressured(repository):
        # Real pool wait consumes the unchanged two-second binding budget;
        # no model delay, looser limit or provider attempt is introduced.
        with ThreadPoolExecutor(1) as pool:
            holder = pool.submit(occupy)
            assert held.wait(5)
            timer = Timer(2.1, release.set)
            timer.start()
            try:
                return original(repository)
            finally:
                release.set()
                timer.cancel()
                holder.result(5)

    monkeypatch.setattr(StructuralRepository, "builds", pressured)
    assert submit(api, sample).status_code == 503
    truth = core.read_run(*sample[:2], "answer")
    assert truth.run.status == "FAILED" and truth.run.completed_at is not None
    assert truth.accepted is None and truth.conversation.head is None and calls == []
    assert truth.operational["provider_phases"] == []
    assert any(
        e["kind"] == "stage_failed" and e["phase"] == "retrieval" for e in truth.operational["timeline"]
    )
