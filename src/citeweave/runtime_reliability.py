"""Conversation-only policy and allowlisted durable reliability signals."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from citeweave.conversation_contract import DurableDTO

RetryClass = Literal["BEFORE_DISPATCH", "RETRYABLE_KNOWN", "PERMANENT", "UNKNOWN"]


def classify(code: str, dispatched: bool) -> RetryClass:
    if code in {
        "llm_http_400",
        "llm_http_401",
        "llm_http_403",
        "llm_key_missing",
        "provider_request_identity_conflict",
    }:
        return "PERMANENT"
    if code in {"llm_connection_failed", "llm_http_429", "circuit_open"}:
        return "RETRYABLE_KNOWN"
    return "UNKNOWN" if dispatched else "BEFORE_DISPATCH"


def retry_delay(attempt: int, random_fraction: float) -> float:
    return min(4.0, 0.5 * 2 ** min(max(attempt - 1, 0), 3)) * max(0.0, min(1.0, random_fraction))


class ReliabilitySignal(DurableDTO):
    id: UUID
    created_at: datetime
    kind: Literal[
        "admitted",
        "execution_started",
        "provider_prepared",
        "provider_attempt",
        "provider_dispatched",
        "provider_completed",
        "provider_failure",
        "provider_retry",
        "accepted",
        "finished",
        "cancelled",
        "recovered",
        "stage_started",
        "stage_completed",
        "stage_failed",
        "stale_result_rejected",
    ]
    fence: int
    phase: (
        Literal["history", "interpretation", "retrieval", "generation", "validation", "publication"] | None
    ) = None
    current_fence: int | None = None
    provider_phase_id: UUID | None = None
    attempt: int | None = None
    from_state: str | None = None
    to_state: str | None = None
    retry_classification: RetryClass | None = None
    error_class: str | None = Field(default=None, max_length=80)
    latency_ms: float | None = Field(default=None, ge=0)
    usage: dict[str, int] | None = None


def event(db, run, kind, **detail):
    from uuid import uuid4

    from citeweave.conversation_models import ConversationRunEventRow
    from citeweave.conversations import _clock

    if detail.get("provider_phase_id") and "phase" not in detail:
        from citeweave.domain import ProviderPhaseRow

        detail["phase"] = db.get(ProviderPhaseRow, detail["provider_phase_id"]).phase
    value = ReliabilitySignal(id=uuid4(), created_at=_clock(db), kind=kind, fence=run.fence, **detail)
    db.add(
        ConversationRunEventRow(
            run_id=run.id,
            **value.model_dump(exclude={"provider_phase_id"}),
            provider_phase_id=value.provider_phase_id,
        )
    )


def read_events(db, run_id):
    from sqlalchemy import select

    from citeweave.conversation_models import ConversationRunEventRow as Event

    rows = list(
        db.scalars(
            select(Event)
            .where(Event.run_id == run_id)
            .order_by(Event.created_at.desc(), Event.id.desc())
            .limit(65)
        )
    )
    return tuple(ReliabilitySignal.model_validate(row) for row in reversed(rows[:64])), len(rows) > 64
