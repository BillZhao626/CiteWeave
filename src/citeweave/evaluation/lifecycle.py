"""PG-clock state machine. All evaluation mutations take the same transaction lock.

Lock order is admission, evaluation, query, phase. Broker and provider I/O never
run inside these transactions. Terminal cases are immutable business outcomes.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select, text

from citeweave.db import transaction
from citeweave.domain import (
    EvalCaseRow,
    EvalOutboxRow,
    EvalRunRow,
    IngestionJobRow,
    ProviderPhaseRow,
    QueryRunRow,
)
from citeweave.lifecycle import LIVE
from citeweave.settings import settings

TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED", "OUTCOME_UNKNOWN"})
RUN_TERMINAL = frozenset({"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "CANCELLED"})
POLICY = "eval-durable-v1"


def lock(db):
    db.execute(text("SELECT pg_advisory_xact_lock(17702201)"))
    db.execute(text("SELECT pg_advisory_xact_lock(17702203)"))
    return db.scalar(select(func.clock_timestamp()))


@dataclass(frozen=True)
class Ownership:
    eval_id: UUID
    case_id: str
    owner: UUID
    fence: int


def owned(db, token, now=None):
    now = now or lock(db)
    run = db.get(EvalRunRow, token.eval_id)
    case = db.get(EvalCaseRow, (token.eval_id, token.case_id))
    if (
        not case
        or not run
        or case.status != "RUNNING"
        or run.status in RUN_TERMINAL
        or run.cancel_requested_at
        or case.cancel_requested_at
        or case.owner != token.owner
        or case.fence != token.fence
        or not case.lease_until
        or case.lease_until <= now
    ):
        raise ValueError("evaluation_lease_lost")
    if any(d and d <= now for d in (run.total_deadline, case.absolute_deadline, case.active_deadline)):
        raise ValueError("evaluation_deadline_exhausted")
    return case, run, now


def phases(db, case):
    return list(
        db.scalars(
            select(ProviderPhaseRow)
            .where(ProviderPhaseRow.eval_run_id == case.eval_run_id, ProviderPhaseRow.case_id == case.case_id)
            .order_by(ProviderPhaseRow.created_at, ProviderPhaseRow.phase_attempt)
        )
    )


def uncertain(db, case):
    found = False
    for p in phases(db, case):
        if p.state in {"DISPATCHED", "UNKNOWN"}:
            p.state, p.outcome = "UNKNOWN", "unknown"
            found = True
    return found


def terminal(db, case, status, now, code=None):
    if case.status in TERMINAL:
        return
    unknown = uncertain(db, case)
    case.status = "OUTCOME_UNKNOWN" if unknown and status != "CANCELLED" else status
    case.completed_at, case.last_error_code = now, code
    case.last_error_category = "unknown_outcome" if unknown else "terminal"
    case.fence += 1
    case.owner, case.lease_until = None, None
    if case.query_run_id:
        query = db.get(QueryRunRow, case.query_run_id)
        if query and query.status == "RUNNING":
            query.status, query.error_code, query.completed_at = "FAILED", code or status.lower(), now
            query.fence = (query.fence or 0) + 1


def summarize(db, run, now):
    db.flush()
    cases = list(db.scalars(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == run.id)))
    counts = Counter(c.status for c in cases)
    done = sum(counts[s] for s in TERMINAL)
    run.completeness = dict(total=len(cases), terminal=done, missing=len(cases) - done, states=dict(counts))
    run.summary = dict(run.summary or {}, lifecycle=run.completeness)
    if done == len(cases) and run.status not in RUN_TERMINAL:
        run.status = (
            "CANCELLED"
            if run.cancel_requested_at
            else "FAILED"
            if run.total_deadline and now >= run.total_deadline
            else "COMPLETED"
            if counts["COMPLETED"] == len(cases)
            else "COMPLETED_WITH_ERRORS"
        )
        run.completed_at = now


def defer(case, now, code, admission=False):
    if admission:
        case.admission_deferrals += 1
    case.status, case.owner, case.lease_until = "RETRY_WAIT", None, None
    case.fence += 1
    case.last_error_code, case.last_error_category = code, "admission" if admission else "retryable"
    delay = min(30, 5 * 2 ** min(3, case.admission_deferrals if admission else case.execution_attempt))
    case.next_attempt_at = now + timedelta(seconds=delay)


def occupied_query_slots(db, exclude=None):
    count = db.scalar(select(func.count()).select_from(QueryRunRow).where(QueryRunRow.status == "RUNNING"))
    reserved = (
        select(func.count())
        .select_from(EvalCaseRow)
        .where(EvalCaseRow.status == "RUNNING", EvalCaseRow.query_run_id.is_(None))
    )
    if exclude:
        from sqlalchemy import or_

        reserved = reserved.where(
            or_(EvalCaseRow.eval_run_id != exclude.eval_id, EvalCaseRow.case_id != exclude.case_id)
        )
    return count + db.scalar(reserved)


def sweep():
    """Expire every live case before considering a single new dispatch."""
    with transaction() as db:
        now = lock(db)
        runs = list(
            db.scalars(
                select(EvalRunRow).where(
                    EvalRunRow.runtime_policy == POLICY, EvalRunRow.status.not_in(RUN_TERMINAL)
                )
            )
        )
        for run in runs:
            for case in db.scalars(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == run.id)):
                if case.status in TERMINAL:
                    continue
                if run.cancel_requested_at or case.cancel_requested_at:
                    terminal(db, case, "CANCELLED", now, "cancelled")
                elif any(d and d <= now for d in (run.total_deadline, case.absolute_deadline)):
                    terminal(db, case, "FAILED", now, "absolute_deadline_exhausted")
                elif case.active_deadline and case.active_deadline <= now:
                    terminal(db, case, "FAILED", now, "active_deadline_exhausted")
                elif case.status == "RUNNING" and (not case.lease_until or case.lease_until <= now):
                    if uncertain(db, case):
                        terminal(db, case, "OUTCOME_UNKNOWN", now, "owner_lost_after_dispatch")
                    elif case.execution_attempt >= case.max_attempts:
                        terminal(db, case, "FAILED", now, "execution_attempts_exhausted")
                    else:
                        if case.query_run_id:
                            q = db.get(QueryRunRow, case.query_run_id)
                            if q and q.status == "RUNNING":
                                q.status, q.error_code, q.completed_at = (
                                    "FAILED",
                                    "owner_lost_before_dispatch",
                                    now,
                                )
                                q.fence = (q.fence or 0) + 1
                        defer(case, now, "owner_lost_before_dispatch")
                elif case.status != "RUNNING" and (case.dispatch_count >= 30 or case.dispatch_failures >= 10):
                    delivery = db.get(
                        EvalOutboxRow, (case.eval_run_id, case.case_id, case.dispatch_generation)
                    )
                    last_delivery_live = (
                        case.status == "QUEUED"
                        and delivery
                        and delivery.state == "SENT"
                        and case.lease_until
                        and case.lease_until > now
                    )
                    if not last_delivery_live:
                        terminal(db, case, "FAILED", now, "dispatch_exhausted")
                elif case.admission_deferrals >= case.max_admission_deferrals:
                    terminal(db, case, "FAILED", now, "capacity_exhausted")
                elif case.status == "QUEUED" and case.lease_until and case.lease_until <= now:
                    defer(case, now, "delivery_expired")
            summarize(db, run, now)
        db.flush()
        if db.scalar(select(IngestionJobRow.id).where(IngestionJobRow.status.in_(LIVE)).limit(1)):
            return
        if db.scalar(
            select(EvalCaseRow.case_id).where(EvalCaseRow.status.in_(["QUEUED", "RUNNING"])).limit(1)
        ):
            return
        for run in runs:
            if run.status in RUN_TERMINAL:
                continue
            for case in db.scalars(
                select(EvalCaseRow)
                .where(EvalCaseRow.eval_run_id == run.id, EvalCaseRow.status.in_(["PENDING", "RETRY_WAIT"]))
                .order_by(EvalCaseRow.case_id)
            ):
                if case.next_attempt_at and case.next_attempt_at > now:
                    continue
                if case.execution_attempt >= case.max_attempts:
                    terminal(db, case, "FAILED", now, "execution_attempts_exhausted")
                    continue
                case.active_deadline = case.active_deadline or min(
                    run.total_deadline, now + timedelta(seconds=600)
                )
                case.dispatch_generation += 1
                case.status, case.lease_until = "QUEUED", now + timedelta(seconds=60)
                db.add(
                    EvalOutboxRow(
                        eval_run_id=run.id,
                        case_id=case.case_id,
                        dispatch_generation=case.dispatch_generation,
                        next_send_at=now,
                    )
                )
                return


def claim(eval_id, case_id, generation):
    with transaction() as db:
        now = lock(db)
        run, case = db.get(EvalRunRow, eval_id), db.get(EvalCaseRow, (eval_id, case_id))
        if not case or not run or case.status != "QUEUED" or case.dispatch_generation != generation:
            return None
        if run.status in RUN_TERMINAL or run.cancel_requested_at:
            terminal(db, case, "CANCELLED", now, "cancelled")
            return None
        if any(d and d <= now for d in (run.total_deadline, case.absolute_deadline, case.active_deadline)):
            terminal(db, case, "FAILED", now, "deadline_exhausted")
            return None
        if case.execution_attempt >= case.max_attempts:
            terminal(db, case, "FAILED", now, "execution_attempts_exhausted")
            return None
        from citeweave.query_runtime import expire_queries

        expire_queries(db, now)
        count = db.scalar(
            select(func.count()).select_from(QueryRunRow).where(QueryRunRow.status == "RUNNING")
        )
        reserved = db.scalar(
            select(func.count())
            .select_from(EvalCaseRow)
            .where(EvalCaseRow.status == "RUNNING", EvalCaseRow.query_run_id.is_(None))
        )
        if count + reserved >= settings().max_active_queries or db.scalar(
            select(IngestionJobRow.id).where(IngestionJobRow.status.in_(LIVE)).limit(1)
        ):
            defer(case, now, "capacity_unavailable", admission=True)
            return None
        case.execution_attempt += 1
        case.owner, case.fence, case.status = uuid4(), case.fence + 1, "RUNNING"
        case.started_at = case.started_at or now
        case.lease_until = min(case.active_deadline, now + timedelta(seconds=30))
        run.status = "RUNNING"
        return Ownership(eval_id, case_id, case.owner, case.fence)


def heartbeat(token):
    with transaction() as db:
        case, _, now = owned(db, token)
        case.lease_until = min(case.active_deadline, now + timedelta(seconds=30))


def save(token, **values):
    with transaction() as db:
        case, run, now = owned(db, token)
        for key, value in values.items():
            setattr(case, key, value)
        if case.status in TERMINAL:
            case.completed_at, case.owner, case.lease_until = now, None, None
            case.fence += 1
        summarize(db, run, now)


def fail(token, code="execution_failed"):
    with transaction() as db:
        try:
            case, run, now = owned(db, token)
        except ValueError:
            return  # sweeper owns expired/cancelled work
        entries = phases(db, case)
        if uncertain(db, case):
            terminal(db, case, "OUTCOME_UNKNOWN", now, code)
        elif (
            entries
            and entries[-1].state == "REJECTED"
            and entries[-1].phase_attempt < 2
            and case.execution_attempt < case.max_attempts
        ):
            if case.query_run_id:
                query = db.get(QueryRunRow, case.query_run_id)
                if query and query.status == "RUNNING":
                    query.status, query.error_code, query.completed_at = "FAILED", code, now
                    query.fence = (query.fence or 0) + 1
            defer(case, now, code)
        else:
            terminal(db, case, "FAILED", now, code)
        summarize(db, run, now)


def cancel(workspace, eval_id):
    from fastapi import HTTPException

    with transaction() as db:
        now = lock(db)
        run = db.get(EvalRunRow, eval_id)
        if not run or run.workspace_id != workspace:
            raise HTTPException(404, "evaluation_not_found")
        if run.status in RUN_TERMINAL:
            return run
        run.cancel_requested_at = now
        for case in db.scalars(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == eval_id)):
            if case.status not in TERMINAL:
                case.cancel_requested_at = now
                terminal(db, case, "CANCELLED", now, "cancelled")
        summarize(db, run, now)
        return run
