"""Versioned allowlisted projections of durable conversation truth.

No history search, reconstruction, provider payload, or inferred interpretation.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from citeweave.conversation_contract import (
    Admission,
    DocumentaryResult,
    DurableDTO,
    Readback,
    RunStatus,
    Scope,
    SourceRef,
)
from citeweave.schemas import Citation


class ConversationScope(Scope):
    """Reuse core validation without renaming the existing v0.1 Scope schema."""


class TurnSubmit(DurableDTO):
    question: str = Field(min_length=1)
    scope: ConversationScope
    expected_head: UUID | None

    def admission(self) -> Admission:
        return Admission(**self.model_dump())


class PublicConversation(DurableDTO):
    revision: Literal["conversation-api-v1"] = "conversation-api-v1"
    id: UUID
    head_id: UUID | None
    active_turn_id: UUID | None
    active_run_id: UUID | None


class DocumentIdentity(DurableDTO):
    document_id: UUID
    document_version_id: UUID


class ClarificationResult(DurableDTO):
    kind: Literal["clarification"] = "clarification"
    text: str


class InsufficientResult(DurableDTO):
    kind: Literal["evidence_insufficient"] = "evidence_insufficient"
    text: str


class DocumentaryAnswer(DurableDTO):
    kind: Literal["documentary_answer"] = "documentary_answer"
    text: str
    citations: tuple[Citation, ...]
    documents: tuple[DocumentIdentity, ...]


class AcceptedResult(DurableDTO):
    revision: Literal["conversation-result-v1"] = "conversation-result-v1"
    acceptance_id: UUID
    conversation_id: UUID
    turn_id: UUID
    run_id: UUID
    created_at: datetime
    result: Annotated[
        ClarificationResult | InsufficientResult | DocumentaryAnswer, Field(discriminator="kind")
    ]


class PublicRun(DurableDTO):
    revision: Literal["conversation-api-v1"] = "conversation-api-v1"
    id: UUID
    conversation_id: UUID
    turn_id: UUID
    retry_of: UUID | None
    expected_head: UUID | None
    status: RunStatus
    created_at: datetime
    completed_at: datetime | None
    deadline_elapsed: bool
    accepted: AcceptedResult | None


class CitationIdentity(DurableDTO):
    label: str
    evidence_id: UUID
    document_version_id: UUID


class ConversationTrace(DurableDTO):
    revision: Literal["conversation-trace-v1"] = "conversation-trace-v1"
    conversation_id: UUID
    turn_id: UUID
    run_id: UUID
    retry_of: UUID | None
    input_head_id: UUID | None
    acceptance_id: UUID | None
    output_state_id: UUID | None
    original_question: str
    scope: ConversationScope
    persistence_profile: Literal["conversation-core-v1"] = "conversation-core-v1"
    status: RunStatus
    created_at: datetime
    completed_at: datetime | None
    metadata_availability: Literal["documentary_bundle", "control_bundle", "no_accepted_bundle"]
    interpretation_mode: Literal["USE_ORIGINAL", "USE_REWRITE"] | None = None
    interpretation_identity: str | None = None
    selected_query: str | None = None
    history_sources: tuple[SourceRef, ...] | None = None
    input_state_item_ids: tuple[UUID, ...] | None = None
    retrieval_profile: Literal["telecom-structural-v1"] | None = None
    documents: tuple[DocumentIdentity, ...] | None = None
    evidence_pack_identity: str | None = None
    evidence_ids: tuple[UUID, ...] | None = None
    citations: tuple[CitationIdentity, ...] | None = None
    validation: Literal["CURRENT_PACK_PHYSICAL_ONLY"] | None = None
    semantic_support: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"


class LifecycleEvent(DurableDTO):
    type: Literal["lifecycle"] = "lifecycle"
    run: PublicRun


class ResultEvent(DurableDTO):
    type: Literal["result"] = "result"
    accepted: AcceptedResult


class ConversationEvent(DurableDTO):
    revision: Literal["conversation-event-v1"] = "conversation-event-v1"
    event: Annotated[LifecycleEvent | ResultEvent, Field(discriminator="type")]


def conversation_view(view):
    return PublicConversation(
        id=view.id,
        head_id=view.head.id if view.head else None,
        active_turn_id=view.active.turn_id if view.active else None,
        active_run_id=view.active.id if view.active else None,
    )


def documents(result: DocumentaryResult):
    return tuple(
        DocumentIdentity(document_id=b.document_id, document_version_id=b.version_id)
        for b in result.snapshot.bindings
    )


def accepted_result(read: Readback) -> AcceptedResult | None:
    accepted = read.accepted
    # Core readback also resolves a later successful retry of the same Turn.
    # Never attach that result to the failed/old attempt being requested.
    if not accepted or accepted.run_id != read.run.id or read.run.status != RunStatus.ACCEPTED:
        return None
    result = accepted.result
    if result.kind == "documentary_answer":
        value = DocumentaryAnswer(
            text=result.text, citations=tuple(result.answer.citations), documents=documents(result)
        )
    elif result.kind == "clarification":
        value = ClarificationResult(text=result.text)
    else:
        value = InsufficientResult(text=result.text)
    return AcceptedResult(
        acceptance_id=accepted.id,
        conversation_id=accepted.conversation_id,
        turn_id=accepted.turn_id,
        run_id=accepted.run_id,
        created_at=accepted.created_at,
        result=value,
    )


def run_view(read: Readback) -> PublicRun:
    run = read.run
    return PublicRun(
        **{
            k: getattr(run, k)
            for k in (
                "id",
                "conversation_id",
                "turn_id",
                "retry_of",
                "expected_head",
                "status",
                "created_at",
                "completed_at",
            )
        },
        deadline_elapsed=read.deadline_elapsed,
        accepted=accepted_result(read),
    )


def trace_view(read: Readback) -> ConversationTrace:
    accepted = accepted_result(read)
    result = read.accepted.result if accepted else None
    fields = {}
    if isinstance(result, DocumentaryResult):
        trace = result.trace
        fields = dict(
            interpretation_mode=trace.interpretation_mode,
            interpretation_identity=trace.interpretation_identity,
            selected_query=trace.selected_query,
            history_sources=trace.history_sources,
            input_state_item_ids=trace.state_item_ids,
            retrieval_profile=trace.retrieval_profile,
            documents=documents(result),
            evidence_pack_identity=trace.evidence_identity,
            evidence_ids=tuple(s.evidence_id for s in result.evidence_pack.spans),
            citations=tuple(
                CitationIdentity(
                    label=c.label, evidence_id=c.evidence_id, document_version_id=c.document_version_id
                )
                for c in result.answer.citations
            ),
            validation=trace.validation,
        )
    return ConversationTrace(
        conversation_id=read.run.conversation_id,
        turn_id=read.run.turn_id,
        run_id=read.run.id,
        retry_of=read.run.retry_of,
        input_head_id=read.run.expected_head,
        acceptance_id=accepted.acceptance_id if accepted else None,
        output_state_id=accepted.acceptance_id if accepted else None,
        original_question=read.turn.request.question,
        scope=read.turn.request.scope,
        status=read.run.status,
        created_at=read.run.created_at,
        completed_at=read.run.completed_at,
        metadata_availability=(
            "documentary_bundle" if fields else "control_bundle" if accepted else "no_accepted_bundle"
        ),
        **fields,
    )
