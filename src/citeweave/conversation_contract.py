"""Internal persistence contract, not a conversational API or execution profile."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from citeweave.catalog import fingerprint as json_fingerprint

OperationKey = Annotated[str, Field(min_length=1, max_length=128)]


class CoreConflict(ValueError):
    """Stable internal conflict code; callers must not silently retry execution."""


class DurableDTO(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class Scope(DurableDTO):
    kb_id: UUID
    version_ids: tuple[UUID, ...] = Field(min_length=1)

    @field_validator("version_ids")
    @classmethod
    def canonical_versions(cls, value):
        if len(set(value)) != len(value):
            raise ValueError("duplicate_version")
        return tuple(sorted(value))


class Admission(DurableDTO):
    question: str = Field(min_length=1)
    scope: Scope
    expected_head: UUID | None
    # This revision describes only persistence. It cannot authorize a model runtime.
    profile: Literal["conversation-core-v1"] = "conversation-core-v1"


class Execution(DurableDTO):
    owner: UUID
    deadline: AwareDatetime


class Operation(DurableDTO):
    key: OperationKey


class RunStatus(StrEnum):
    ADMITTED = "ADMITTED"
    ACCEPTED = "ACCEPTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


class ProducedResult(DurableDTO):
    # Already produced/validated control payloads only. Documentary answers require
    # later EvidencePack/Citation integration and are deliberately rejected here.
    kind: Literal["clarification", "evidence_insufficient"]
    text: str = Field(min_length=1)


class StateSnapshot(DurableDTO):
    revision: Literal["conversation-core-v1"] = "conversation-core-v1"
    source_turn_id: UUID
    previous_snapshot_id: UUID | None
    # No semantic projection: provenance alone is the minimal durable state.


class Acceptance(DurableDTO):
    id: UUID  # One immutable bundle identifies result, output snapshot and head.
    conversation_id: UUID
    turn_id: UUID
    run_id: UUID
    result: ProducedResult
    state: StateSnapshot
    created_at: datetime


class RunView(DurableDTO):
    id: UUID
    conversation_id: UUID
    turn_id: UUID
    retry_of: UUID | None
    key: str
    fingerprint: str
    expected_head: UUID | None
    owner: UUID
    fence: int
    deadline: datetime
    status: RunStatus
    created_at: datetime
    completed_at: datetime | None


class TurnView(DurableDTO):
    id: UUID
    conversation_id: UUID
    request: Admission
    created_at: datetime


class ConversationView(DurableDTO):
    id: UUID
    head: Acceptance | None
    active: RunView | None


class Readback(DurableDTO):
    conversation: ConversationView
    turn: TurnView
    run: RunView
    accepted: Acceptance | None
    unfinished: bool
    deadline_elapsed: bool


def fingerprint(body: Admission) -> str:
    return json_fingerprint(body.model_dump(mode="json"))


def transition(source: RunStatus, target: RunStatus) -> RunStatus:
    try:
        source, target = RunStatus(source), RunStatus(target)
    except ValueError:
        raise CoreConflict("illegal_transition") from None
    if source != RunStatus.ADMITTED or target == RunStatus.ADMITTED:
        raise CoreConflict("illegal_transition")
    return target


def require_head(actual: UUID | None, expected: UUID | None):
    if actual != expected:
        raise CoreConflict("head_conflict")


def require_fence(status, owner, fence, supplied_owner, supplied_fence, current_fence):
    if status != RunStatus.ADMITTED:
        raise CoreConflict("run_not_active")
    if owner != supplied_owner or fence != supplied_fence or fence != current_fence:
        raise CoreConflict("stale_owner")


def require_owner(status, owner, fence, supplied_owner, supplied_fence, current_fence, deadline, now):
    require_fence(status, owner, fence, supplied_owner, supplied_fence, current_fence)
    if deadline <= now:
        raise CoreConflict("deadline_elapsed")
