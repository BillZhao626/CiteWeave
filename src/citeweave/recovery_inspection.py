"""Operator-only bounded read-only inspection of existing durable Run truth."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import case, select, text

from citeweave.conversation_contract import DurableDTO, RunStatus
from citeweave.operational_trace import OperationalTrace


class RecoveryItem(DurableDTO):
    conversation_id: UUID
    turn_id: UUID
    run_id: UUID
    status: RunStatus
    deadline_elapsed: bool
    attention: Literal[
        "RECONCILE_EXPIRED",
        "UNKNOWN_BLOCKED",
        "INTERRUPTED_NEW_AUTH_REQUIRED",
        "PERMANENT_FAILURE",
        "FAILED_REVIEW",
        "ACTIVE_WAIT",
        "NO_ACTION",
    ]
    reconcile_target: Literal["INTERRUPTED", "UNKNOWN", "FAILED"] | None
    operational: OperationalTrace


class RecoveryInspection(DurableDTO):
    observed_at: datetime
    limit: int
    has_more: bool
    items: tuple[RecoveryItem, ...]


def inspect_recovery(workspace, *, limit=32, include_terminal=False, run_id=None):
    from citeweave import conversation_provider as ledger
    from citeweave import conversations as core
    from citeweave.conversation_models import ConversationRow as Conversation
    from citeweave.conversation_models import ConversationRunRow as Run
    from citeweave.db import transaction
    from citeweave.operational_trace import diagnose, provider_diagnostics
    from citeweave.runtime_reliability import read_events

    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError("recovery_batch_limit_invalid")
    with transaction() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        now = core._clock(db)
        query = (
            select(Run)
            .join(Conversation, Run.conversation_id == Conversation.id)
            .where(Conversation.workspace_id == workspace)
        )
        if run_id is not None:
            query = query.where(Run.id == run_id)
        elif not include_terminal:
            query = query.where(
                (Run.status.in_(["UNKNOWN", "INTERRUPTED", "FAILED"]))
                | ((Run.status == "ADMITTED") & (Run.deadline <= now))
            )
        query = query.order_by(
            case(
                ((Run.status == "ADMITTED") & (Run.deadline <= now), 0), (Run.status == "UNKNOWN", 1), else_=2
            ),
            Run.created_at,
            Run.id,
        ).limit(limit + 1)
        rows = list(db.scalars(query))
        items = []
        for run in rows[:limit]:
            expired = run.status == "ADMITTED" and run.deadline <= now
            permanent = ledger.permanent_failure(db, run.id)
            blocked = ledger.blocks_retry(db, run.id)
            target = ("UNKNOWN" if blocked else "FAILED" if permanent else "INTERRUPTED") if expired else None
            attention = (
                "RECONCILE_EXPIRED"
                if expired
                else "UNKNOWN_BLOCKED"
                if run.status == "UNKNOWN"
                else "INTERRUPTED_NEW_AUTH_REQUIRED"
                if run.status == "INTERRUPTED"
                else "PERMANENT_FAILURE"
                if run.status == "FAILED" and permanent
                else "FAILED_REVIEW"
                if run.status == "FAILED"
                else "ACTIVE_WAIT"
                if run.status == "ADMITTED"
                else "NO_ACTION"
            )
            signals, truncated = read_events(db, run.id)
            items.append(
                RecoveryItem(
                    conversation_id=run.conversation_id,
                    turn_id=run.turn_id,
                    run_id=run.id,
                    status=run.status,
                    deadline_elapsed=expired,
                    attention=attention,
                    reconcile_target=target,
                    operational=diagnose(
                        run.status,
                        run.created_at,
                        run.completed_at,
                        signals,
                        truncated,
                        provider_diagnostics(db, run.id),
                    ),
                )
            )
        return RecoveryInspection(
            observed_at=now, limit=limit, has_more=len(rows) > limit, items=tuple(items)
        )
