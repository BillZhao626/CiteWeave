"""PG-clock admission expiry and execution guards, compatible with legacy rows."""

from datetime import timedelta

from sqlalchemy import and_, func, or_, select

from citeweave.db import transaction
from citeweave.domain import QueryRunRow


def expire_queries(db, stamp):
    rows = db.scalars(
        select(QueryRunRow)
        .where(
            QueryRunRow.status == "RUNNING",
            or_(
                QueryRunRow.absolute_deadline <= stamp,
                and_(
                    QueryRunRow.absolute_deadline.is_(None),
                    QueryRunRow.created_at < stamp - timedelta(seconds=120),
                ),
            ),
        )
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        row.status, row.error_code = "FAILED", "api_interrupted"
        row.completed_at, row.error_category = stamp, "unknown_outcome"
        if row.fence is not None:
            row.fence += 1


def check_owned(db, run_id, owner, fence):
    row = db.scalar(select(QueryRunRow).where(QueryRunRow.id == run_id).with_for_update())
    stamp = db.scalar(select(func.clock_timestamp()))
    if not row or row.status != "RUNNING" or row.owner != owner or row.fence != fence:
        raise ValueError("run_no_longer_active")
    if row.absolute_deadline and row.absolute_deadline <= stamp:
        raise TimeoutError("query_deadline_exhausted")
    return row, stamp


def remaining(run_id, owner, fence):
    with transaction() as db:
        row, stamp = check_owned(db, run_id, owner, fence)
        return max(0, (row.absolute_deadline - stamp).total_seconds()) if row.absolute_deadline else 120
