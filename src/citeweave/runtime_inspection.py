"""Read-only, scope-checked projections of existing Conversation publication truth."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import select

from citeweave import conversations as core
from citeweave.conversation_contract import DurableDTO, Readback, RunStatus, WorkingState
from citeweave.conversation_models import ConversationRow, ConversationRunRow
from citeweave.conversation_public import (
    ConversationTrace,
    PublicRun,
    accepted_result,
    run_view,
    trace_view,
)
from citeweave.db import transaction


class PublishedStateSummary(DurableDTO):
    snapshot_id: UUID
    revision: Literal["conversation-core-v1", "conversation-state-v2"]
    source_turn_id: UUID
    previous_snapshot_id: UUID | None
    topic_signal: str | None
    active_entries: int | None
    retired_entries: int | None


class PublicationObservation(DurableDTO):
    decision: Literal["PUBLISHED", "NOT_PUBLISHED"]
    acceptance_id: UUID | None
    recorded_at: datetime | None
    working_state: PublishedStateSummary | None
    conversation_head_id: UUID | None
    head_relation: Literal["CURRENT", "ADVANCED", "NO_ACCEPTANCE"]


class ConversationRunInspection(DurableDTO):
    revision: Literal["conversation-inspection-v1"] = "conversation-inspection-v1"
    run: PublicRun
    publication: PublicationObservation
    trace: ConversationTrace


class ConversationRunSummary(DurableDTO):
    run_id: UUID
    conversation_id: UUID
    turn_id: UUID
    question: str
    status: RunStatus
    created_at: datetime
    completed_at: datetime | None
    acceptance_id: UUID | None
    publication: Literal["PUBLISHED", "NOT_PUBLISHED"]
    retry_decision: Literal[
        "BLOCKED_UNKNOWN",
        "TERMINAL_NO_DISPATCH",
        "EXPLICIT_NEW_AUTHORIZATION_REQUIRED",
        "POLICY_AND_KNOWN_PROOF_REQUIRED",
    ]
    unknown_reason: (
        Literal[
            "PROVIDER_UNCERTAIN",
            "KNOWN_RESULT_NOT_ACCEPTED",
            "CANCELLED_WITH_UNRESOLVED_PROVIDER",
            "LEGACY_REASON_UNAVAILABLE",
        ]
        | None
    )
    reason_code: str | None


def inspection_view(read: Readback) -> ConversationRunInspection:
    accepted = accepted_result(read)
    head_id = read.conversation.head.id if read.conversation.head else None
    state = read.accepted.state if accepted else None
    summary = None
    if state:
        working = isinstance(state, WorkingState)
        summary = PublishedStateSummary(
            snapshot_id=accepted.acceptance_id,
            revision=state.revision,
            source_turn_id=state.source_turn_id,
            previous_snapshot_id=state.previous_snapshot_id,
            topic_signal=state.delta.signals.topic if working else None,
            active_entries=sum(e.active for e in state.entries) if working else None,
            retired_entries=sum(not e.active for e in state.entries) if working else None,
        )
    return ConversationRunInspection(
        run=run_view(read),
        trace=trace_view(read),
        publication=PublicationObservation(
            decision="PUBLISHED" if accepted else "NOT_PUBLISHED",
            acceptance_id=accepted.acceptance_id if accepted else None,
            recorded_at=accepted.created_at if accepted else None,
            working_state=summary,
            conversation_head_id=head_id,
            head_relation="CURRENT"
            if accepted and head_id == accepted.acceptance_id
            else "ADVANCED"
            if accepted
            else "NO_ACCEPTANCE",
        ),
    )


def list_runs(workspace: UUID, limit: int, offset: int) -> tuple[ConversationRunSummary, ...]:
    # The catalog is bounded, newest first. Each row then uses the existing core
    # reader's workspace and fixed-version checks; unavailable scope fails closed.
    # Each inspection is coherent under its Conversation lock. This list is not
    # a cross-conversation transactional snapshot or dispatch authority.
    with transaction() as db:
        identities = db.execute(
            select(ConversationRunRow.conversation_id, ConversationRunRow.id)
            .join(ConversationRow, ConversationRow.id == ConversationRunRow.conversation_id)
            .where(ConversationRow.workspace_id == workspace)
            .order_by(ConversationRunRow.created_at.desc(), ConversationRunRow.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    summaries = []
    for conversation_id, run_id in identities:
        value = inspection_view(core.read_run_id(workspace, conversation_id, run_id))
        op = value.trace.operational
        assert op is not None  # The core reader always diagnoses durable events.
        summaries.append(
            ConversationRunSummary(
                run_id=value.run.id,
                conversation_id=value.run.conversation_id,
                turn_id=value.run.turn_id,
                question=value.trace.original_question,
                status=value.run.status,
                created_at=value.run.created_at,
                completed_at=value.run.completed_at,
                acceptance_id=value.publication.acceptance_id,
                publication=value.publication.decision,
                retry_decision=op.retry_decision,
                unknown_reason=op.unknown_reason,
                reason_code=next((e.error_code for e in reversed(op.timeline) if e.error_code), None),
            )
        )
    return tuple(summaries)


def mount(app, principal):
    @app.get("/v1/runtime/conversation-runs", response_model=tuple[ConversationRunSummary, ...])
    def runs(workspace=Depends(principal), limit: int = Query(25, ge=1, le=25), offset: int = Query(0, ge=0)):
        return list_runs(workspace, limit, offset)

    @app.get(
        "/v1/conversations/{conversation_id}/runs/{run_id}/inspection",
        response_model=ConversationRunInspection,
    )
    def inspection(conversation_id: UUID, run_id: UUID, workspace=Depends(principal)):
        return inspection_view(core.read_run_id(workspace, conversation_id, run_id))
