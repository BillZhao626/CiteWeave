"""Bounded typed diagnostics over existing PostgreSQL facts, never retry authority."""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from citeweave.conversation_contract import CoreConflict, DurableDTO
from citeweave.runtime_reliability import ReliabilitySignal, event

Phase = Literal[
    "admission_queue",
    "history",
    "interpretation",
    "retrieval",
    "generation",
    "validation",
    "publication",
    "provider",
    "total",
]
Category = Literal[
    "admission",
    "validation",
    "database_transaction",
    "retrieval",
    "provider_known_safe",
    "provider_unknown",
    "provider_permanent",
    "cancellation",
    "deadline",
    "reconciliation",
    "stale_fenced",
    "internal_invariant",
]
Availability = Literal["AVAILABLE", "UNAVAILABLE", "INCOMPLETE", "UNKNOWN", "CANCELLED"]
_observer = ContextVar("conversation_operational_observer", default=None)


def safe_error_code(exc):
    # Only application-owned exception codes; never arbitrary exception messages.
    from citeweave.llm import ProviderError

    if isinstance(exc, SQLAlchemyError):
        return "database_transaction_failed"
    if isinstance(exc, (CoreConflict, ProviderError)):
        code = exc.code if isinstance(exc, ProviderError) else str(exc)
        if code and len(code) <= 80 and all(c.isascii() and (c.isalnum() or c == "_") for c in code):
            return code
    if isinstance(exc, TimeoutError):
        return "deadline_elapsed"
    from pydantic import ValidationError

    return "local_validation_failed" if isinstance(exc, ValidationError) else "internal_error"


def operational_category(code, *, classification=None, phase=None, kind=None):
    if classification == "UNKNOWN":
        return "provider_unknown"
    if classification in {"BEFORE_DISPATCH", "RETRYABLE_KNOWN"}:
        return "provider_known_safe"
    if classification == "PERMANENT":
        return "provider_permanent"
    if (
        kind == "stale_result_rejected"
        or code
        and ("fenced" in code or code in {"stale_owner", "stale_fence", "run_not_active", "head_changed"})
    ):
        return "stale_fenced"
    if kind == "cancelled" or code == "cancel_requested":
        return "cancellation"
    if code and ("deadline" in code or code == "request_timeout"):
        return "deadline"
    if kind == "recovered" or code == "execution_expired":
        return "reconciliation"
    if code in {"database_transaction_failed", "IntegrityError", "OperationalError", "DBAPIError"}:
        return "database_transaction"
    if phase == "retrieval" or code and code.startswith(("index_", "model_")):
        return "retrieval"
    if code and code.startswith(
        ("admission_", "runtime_request_", "provider_input_authorization", "provider_phase_not_authorized")
    ):
        return "admission"
    if (
        phase == "validation"
        or code
        and code.startswith(("documentary_", "interpretation_", "local_validation", "conversation_context_"))
    ):
        return "validation"
    return "internal_invariant" if code else None


class TimelineItem(ReliabilitySignal):
    error_code: str | None = None
    error_category: Category | None = None


class Duration(DurableDTO):
    phase: Phase
    availability: Availability
    latency_ms: float | None = Field(default=None, ge=0)
    measurement: Literal["db_timestamp_difference", "local_monotonic", "not_recorded"] = "not_recorded"


class ProviderDiagnostic(DurableDTO):
    provider_phase_id: UUID
    phase: Literal["interpretation", "generation"]
    state: str
    attempt: int | None
    attempt_limit: int
    dispatch: Literal[
        "NOT_RECORDED", "MARKER_COMMITTED_SEND_UNCONFIRMED", "RESPONSE_OBSERVED", "KNOWN_NOT_EXECUTED"
    ]
    retry_classification: str | None
    error_code: str | None
    error_category: Category | None
    usage: dict[str, int] | None
    estimated_yuan: Decimal | None
    price_revision: str | None


class OperationalTrace(DurableDTO):
    revision: Literal["operational-trace-v1"] = "operational-trace-v1"
    timeline: tuple[TimelineItem, ...] = ()
    truncated: bool = False
    durations: tuple[Duration, ...] = ()
    total: Duration
    provider_phases: tuple[ProviderDiagnostic, ...] = ()
    retry_decision: Literal[
        "BLOCKED_UNKNOWN",
        "TERMINAL_NO_DISPATCH",
        "EXPLICIT_NEW_AUTHORIZATION_REQUIRED",
        "POLICY_AND_KNOWN_PROOF_REQUIRED",
    ]
    publication: Literal["ACCEPTED", "NOT_ACCEPTED"]
    unknown_reason: (
        Literal[
            "PROVIDER_UNCERTAIN",
            "KNOWN_RESULT_NOT_ACCEPTED",
            "CANCELLED_WITH_UNRESOLVED_PROVIDER",
            "LEGACY_REASON_UNAVAILABLE",
        ]
        | None
    ) = None


def provider_diagnostics(db, run_id):
    from citeweave.domain import ProviderPhaseRow as Provider

    # Product schema admits only one phase per purpose. No legacy/Eval rows included.
    rows = db.scalars(
        select(Provider)
        .where(Provider.conversation_run_id == run_id)
        .order_by(Provider.reserved_at, Provider.id)
        .limit(2)
    )
    return tuple(
        ProviderDiagnostic(
            provider_phase_id=r.id,
            phase=r.phase,
            state=r.state,
            attempt=r.transport_attempt or None,
            attempt_limit=r.transport_limit,
            dispatch=(
                "RESPONSE_OBSERVED"
                if r.state == "COMPLETED"
                or (r.error_code or "").startswith("llm_http_")
                or r.usage is not None
                or r.request_id is not None
                or r.result_hash is not None
                else "KNOWN_NOT_EXECUTED"
                if r.outcome == "known_not_executed"
                else "MARKER_COMMITTED_SEND_UNCONFIRMED"
                if r.dispatched_at
                else "NOT_RECORDED"
            ),
            retry_classification=r.retry_classification,
            error_code=r.error_code,
            error_category=operational_category(r.error_code, classification=r.retry_classification),
            usage=r.usage,
            estimated_yuan=r.estimated_yuan,
            price_revision=r.price_revision,
        )
        for r in rows
    )


def diagnose(status, created_at, completed_at, signals, truncated, providers):
    providers = tuple(providers)
    phases = {p.provider_phase_id: p.phase for p in providers}
    timeline = tuple(
        TimelineItem(
            **s.model_dump(exclude={"phase"}),
            phase=s.phase or phases.get(s.provider_phase_id),
            error_code=s.error_class,
            error_category=operational_category(
                s.error_class, classification=s.retry_classification, phase=s.phase, kind=s.kind
            ),
        )
        for s in sorted(signals, key=lambda s: (s.created_at, s.id))
    )
    durations = []
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
        completed = [
            s
            for s in timeline
            if s.latency_ms is not None
            and (
                s.kind in {"provider_completed", "provider_failure"}
                if phase == "provider"
                else s.phase == phase and s.kind in {"stage_completed", "stage_failed"}
            )
        ]
        invalid_timestamp = False
        if phase == "admission_queue":
            starts = [s for s in timeline if s.kind == "execution_started"]
            invalid_timestamp = bool(starts and starts[0].created_at < created_at)
            latency = (
                (starts[0].created_at - created_at).total_seconds() * 1000
                if starts and not invalid_timestamp
                else None
            )
            measurement = "db_timestamp_difference" if latency is not None else "not_recorded"
        else:
            latency = sum(s.latency_ms for s in completed) if completed else None
            measurement = "local_monotonic" if completed else "not_recorded"
        incomplete = (
            truncated
            or invalid_timestamp
            or phase == "provider"
            and any(
                p.state in {"DISPATCHED", "UNKNOWN"}
                or p.attempt is not None
                and len(
                    {
                        s.attempt
                        for s in completed
                        if s.provider_phase_id == p.provider_phase_id and s.attempt is not None
                    }
                )
                < p.attempt
                for p in providers
            )
            or any(s.phase == phase and s.kind == "stage_started" for s in timeline)
            and len(completed) < sum(s.phase == phase and s.kind == "stage_started" for s in timeline)
        )
        durations.append(
            Duration(
                phase=phase,
                latency_ms=latency,
                measurement=measurement,
                availability="INCOMPLETE"
                if incomplete
                else "AVAILABLE"
                if latency is not None
                else "UNAVAILABLE",
            )
        )
    total_ms = (
        (completed_at - created_at).total_seconds() * 1000
        if completed_at and completed_at >= created_at
        else None
    )
    total = Duration(
        phase="total",
        latency_ms=total_ms,
        measurement="db_timestamp_difference" if total_ms is not None else "not_recorded",
        availability=status
        if status in {"UNKNOWN", "CANCELLED"}
        else "AVAILABLE"
        if total_ms is not None
        else "INCOMPLETE",
    )
    return OperationalTrace(
        timeline=timeline,
        truncated=truncated,
        durations=tuple(durations),
        total=total,
        provider_phases=providers,
        publication="ACCEPTED" if status == "ACCEPTED" else "NOT_ACCEPTED",
        unknown_reason=(
            "CANCELLED_WITH_UNRESOLVED_PROVIDER"
            if status == "CANCELLED" and any(p.state == "UNKNOWN" for p in providers)
            else "KNOWN_RESULT_NOT_ACCEPTED"
            if status == "UNKNOWN" and any(p.state == "COMPLETED" for p in providers)
            else "PROVIDER_UNCERTAIN"
            if status == "UNKNOWN" and any(p.state in {"UNKNOWN", "DISPATCHED"} for p in providers)
            else "LEGACY_REASON_UNAVAILABLE"
            if status == "UNKNOWN"
            else None
        ),
        retry_decision="BLOCKED_UNKNOWN"
        if status == "UNKNOWN"
        or any(p.state in {"DISPATCHED", "UNKNOWN", "COMPLETED"} for p in providers)
        and status != "ACCEPTED"
        else "EXPLICIT_NEW_AUTHORIZATION_REQUIRED"
        if status == "INTERRUPTED"
        else "POLICY_AND_KNOWN_PROOF_REQUIRED"
        if status == "ADMITTED"
        else "TERMINAL_NO_DISPATCH",
    )


@contextmanager
def observe(workspace, run):
    token = _observer.set((workspace, run))
    try:
        yield
    finally:
        _observer.reset(token)


def _record(workspace, supplied, kind, phase, **detail):
    from citeweave import conversations as core
    from citeweave.db import transaction

    # Lock and verify identity only. Workflow guards retain execution authority;
    # an observation must not add a deadline/status gate to the observed operation.
    with transaction() as db:
        conversation = core._conversation(db, workspace, supplied.conversation_id)
        run = core._run(db, supplied.conversation_id, supplied.turn_id, supplied.id)
        if run.owner != supplied.owner or run.fence != supplied.fence:
            raise CoreConflict("stale_owner")
        event(
            db,
            run,
            kind,
            phase=phase,
            current_fence=conversation.fence,
            to_state={"stage_started": "RUNNING", "stage_completed": "COMPLETED", "stage_failed": "FAILED"}[
                kind
            ],
            **detail,
        )
        db.flush()


@contextmanager
def operational_stage(phase):
    observer = _observer.get()
    if observer is None:
        yield
        return
    _record(*observer, "stage_started", phase)
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        _record(
            *observer,
            "stage_failed",
            phase,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            error_class=safe_error_code(exc),
        )
        raise
    else:
        if phase != "publication":
            _record(
                *observer,
                "stage_completed",
                phase,
                latency_ms=round((time.perf_counter() - started) * 1000, 3),
            )


def publication_fact(db, run, started):
    # Atomic with Acceptance; excludes final flush/commit acknowledgement.
    if _observer.get() is not None:
        event(
            db,
            run,
            "stage_completed",
            phase="publication",
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
        )


def record_fenced(workspace, supplied, error_code):
    # A failed late worker may append a diagnostic; it cannot change Run/accounting/result.
    from citeweave import conversations as core
    from citeweave.db import transaction

    if error_code not in {"stale_owner", "run_not_active"}:
        return
    with transaction() as db:
        conversation = core._conversation(db, workspace, supplied.conversation_id)
        run = core._run(db, supplied.conversation_id, supplied.turn_id, supplied.id)
        if run.owner != supplied.owner or run.fence != supplied.fence:
            raise CoreConflict("stale_owner")
        from citeweave.conversation_models import ConversationRunEventRow as Event

        if db.scalar(
            select(Event.id)
            .where(
                Event.run_id == run.id,
                Event.kind == "stale_result_rejected",
                Event.fence == run.fence,
                Event.current_fence == conversation.fence,
            )
            .limit(1)
        ):
            return
        event(
            db,
            run,
            "stale_result_rejected",
            current_fence=conversation.fence,
            error_class=error_code,
            to_state=run.status,
        )
        db.flush()
