"""Conversation adapter for the existing provider ledger. No transport/runtime wiring.

Each explicit authorization reserves ONE call for ONE Run/purpose. Positive
synthetic authorizations in tests are not production spending grants. Admission
policy, aggregate budgets and external execution remain #5c-2 responsibilities.
"""

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

Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
TokenCount = Annotated[StrictInt, Field(ge=0)]


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
        )
        row = db.scalar(
            select(ProviderPhaseRow).where(
                ProviderPhaseRow.conversation_run_id == run.id, ProviderPhaseRow.phase == grant.purpose
            )
        )
        if row:
            if any(getattr(row, k) != v for k, v in values.items()):
                raise CoreConflict("provider_authorization_conflict")
            return row  # Read receipt only; dispatch separately rejects every non-PREPARED state.
        if unresolved(db, run.id):
            raise CoreConflict("provider_outcome_unknown")
        row = ProviderPhaseRow(**values, reserved_at=now)
        db.add(row)
        _flush_owned(db, workspace, supplied, row)
        return row


def dispatch(workspace, supplied, identity):
    """Commit permission BEFORE future transport. Repeated dispatch fails closed."""
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        if row.state != "PREPARED" or row.dispatched_at is not None:
            raise CoreConflict("provider_phase_not_dispatchable")
        if unresolved(db, run.id):
            raise CoreConflict("provider_outcome_unknown")
        row.state, row.outcome, row.dispatched_at = "DISPATCHED", "unknown", now
        _flush_owned(db, workspace, supplied, row)


def complete(workspace, supplied, identity, observation: Observation):
    receipt = Observation.model_validate(observation.model_dump())
    if receipt.result_hash is None:
        raise CoreConflict("provider_result_identity_required")
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        if row.state != "DISPATCHED" or row.dispatched_at is None:
            raise CoreConflict("provider_phase_not_dispatched")
        row.state, row.outcome = "COMPLETED", "known"
        _observation(row, receipt)
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
):
    if code not in {"response_lost", "request_timeout"}:
        raise CoreConflict("provider_unknown_code_invalid")
    receipt = Observation.model_validate(observation.model_dump()) if observation else None
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
        if row.state != "DISPATCHED":
            raise CoreConflict("provider_phase_not_dispatched")
        row.state, row.outcome, row.error_code = "UNKNOWN", "unknown", code
        if receipt is not None:
            _observation(row, receipt)
        _flush_owned(db, workspace, supplied, row)


def reject_dispatched(workspace, supplied, identity, code):
    """Record a direct known non-execution observation, never infer it from expiry."""
    if code not in KNOWN_NOT_EXECUTED:
        raise CoreConflict("provider_rejection_not_proven")
    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        row = _phase(db, run, identity, now)
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
                    (ProviderPhaseRow.state == "REJECTED")
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


def reconcile(db, run_id):
    """Caller holds Conversation lock. Preserve completed receipts and reservations."""
    blocked = blocks_retry(db, run_id)
    for row in db.scalars(
        select(ProviderPhaseRow).where(
            ProviderPhaseRow.conversation_run_id == run_id, ProviderPhaseRow.state == "DISPATCHED"
        )
    ):
        row.state, row.outcome, row.error_code = "UNKNOWN", "unknown", "execution_expired"
    return blocked
