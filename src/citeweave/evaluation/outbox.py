"""Bounded transport attempts, with generation/fence checked acknowledgements."""

from datetime import timedelta

from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, EvalOutboxRow, EvalRunRow
from citeweave.evaluation.lifecycle import RUN_TERMINAL, lock, sweep


def acquire():
    with transaction() as db:
        now = lock(db)
        for row in db.scalars(
            select(EvalOutboxRow)
            .where(EvalOutboxRow.state == "PENDING", EvalOutboxRow.next_send_at <= now)
            .order_by(EvalOutboxRow.created_at)
        ):
            if row.publish_lease and row.publish_lease > now:
                continue
            case = db.get(EvalCaseRow, (row.eval_run_id, row.case_id))
            run = db.get(EvalRunRow, row.eval_run_id)
            if (
                case.status != "QUEUED"
                or case.dispatch_generation != row.dispatch_generation
                or run.status in RUN_TERMINAL
            ):
                row.state = "OBSOLETE"
                continue
            if (
                any(
                    d and d <= now for d in (run.total_deadline, case.absolute_deadline, case.active_deadline)
                )
                or case.dispatch_count >= 30
                or case.dispatch_failures >= 10
            ):
                continue
            row.publish_fence += 1
            row.publish_lease = now + timedelta(seconds=10)
            row.send_count += 1
            case.dispatch_count += 1  # pre-send accounting also bounds send-success/ACK-loss
            return (row.eval_run_id, row.case_id, row.dispatch_generation, row.publish_fence)


def acknowledge(ticket, task_id=None, failed=False):
    with transaction() as db:
        now = lock(db)
        row = db.get(EvalOutboxRow, ticket[:3])
        case = db.get(EvalCaseRow, ticket[:2])
        if not row or row.publish_fence != ticket[3] or case.dispatch_generation != ticket[2]:
            return
        row.publish_lease = None
        if case.status != "QUEUED":
            row.state, row.task_id = "OBSOLETE", str(task_id) if task_id else None
            return
        if failed:
            case.dispatch_failures += 1
            row.next_send_at = now + timedelta(seconds=min(30, 2 ** min(5, case.dispatch_failures)))
        else:
            row.state, row.task_id = "SENT", str(task_id) if task_id else None
            case.dispatch_failures = 0


def dispatch(send):
    ticket = acquire()
    if not ticket:
        return
    try:
        result = send(str(ticket[0]), ticket[1], ticket[2])
    except Exception:
        acknowledge(ticket, failed=True)
        return
    acknowledge(ticket, getattr(result, "id", None))


def reconcile(send):
    sweep()
    dispatch(send)
