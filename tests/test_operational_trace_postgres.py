"""Active HTTP/PG observability, read-only inspection, migration and restart proof."""

import json
import os
import subprocess
import sys
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import event as sql_event
from sqlalchemy import select, text
from test_conversation_api_postgres import paths, submit
from test_conversation_postgres import execution
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark
from test_conversation_runtime_postgres import evidence_case as evidence_case
from test_runtime_reliability_postgres import expire, production

from citeweave import conversations as core
from citeweave.conversation_models import ConversationRunEventRow as Event
from citeweave.db import engine, transaction
from citeweave.recovery_inspection import inspect_recovery
from citeweave.runtime_reliability import event, read_events
from citeweave.settings import ROOT


def test_stage_observation_does_not_add_execution_authority(evidence_case):
    from citeweave.conversation_contract import CoreConflict
    from citeweave.operational_trace import observe, operational_stage

    sample, _ = evidence_case
    run = core.admit(*sample[:2], "diagnostic", sample[2], execution())
    expire(run)
    with observe(sample[0], run), operational_stage("history"):
        pass
    assert core.read_run_id(*sample[:2], run.id).run.status == "ADMITTED"
    with pytest.raises(CoreConflict, match="deadline_elapsed"):
        core.execution_input(sample[0], run)
    core.cancel(sample[0], sample[1], run.id)
    with observe(sample[0], run), operational_stage("validation"):
        pass
    with pytest.raises(CoreConflict, match="run_not_active"):
        core.execution_input(sample[0], run)
    read = core.read_run_id(*sample[:2], run.id)
    assert read.run.status == "CANCELLED" and read.accepted is None


def test_non_fencing_conflict_is_not_a_stale_rejection(evidence_case):
    from citeweave.operational_trace import record_fenced

    sample, _ = evidence_case
    run = core.admit(*sample[:2], "non-fencing", sample[2], execution())
    record_fenced(sample[0], run, "provider_outcome_requires_unknown")
    read = core.read_run_id(*sample[:2], run.id)
    assert read.run.status == "ADMITTED"
    assert all(e["kind"] != "stale_result_rejected" for e in read.reliability_events)


def test_active_trace_durable_durations_usage_and_restart_inspection(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, _, calls = production(evidence_case, monkeypatch)
    run = submit(api, sample).json()
    root = paths(sample) + "/runs/" + run["id"]
    trace = api.get(root + "/trace").json()
    diagnostic = trace["operational"]
    assert diagnostic["publication"] == "ACCEPTED" and len(calls) == 1
    durations = {d["phase"]: d for d in diagnostic["durations"]}
    for phase in (
        "admission_queue",
        "history",
        "interpretation",
        "retrieval",
        "generation",
        "validation",
        "publication",
        "provider",
    ):
        assert durations[phase]["availability"] == "AVAILABLE" and durations[phase]["latency_ms"] >= 0
    assert diagnostic["total"]["availability"] == "AVAILABLE"
    phase = diagnostic["provider_phases"][0]
    assert phase["usage"] == {"prompt_tokens": 73, "completion_tokens": 20}
    assert phase["dispatch"] == "RESPONSE_OBSERVED" and phase["estimated_yuan"] is not None
    assert {e["phase"] for e in diagnostic["timeline"] if e["provider_phase_id"]} == {"generation"}
    assert api.get(root + "/trace").json() == trace
    env = dict(
        os.environ,
        CW_DATABASE_URL=engine().url.render_as_string(hide_password=False),
        DEEPSEEK_API_KEY="",
        PYTHONIOENCODING="utf-8",
    )
    child = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/reconcile_conversations.py"),
            "--workspace",
            str(sample[0]),
            "--inspect",
            "--run",
            run["id"],
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert child.returncode == 0
    item = json.loads(child.stdout)["items"][0]
    assert item["operational"] == diagnostic and item["attention"] == "NO_ACTION"
    assert len(calls) == 1
    assert api.get(root + "/trace", headers={"Authorization": "Bearer forged"}).status_code == 401


@pytest.mark.parametrize(
    "status,category", [(429, "provider_known_safe"), (503, "provider_unknown"), (401, "provider_permanent")]
)
def test_failure_taxonomy_usage_absence_and_no_inspection_dispatch(
    evidence_case, monkeypatch, status, category
):
    sample, _ = evidence_case
    api, _, calls = production(
        evidence_case, monkeypatch, attempts=2, handler=lambda *_: httpx.Response(status)
    )
    submit(api, sample)
    read = core.read_run(*sample[:2], "answer")
    trace = api.get(paths(sample) + "/runs/" + str(read.run.id) + "/trace").json()["operational"]
    errors = [e for e in trace["timeline"] if e["kind"] == "provider_failure"]
    assert errors and all(
        e["error_code"] == f"llm_http_{status}" and e["error_category"] == category for e in errors
    )
    p = trace["provider_phases"][0]
    assert p["usage"] is None and p["dispatch"] == "RESPONSE_OBSERVED"
    snapshot = inspect_recovery(sample[0], run_id=read.run.id)
    assert snapshot.items[0].operational.model_dump(mode="json") == trace
    assert len(calls) == (2 if status == 429 else 1)
    if status == 503:
        assert snapshot.items[0].attention == "UNKNOWN_BLOCKED"
        assert snapshot.items[0].operational.retry_decision == "BLOCKED_UNKNOWN"


def test_inspection_is_read_only_bounded_scoped_and_predicts_reconciliation(evidence_case):
    sample, _ = evidence_case
    run = core.admit(*sample[:2], "inspect", sample[2], execution())
    expire(run)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sql_event.listen(engine(), "before_cursor_execute", record)
    try:
        view = inspect_recovery(sample[0], limit=1)
    finally:
        sql_event.remove(engine(), "before_cursor_execute", record)
    assert any("READ ONLY" in s for s in statements)
    assert all(s.lstrip().split()[0].upper() in {"SET", "SELECT"} for s in statements)
    assert view.items[0].reconcile_target == "INTERRUPTED"
    assert core.read_run_id(*sample[:2], run.id).run.status == "ADMITTED"
    assert inspect_recovery(uuid4(), run_id=run.id).items == ()
    core.reconcile_batch(sample[0], limit=1)
    assert inspect_recovery(sample[0]).items[0].status == "INTERRUPTED"
    for limit in (0, 129, True):
        with pytest.raises(ValueError, match="recovery_batch_limit_invalid"):
            inspect_recovery(sample[0], limit=limit)
    other = core.create(sample[0], "second")
    core.admit(sample[0], other.id, "second", sample[2], execution())
    assert inspect_recovery(sample[0], limit=1, include_terminal=True).has_more


def test_event_tail_tie_order_and_legacy_absence(evidence_case):
    sample, _ = evidence_case
    run = core.admit(*sample[:2], "tail", sample[2], execution())
    with transaction() as db:
        row = db.get(core.Run, run.id)
        for _ in range(70):
            event(db, row, "stage_completed", phase="retrieval", latency_ms=0)
        db.flush()
        tied = core._clock(db)
        for identifier in (UUID(int=2), UUID(int=1)):
            db.add(
                Event(
                    id=identifier,
                    run_id=run.id,
                    created_at=tied,
                    kind="stage_completed",
                    fence=1,
                    phase="retrieval",
                    latency_ms=0,
                )
            )
    with transaction() as db:
        events, truncated = read_events(db, run.id)
        assert len(events) == 64 and truncated
        assert [(e.created_at, e.id) for e in events] == sorted((e.created_at, e.id) for e in events)
        assert [e.id for e in events[-2:]] == [UUID(int=1), UUID(int=2)]
    view = inspect_recovery(sample[0], run_id=run.id).items[0].operational
    assert view.truncated and view.durations[3].availability == "INCOMPLETE"
    with transaction() as db:
        # Migration nullable fields do not invent facts on legacy rows.
        db.execute(
            text(
                "INSERT INTO cw5_run_events (id,run_id,created_at,kind,fence) VALUES (:id,:run,clock_timestamp(),'admitted',1)"
            ),
            {"id": uuid4(), "run": run.id},
        )
        legacy = db.scalar(
            select(Event)
            .where(Event.run_id == run.id, Event.phase.is_(None))
            .order_by(Event.created_at.desc())
        )
        assert legacy.phase is None and legacy.current_fence is None


def test_untrusted_exception_body_is_never_persisted(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, runtime, _ = production(evidence_case, monkeypatch)

    def fail(*a):
        raise RuntimeError("PRIVATE_PROVIDER_BODY credential=secret synthetic")

    monkeypatch.setattr(runtime.retriever, "retrieve", fail)
    submit(api, sample)
    read = core.read_run(*sample[:2], "answer")
    trace = api.get(paths(sample) + "/runs/" + str(read.run.id) + "/trace").json()
    assert "PRIVATE_PROVIDER_BODY" not in json.dumps(trace) and "credential" not in json.dumps(trace)
    failure = next(e for e in trace["operational"]["timeline"] if e["kind"] == "stage_failed")
    assert failure["phase"] == "retrieval" and failure["error_category"] == "retrieval"


def test_partial_response_usage_is_known_but_result_stays_unknown(evidence_case, monkeypatch):
    sample, _ = evidence_case
    api, runtime, _ = production(evidence_case, monkeypatch)

    class Partial:
        async def stream_request(self, body, *, before_send):
            before_send()
            yield {"text": "", "provider_id": "synthetic-partial", "usage": {"prompt_tokens": 0}}
            raise TimeoutError("synthetic private body")

    runtime.provider_factory = Partial
    assert submit(api, sample).status_code == 503
    run = core.read_run(*sample[:2], "answer").run
    item = inspect_recovery(sample[0], run_id=run.id).items[0]
    p = item.operational.provider_phases[0]
    assert item.status == "UNKNOWN" and item.operational.retry_decision == "BLOCKED_UNKNOWN"
    assert p.dispatch == "RESPONSE_OBSERVED" and p.usage == {"prompt_tokens": 0}
    assert p.estimated_yuan is None  # missing completion usage, not a fabricated zero cost
