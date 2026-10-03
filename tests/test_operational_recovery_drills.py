"""Sixteen provider-free drills reuse M1 fault seams and inspect durable outcomes.

Optional CW_OPERATIONAL_DRILL_DIR writes synthetic read-only receipts under the
project's ignored .runtime/reliability/m2 directory. No provider policy is installed.
"""

import json
import os
from pathlib import Path

import pytest
import test_runtime_reliability_postgres as m1
from test_conversation_api_postgres import submit
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark
from test_conversation_runtime_postgres import evidence_case as evidence_case

from citeweave import conversations as core
from citeweave.conversation_public import trace_view
from citeweave.recovery_inspection import inspect_recovery
from citeweave.settings import ROOT

DRILLS = {
    "01_success": ("New admitted request", "None", "ACCEPTED"),
    "02_duplicate": ("Same canonical request/key", "Replay in a new process", "ACCEPTED"),
    "03_known_safe_retry": ("Explicit two-attempt synthetic grant", "HTTP429 then success", "ACCEPTED"),
    "04_retry_exhaustion": ("Explicit two-attempt synthetic grant", "HTTP429 twice", "FAILED"),
    "05_provider_unknown": ("Dispatch marker committed", "HTTP503", "UNKNOWN"),
    "06_cancel_before_dispatch": ("Admitted without execution claim", "Client cancel", "CANCELLED"),
    "07_cancel_inflight": ("Held dispatched synthetic response", "Client cancel while held", "CANCELLED"),
    "08_late_after_cancel": (
        "Held dispatched synthetic response",
        "Release late response after cancel",
        "CANCELLED",
    ),
    "09_stale_fence": (
        "Expired local owner",
        "Old owner attempts publication after recovery/new fence",
        "ACCEPTED",
    ),
    "10_kill_before_dispatch": (
        "PREPARED in child process",
        "OS process kill; expiry; fresh-process reconcile",
        "INTERRUPTED",
    ),
    "11_kill_after_dispatch": (
        "DISPATCHED in child process",
        "OS process kill; expiry; fresh-process reconcile",
        "UNKNOWN",
    ),
    "12_result_without_acceptance": (
        "COMPLETED ledger in child process",
        "OS process kill before Acceptance; reconcile",
        "UNKNOWN",
    ),
    "13_permanent_rejection": (
        "Durable permanent rejection",
        "Crash seam before Run finish; reconcile",
        "FAILED",
    ),
    "14_transaction_failure": ("Known provider receipt", "Acceptance insert flush fails", "UNKNOWN"),
    "15_publication_deadline": (
        "Known provider receipt",
        "Final publication flush injects an expired DB deadline",
        "UNKNOWN",
    ),
    "16_bounded_reconcile": (
        "Two expired Conversations",
        "One-item reconciliation; repeated no-op",
        "INTERRUPTED",
    ),
}


@pytest.mark.parametrize("drill", DRILLS)
def test_operational_recovery_drill(evidence_case, monkeypatch, tmp_path, drill):
    sample, _ = evidence_case
    if drill == "01_success":
        api, _, sends = m1.production(evidence_case, monkeypatch)
        assert submit(api, sample).json()["status"] == "ACCEPTED" and len(sends) == 1
    elif drill == "02_duplicate":
        m1.test_http_sequential_completed_and_restart_duplicate_count(evidence_case, monkeypatch, tmp_path)
    elif drill in {"03_known_safe_retry", "05_provider_unknown"}:
        retry = drill == "03_known_safe_retry"
        m1.test_active_http_bounded_retry_or_prohibited_retry(
            evidence_case, monkeypatch, 429 if retry else 503, retry, "ACCEPTED" if retry else "UNKNOWN"
        )
    elif drill == "04_retry_exhaustion":
        m1.test_retry_exhaustion_persisted_and_no_extra_attempt(evidence_case, monkeypatch)
    elif drill == "06_cancel_before_dispatch":
        m1.test_cancel_before_execution_claim(evidence_case)
    elif drill in {"07_cancel_inflight", "08_late_after_cancel"}:
        # Same deterministic race has two assertions: cancel state and late receipt.
        m1.test_cancel_inflight_late_response_never_publishes(evidence_case, monkeypatch)
    elif drill == "09_stale_fence":
        m1.test_stale_worker_after_recovery_and_new_fence(evidence_case)
    elif drill in {"10_kill_before_dispatch", "11_kill_after_dispatch", "12_result_without_acceptance"}:
        stage = {
            "10_kill_before_dispatch": "before_dispatch",
            "11_kill_after_dispatch": "after_dispatch",
            "12_result_without_acceptance": "after_result",
        }[drill]
        m1.test_real_process_kill_restart_reconcile(evidence_case, tmp_path, stage)
    elif drill == "13_permanent_rejection":
        m1.test_permanent_failure_survives_crash_before_run_finish(evidence_case)
    elif drill == "14_transaction_failure":
        m1.test_pg_acceptance_transaction_failure_rolls_back_bundle(evidence_case, monkeypatch)
    elif drill == "15_publication_deadline":
        m1.test_acceptance_final_write_cannot_cross_deadline(evidence_case, monkeypatch)
    elif drill == "16_bounded_reconcile":
        first = core.admit(*sample[:2], "first", sample[2], m1.execution())
        second_conversation = core.create(sample[0], "second")
        second = core.admit(sample[0], second_conversation.id, "second", sample[2], m1.execution())
        m1.expire(first)
        m1.expire(second)
        assert len(core.reconcile_batch(sample[0], limit=1)) == 1
        interim = inspect_recovery(sample[0], include_terminal=True)
        assert {i.status for i in interim.items} == {"ADMITTED", "INTERRUPTED"}
        assert len(core.reconcile_batch(sample[0], limit=1)) == 1
        assert core.reconcile_batch(sample[0], limit=1) == ()

    inspection = inspect_recovery(sample[0], include_terminal=True)
    items = inspection.items
    assert DRILLS[drill][2] in {i.status for i in items}
    if drill in {"07_cancel_inflight", "08_late_after_cancel"}:
        rejected = [e for i in items for e in i.operational.timeline if e.kind == "stale_result_rejected"]
        assert len(rejected) == 1 and rejected[0].current_fence > rejected[0].fence
        assert all(i.operational.publication == "NOT_ACCEPTED" for i in items)
    receipts = []
    for item in items:
        read = core.read_run_id(sample[0], item.conversation_id, item.run_id)
        receipts.append(
            dict(
                run_id=str(item.run_id),
                final_state=item.status,
                acceptance_exists=read.accepted is not None and read.accepted.run_id == item.run_id,
                dispatch_markers=sum(e.kind == "provider_dispatched" for e in item.operational.timeline),
                redispatch_marker_observed=sum(
                    e.kind == "provider_dispatched" for e in item.operational.timeline
                )
                > 1,
                expected_operator_interpretation=item.attention,
                operational=item.operational.model_dump(mode="json"),
                public_trace=trace_view(read).model_dump(mode="json"),
            )
        )
    destination = os.getenv("CW_OPERATIONAL_DRILL_DIR")
    if destination:
        folder = Path(destination).resolve()
        allowed = (ROOT / ".runtime/reliability/m2").resolve()
        assert folder == allowed or allowed in folder.parents
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{drill}.json").write_text(
            json.dumps(
                dict(
                    drill=drill,
                    initial_condition=DRILLS[drill][0],
                    injected_failure=DRILLS[drill][1],
                    provider_model_judge_calls=0,
                    synthetic=True,
                    runs=receipts,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
