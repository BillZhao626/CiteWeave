"""Internal persistence contract, not a conversational API or execution profile."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from citeweave.catalog import fingerprint as json_fingerprint
from citeweave.query_evidence import EvidencePack, StructuralSnapshot
from citeweave.schemas import Answer

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
    # Legacy control payload only; documentary results use the separate typed
    # bundle below and must pass the EvidencePack/Citation acceptance boundary.
    kind: Literal["clarification", "evidence_insufficient"]
    text: str = Field(min_length=1)


class StateSnapshot(DurableDTO):
    revision: Literal["conversation-core-v1"] = "conversation-core-v1"
    source_turn_id: UUID
    previous_snapshot_id: UUID | None
    # No semantic projection: provenance alone is the minimal durable state.


class SourceRef(DurableDTO):
    acceptance_id: UUID
    turn_id: UUID


class DocumentaryTrace(DurableDTO):
    original_question: str
    proposed_rewrite: str | None
    selected_query: str
    interpretation_mode: Literal["USE_ORIGINAL", "USE_REWRITE"]
    interpretation_identity: str
    history_sources: tuple[SourceRef, ...]
    state_item_ids: tuple[UUID, ...]
    scope: Scope
    retrieval_profile: Literal["telecom-structural-v1"] = "telecom-structural-v1"
    evidence_identity: str
    validation: Literal["CURRENT_PACK_PHYSICAL_ONLY"] = "CURRENT_PACK_PHYSICAL_ONLY"


class DocumentaryResult(DurableDTO):
    """Internal JSON bundle; existing control payloads remain readable unchanged."""

    revision: Literal["conversation-documentary-v1"] = "conversation-documentary-v1"
    kind: Literal["documentary_answer", "evidence_insufficient"]
    text: str = Field(min_length=1, max_length=8192)
    answer: Answer
    snapshot: StructuralSnapshot
    evidence_pack: EvidencePack
    trace: DocumentaryTrace


class ResolvedSignals(DurableDTO):
    topic: str | None = None
    task: str | None = None
    entities: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


class StateValue(DurableDTO):
    id: UUID
    kind: Literal["topic", "entity", "constraint", "ambiguity"]
    key: str = Field(min_length=1)
    value: str = Field(min_length=1)
    replaces: tuple[UUID, ...] = ()


class HistoryRelation(DurableDTO):
    target: SourceRef
    kind: Literal["correction", "dependency"]
    # Empty means the whole source; otherwise correct only these state entries.
    state_item_ids: tuple[UUID, ...] = ()


class ResolvedConversationDelta(DurableDTO):
    """Already resolved intent only. Never interpret text or assert evidence truth."""

    source_turn_id: UUID
    previous_snapshot_id: UUID | None
    signals: ResolvedSignals = Field(default_factory=ResolvedSignals)
    put: tuple[StateValue, ...] = ()
    deactivate: tuple[UUID, ...] = ()
    relations: tuple[HistoryRelation, ...] = ()
    # Optional for legacy v2 bundles. Distinguishes retiring context on a shift
    # from an explicit user correction when an old topic is later revalidated.
    topic_relation: Literal["continue", "shift", "return"] | None = None


class StateEntry(DurableDTO):
    item: StateValue
    introduced_by: SourceRef
    scope: Scope
    active: bool = True
    changed_by: SourceRef | None = None
    change: Literal["superseded", "deactivated", "scope_narrowed"] | None = None


class WorkingState(DurableDTO):
    revision: Literal["conversation-state-v2"] = "conversation-state-v2"
    authority: Literal["contextual_intent_not_evidence"] = "contextual_intent_not_evidence"
    source_turn_id: UUID
    previous_snapshot_id: UUID | None
    source: SourceRef
    scope: Scope
    entries: tuple[StateEntry, ...] = ()
    delta: ResolvedConversationDelta


class Acceptance(DurableDTO):
    id: UUID  # One immutable bundle identifies result, output snapshot and head.
    conversation_id: UUID
    turn_id: UUID
    run_id: UUID
    result: ProducedResult | DocumentaryResult
    state: Annotated[StateSnapshot | WorkingState, Field(discriminator="revision")]
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
    reliability_events: tuple[dict, ...] = ()
    reliability_truncated: bool = False
    operational: dict | None = None


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
