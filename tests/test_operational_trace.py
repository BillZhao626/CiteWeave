"""Operational projections must not turn missing or uncertain facts into success."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from citeweave.operational_trace import ProviderDiagnostic, diagnose, operational_category, safe_error_code
from citeweave.runtime_reliability import ReliabilitySignal, classify


def test_absent_history_is_not_zero_usage_or_a_dispatch_proof():
    now = datetime.now(timezone.utc)
    value = diagnose("UNKNOWN", now, now + timedelta(seconds=2), (), False, ())
    assert value.total.latency_ms == 2000
    assert value.total.availability == "UNKNOWN"
    assert value.provider_phases == ()
    assert all(d.latency_ms is None for d in value.durations if d.phase != "total")
    assert value.retry_decision == "BLOCKED_UNKNOWN"
    assert value.unknown_reason == "LEGACY_REASON_UNAVAILABLE"


def test_exception_payloads_are_not_error_codes():
    from sqlalchemy.exc import SQLAlchemyError

    from citeweave.conversation_contract import CoreConflict

    assert safe_error_code(RuntimeError("private payload")) == "internal_error"
    assert safe_error_code(SQLAlchemyError("password=private")) == "database_transaction_failed"
    assert (
        safe_error_code(CoreConflict("documentary_answer_identity_conflict"))
        == "documentary_answer_identity_conflict"
    )


def test_zero_local_duration_and_bounded_incomplete_history():
    now = datetime.now(timezone.utc)
    events = (
        ReliabilitySignal(
            id=uuid4(), created_at=now, kind="stage_completed", fence=1, phase="retrieval", latency_ms=0
        ),
    )
    value = diagnose("CANCELLED", now, now, events, True, ())
    retrieval = next(d for d in value.durations if d.phase == "retrieval")
    assert retrieval.latency_ms == 0 and retrieval.availability == "INCOMPLETE"
    assert value.total.availability == "CANCELLED"
    assert value.timeline[0].phase == "retrieval"


@pytest.mark.parametrize("phase", ["admission_queue", "total"])
def test_reversed_database_timestamps_are_not_measured_zero(phase):
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(seconds=1)
    signals = (ReliabilitySignal(id=uuid4(), created_at=earlier, kind="execution_started", fence=1),)
    value = diagnose("ACCEPTED", now, earlier, signals, False, ())
    duration = value.total if phase == "total" else value.durations[0]
    assert duration.latency_ms is None and duration.availability == "INCOMPLETE"
    assert duration.measurement == "not_recorded"


def test_provider_duration_with_missing_attempt_measurement_is_incomplete():
    now, identity = datetime.now(timezone.utc), uuid4()
    provider = ProviderDiagnostic(
        provider_phase_id=identity,
        phase="generation",
        state="COMPLETED",
        attempt=2,
        attempt_limit=2,
        dispatch="RESPONSE_OBSERVED",
        retry_classification=None,
        error_code=None,
        error_category=None,
        usage=None,
        estimated_yuan=None,
        price_revision=None,
    )
    signals = (
        ReliabilitySignal(
            id=uuid4(),
            created_at=now,
            kind="provider_completed",
            fence=1,
            provider_phase_id=identity,
            attempt=2,
            latency_ms=0,
        ),
    )
    value = diagnose("ACCEPTED", now, now, signals, False, (provider,))
    duration = next(d for d in value.durations if d.phase == "provider")
    assert duration.latency_ms == 0 and duration.availability == "INCOMPLETE"


@pytest.mark.parametrize(
    "code,classification,category",
    [
        ("llm_http_503", "UNKNOWN", "provider_unknown"),
        ("llm_http_429", "RETRYABLE_KNOWN", "provider_known_safe"),
        ("deadline_elapsed", None, "deadline"),
        ("provider_attempt_fenced", None, "stale_fenced"),
        ("IntegrityError", None, "database_transaction"),
        ("documentary_answer_citation_conflict", None, "validation"),
    ],
)
def test_operational_taxonomy_never_redefines_retry(code, classification, category):
    assert operational_category(code, classification=classification) == category
    if classification:
        assert classify(code, True) == classification
