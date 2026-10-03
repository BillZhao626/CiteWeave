"""Conversation provider ledger and immutable aggregate Run authorization.

No transport here. Explicit phase grants consume the Run envelope permanently;
an absent grant authorizes zero calls/spending. Synthetic test grants are not
production spending grants.
"""

from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt
from sqlalchemy import select

from citeweave import conversations as core
from citeweave.conversation_contract import Admission, CoreConflict, DurableDTO, require_head, require_owner
from citeweave.costs import RATE_CARD, estimated_cost
from citeweave.db import transaction
from citeweave.domain import ProviderPhaseRow
from citeweave.provider_phases import KNOWN_NOT_EXECUTED
from citeweave.runtime_reliability import classify, event

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
TokenCount = Annotated[StrictInt, Field(ge=0)]


class RunAuthorization(DurableDTO):
    id: UUID
    run_id: UUID
    expires_at: AwareDatetime
    max_calls: int = Field(ge=0, le=2147483647, strict=True)
    max_input_tokens: int = Field(ge=0, le=9223372036854775807, strict=True)
    max_output_tokens: int = Field(ge=0, le=9223372036854775807, strict=True)
    max_yuan: Decimal = Field(ge=0, max_digits=12, decimal_places=8, allow_inf_nan=False)


def authorize_run(workspace, supplied, authorization: RunAuthorization):
    grant = RunAuthorization.model_validate(authorization.model_dump())
    if grant.run_id != supplied.id:
        raise CoreConflict("run_authorization_identity_conflict")
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        if not now < grant.expires_at <= run.deadline:
            raise CoreConflict("run_authorization_deadline_conflict")
        values = dict(
            authorization_id=grant.id,
            authorization_deadline=grant.expires_at,
            authorization_max_calls=grant.max_calls,
            authorization_input_tokens=grant.max_input_tokens,
            authorization_output_tokens=grant.max_output_tokens,
            authorization_yuan=grant.max_yuan,
        )
        if run.authorization_id is not None:
            if any(getattr(run, key) != value for key, value in values.items()):
                raise CoreConflict("run_authorization_conflict")
            return
        if db.scalar(
            select(ProviderPhaseRow.id).where(ProviderPhaseRow.conversation_run_id == run.id).limit(1)
        ):
            raise CoreConflict("run_authorization_after_reservation")
        for key, value in values.items():
            setattr(run, key, value)
        db.flush()
        _, now = _owned(db, workspace, supplied)
        if grant.expires_at <= now:
            raise CoreConflict("run_authorization_expired")


def _aggregate(db, run, now, candidate=None):
    if run.authorization_id is None:
        raise CoreConflict("run_authorization_required")
    if run.authorization_deadline <= now:
        raise CoreConflict("run_authorization_expired")
    rows = list(db.scalars(select(ProviderPhaseRow).where(ProviderPhaseRow.conversation_run_id == run.id)))
    calls = sum(p.transport_limit for p in rows) + (candidate.max_attempts if candidate else 0)
    inputs = sum(p.input_tokens * p.transport_limit for p in rows) + (
        candidate.input_tokens * candidate.max_attempts if candidate else 0
    )
    outputs = sum(p.output_tokens * p.transport_limit for p in rows) + (
        candidate.output_tokens * candidate.max_attempts if candidate else 0
    )
    amount = sum((p.reserved_yuan * p.transport_limit for p in rows), Decimal(0)) + (
        candidate.max_yuan * candidate.max_attempts if candidate else Decimal(0)
    )
    if (
        calls > run.authorization_max_calls
        or inputs > run.authorization_input_tokens
        or outputs > run.authorization_output_tokens
        or amount > run.authorization_yuan
    ):
        raise CoreConflict("run_authorization_exceeded")
    if candidate and candidate.expires_at > run.authorization_deadline:
        raise CoreConflict("run_authorization_deadline_conflict")
    if any(p.authorization_deadline > run.authorization_deadline for p in rows):
        raise CoreConflict("run_authorization_deadline_conflict")
    if any(
        p.usage
        and (
            p.usage.get("prompt_tokens", 0) > p.input_tokens
            or p.usage.get("completion_tokens", 0) > p.output_tokens
        )
        for p in rows
    ):
        raise CoreConflict("provider_usage_exceeded_authorization")


class CallAuthorization(DurableDTO):
    id: UUID
    run_id: UUID
    purpose: Literal["interpretation", "generation"]
    provider: Literal["deepseek"]
    model: Literal["deepseek-flash"]
    price_revision: Literal["deepseek-flash-CNY-2026-09-13"]
    prompt_revision: str = Field(min_length=1, max_length=160)
    request_hash: Hash
    input_tokens: int = Field(gt=0, le=2147483647, strict=True)
    output_tokens: int = Field(gt=0, le=2147483647, strict=True)
    max_yuan: Decimal = Field(gt=0, max_digits=12, decimal_places=8, allow_inf_nan=False)
    expires_at: AwareDatetime
    max_attempts: int = Field(default=1, ge=1, le=3, strict=True)


class Usage(DurableDTO):
    prompt_tokens: TokenCount | None = None
    completion_tokens: TokenCount | None = None
    total_tokens: TokenCount | None = None
    prompt_cache_hit_tokens: TokenCount | None = None
    prompt_cache_miss_tokens: TokenCount | None = None


class Observation(DurableDTO):
    request_id: str | None = Field(default=None, min_length=1, max_length=200)
    result_hash: Hash | None = None
    usage: Usage | None = None


def _owned(db, workspace, supplied):
    conversation = core._conversation(db, workspace, supplied.conversation_id)
    turn = core._turn(db, conversation.id, supplied.turn_id)
    run = core._run(db, conversation.id, turn.id, supplied.id)
    request = Admission.model_validate(turn.request)
    core._scope(db, workspace, request.scope, current=True)
    require_head(conversation.head_id, turn.expected_head)
    now = core._clock(db)
    require_owner(
        run.status,
        run.owner,
        run.fence,
        supplied.owner,
        supplied.fence,
        conversation.fence,
        run.deadline,
        now,
    )
    if supplied != core._run_view(run, turn):
        raise CoreConflict("provider_run_identity_conflict")
    return run, now


def _phase(db, run, identity, now):
    row = db.get(ProviderPhaseRow, identity)
    if row is None or row.conversation_run_id != run.id or (row.owner, row.fence) != (run.owner, run.fence):
        raise CoreConflict("provider_phase_identity_conflict")
    if row.authorization_deadline <= now:
        raise CoreConflict("provider_authorization_expired")
    return row


def _flush_owned(db, workspace, supplied, row):
    # As in Core acceptance, a slow write must not cross an elapsed DB deadline.
    db.flush()
    run, now = _owned(db, workspace, supplied)
    _phase(db, run, row.id, now)


def prepare(workspace, supplied, authorization: CallAuthorization):
    grant = CallAuthorization.model_validate(authorization.model_dump())
    if grant.run_id != supplied.id or grant.price_revision != RATE_CARD:
        raise CoreConflict("provider_authorization_identity_conflict")
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        if not now < grant.expires_at <= run.deadline:
            raise CoreConflict("provider_authorization_deadline_conflict")
        values = dict(
            conversation_run_id=run.id,
            provider=grant.provider,
            model=grant.model,
            price_revision=grant.price_revision,
            authorization_id=grant.id,
            authorization_deadline=grant.expires_at,
            input_tokens=grant.input_tokens,
            output_tokens=grant.output_tokens,
            prompt_revision=grant.prompt_revision,
            request_hash=grant.request_hash,
            reserved_yuan=grant.max_yuan,
            phase=grant.purpose,
            phase_attempt=1,
            owner=run.owner,
            fence=run.fence,
            logical_key=f"conversation:{run.id}:{grant.purpose}",
            transport_limit=grant.max_attempts,
        )
        row = db.scalar(
            select(ProviderPhaseRow).where(
                ProviderPhaseRow.conversation_run_id == run.id, ProviderPhaseRow.phase == grant.purpose
            )
        )
        if row:
            if any(getattr(row, k) != v for k, v in values.items()):
                raise CoreConflict("provider_authorization_conflict")
            _aggregate(db, run, now)
            return row  # Read receipt only; dispatch separately rejects every non-PREPARED state.
        _aggregate(db, run, now, grant)
        if unresolved(db, run.id):
            raise CoreConflict("provider_outcome_unknown")
        row = ProviderPhaseRow(**values, reserved_at=now)
        db.add(row)
        _flush_owned(db, workspace, supplied, row)
        event(db, run, "provider_prepared", provider_phase_id=row.id, attempt=0, to_state="PREPARED")
        return row


def dispatch(workspace, supplied, identity, *, attempt=None):
    """Commit permission BEFORE future transport. Repeated dispatch fails closed."""
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        _attempt(row, attempt)
        if row.state != "PREPARED" or row.retry_after is not None:
            raise CoreConflict("provider_phase_not_dispatchable")
        if unresolved(db, run.id):
            raise CoreConflict("provider_outcome_unknown")
        row.state, row.outcome = "DISPATCHED", "unknown"
        row.dispatched_at = now  # Current attempt prices at its actual dispatch; events retain earlier sends.
        row.error_code, row.retry_classification = None, None
        row.estimated_yuan = None
        event(
            db,
            run,
            "provider_dispatched",
            provider_phase_id=row.id,
            attempt=row.transport_attempt or 1,
            from_state="PREPARED",
            to_state="DISPATCHED",
        )
        _aggregate(db, run, now)
        _flush_owned(db, workspace, supplied, row)
        _aggregate(db, run, core._clock(db))


def complete(workspace, supplied, identity, observation: Observation, *, attempt=None, latency_ms=None):
    receipt = Observation.model_validate(observation.model_dump())
    if receipt.result_hash is None:
        raise CoreConflict("provider_result_identity_required")
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        _attempt(row, attempt)
        if row.state != "DISPATCHED" or row.dispatched_at is None:
            raise CoreConflict("provider_phase_not_dispatched")
        row.state, row.outcome = "COMPLETED", "known"
        _observation(row, receipt)
        event(
            db,
            run,
            "provider_completed",
            provider_phase_id=row.id,
            attempt=row.transport_attempt or 1,
            from_state="DISPATCHED",
            to_state="COMPLETED",
            latency_ms=latency_ms,
            usage=row.usage,
        )
        _flush_owned(db, workspace, supplied, row)


def _observation(row, receipt):
    row.request_id, row.result_hash = receipt.request_id, receipt.result_hash
    row.usage = receipt.usage.model_dump(exclude_none=True) if receipt.usage else None
    # Preserve reported usage, including over-budget observations; never infer
    # missing counts or label an estimate as the provider's actual charge.
    row.estimated_yuan = (
        estimated_cost(row.usage, row.dispatched_at) if row.price_revision == RATE_CARD else None
    )


def reject_prepared(workspace, supplied, identity, code: Literal["local_validation_failed"]):
    if code != "local_validation_failed":
        raise CoreConflict("provider_rejection_not_proven")
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        _attempt(row, None)
        if row.state != "PREPARED" or row.dispatched_at is not None:
            raise CoreConflict("provider_phase_not_prepared")
        row.state, row.outcome, row.error_code = "REJECTED", "known_not_executed", code
        row.estimated_yuan = Decimal(0)
        _flush_owned(db, workspace, supplied, row)


def record_unknown(
    workspace,
    supplied,
    identity,
    code: Literal["response_lost", "request_timeout"],
    observation: Observation | None = None,
    *,
    attempt=None,
):
    if code not in {"response_lost", "request_timeout"}:
        raise CoreConflict("provider_unknown_code_invalid")
    receipt = Observation.model_validate(observation.model_dump()) if observation else None
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        _attempt(row, attempt)
        if row.state != "DISPATCHED":
            raise CoreConflict("provider_phase_not_dispatched")
        row.state, row.outcome, row.error_code = "UNKNOWN", "unknown", code
        row.retry_classification = "UNKNOWN"
        if receipt is not None:
            _observation(row, receipt)
        _flush_owned(db, workspace, supplied, row)
        event(
            db,
            run,
            "provider_failure",
            provider_phase_id=row.id,
            attempt=row.transport_attempt or 1,
            from_state="DISPATCHED",
            to_state="UNKNOWN",
            retry_classification="UNKNOWN",
            error_class=code,
        )


def reject_dispatched(workspace, supplied, identity, code):
    """Record a direct known non-execution observation, never infer it from expiry."""
    if code not in KNOWN_NOT_EXECUTED:
        raise CoreConflict("provider_rejection_not_proven")
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        _attempt(row, None)
        if row.state != "DISPATCHED" or row.dispatched_at is None:
            raise CoreConflict("provider_phase_not_dispatched")
        row.state, row.outcome, row.error_code = "REJECTED", "known_not_executed", code
        row.estimated_yuan = Decimal(0)
        _flush_owned(db, workspace, supplied, row)


def blocks_retry(db, run_id):
    """A completed call without Acceptance still cannot authorize a fresh paid call."""
    return (
        db.scalar(
            select(ProviderPhaseRow.id)
            .where(
                ProviderPhaseRow.conversation_run_id == run_id,
                ProviderPhaseRow.dispatched_at.is_not(None),
                ~(
                    (ProviderPhaseRow.state.in_(["REJECTED", "PREPARED"]))
                    & (ProviderPhaseRow.outcome == "known_not_executed")
                ),
            )
            .limit(1)
        )
        is not None
    )


def unresolved(db, run_id):
    return (
        db.scalar(
            select(ProviderPhaseRow.id)
            .where(
                ProviderPhaseRow.conversation_run_id == run_id,
                ProviderPhaseRow.state.in_(["DISPATCHED", "UNKNOWN"]),
            )
            .limit(1)
        )
        is not None
    )


def permanent_failure(db, run_id):
    return (
        db.scalar(
            select(ProviderPhaseRow.id)
            .where(
                ProviderPhaseRow.conversation_run_id == run_id,
                ProviderPhaseRow.state == "REJECTED",
                ProviderPhaseRow.retry_classification == "PERMANENT",
            )
            .limit(1)
        )
        is not None
    )


def reconcile(db, run_id, *, code="execution_expired"):
    """Caller holds Conversation lock. Preserve completed receipts and reservations."""
    blocked = blocks_retry(db, run_id)
    for row in db.scalars(
        select(ProviderPhaseRow).where(
            ProviderPhaseRow.conversation_run_id == run_id, ProviderPhaseRow.state == "DISPATCHED"
        )
    ):
        row.state, row.outcome, row.error_code = "UNKNOWN", "unknown", code
        row.retry_classification = "UNKNOWN"
        run = db.get(core.Run, run_id)
        event(
            db,
            run,
            "provider_failure",
            provider_phase_id=row.id,
            attempt=row.transport_attempt or 1,
            from_state="DISPATCHED",
            to_state="UNKNOWN",
            retry_classification="UNKNOWN",
            error_class=code,
        )
    return blocked


def _attempt(row, attempt):
    # Old one-send callers cannot mutate the receipt of a newer transport attempt.
    if attempt is None:
        if row.transport_limit > 1 or row.transport_attempt > 1:
            raise CoreConflict("provider_attempt_required")
    elif row.transport_attempt != attempt:
        raise CoreConflict("stale_provider_attempt")


def begin_attempt(workspace, supplied, identity):
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        if row.state != "PREPARED" or row.transport_attempt >= row.transport_limit:
            raise CoreConflict("provider_attempt_not_allowed")
        # Only initial transport or a durably scheduled known-safe retry.
        if row.transport_attempt and (row.retry_after is None or row.retry_after > now):
            raise CoreConflict("provider_retry_not_due")
        row.transport_attempt += 1
        row.retry_after = None
        event(
            db,
            run,
            "provider_attempt",
            provider_phase_id=row.id,
            attempt=row.transport_attempt,
            to_state="PREPARED",
        )
        _flush_owned(db, workspace, supplied, row)
        return row.transport_attempt


def fail_attempt(workspace, supplied, identity, attempt, code, *, dispatched, latency_ms, observation=None):
    classification = classify(code, dispatched)
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        _attempt(row, attempt)
        expected = "DISPATCHED" if dispatched else "PREPARED"
        if row.state != expected:
            raise CoreConflict("provider_failure_receipt_conflict")
        # A committed dispatch whose acknowledgement was lost is still uncertain.
        if dispatched and classification != "UNKNOWN" and code not in KNOWN_NOT_EXECUTED:
            raise CoreConflict("provider_rejection_not_proven")
        row.state = "UNKNOWN" if classification == "UNKNOWN" else "REJECTED"
        row.outcome = "unknown" if classification == "UNKNOWN" else "known_not_executed"
        row.error_code, row.retry_classification = code, classification
        if classification != "UNKNOWN":
            row.estimated_yuan = Decimal(0)
        elif observation is not None:
            _observation(row, Observation.model_validate(observation.model_dump()))
        event(
            db,
            run,
            "provider_failure",
            provider_phase_id=row.id,
            attempt=attempt,
            from_state=expected,
            to_state=row.state,
            retry_classification=classification,
            error_class=code,
            latency_ms=latency_ms,
        )
        _flush_owned(db, workspace, supplied, row)
        return classification


def schedule_retry(workspace, supplied, identity, attempt, delay):
    if not 0 <= delay <= 4:
        raise CoreConflict("provider_retry_delay_invalid")
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        _attempt(row, attempt)
        if (
            row.state != "REJECTED"
            or row.outcome != "known_not_executed"
            or row.retry_classification != "RETRYABLE_KNOWN"
            or row.transport_attempt >= row.transport_limit
        ):
            raise CoreConflict("provider_retry_not_allowed")
        # Earlier phases may have consumed a side effect; this retry only applies
        # to this phase's proved non-execution, never to the completed phase.
        if unresolved(db, run.id):
            raise CoreConflict("provider_outcome_unknown")
        row.retry_after = now + timedelta(seconds=delay)
        if row.retry_after >= min(run.deadline, row.authorization_deadline):
            raise CoreConflict("provider_retry_deadline_elapsed")
        row.state, row.outcome = "PREPARED", "known_not_executed"
        event(
            db,
            run,
            "provider_retry",
            provider_phase_id=row.id,
            attempt=attempt,
            from_state="REJECTED",
            to_state="PREPARED",
            retry_classification="RETRYABLE_KNOWN",
        )
        _aggregate(db, run, now)
        _flush_owned(db, workspace, supplied, row)
