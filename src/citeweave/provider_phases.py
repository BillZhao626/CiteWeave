"""Durable external-call permission and outcome ledger.

DISPATCHED commits before I/O. A crash in the commit/send gap is conservatively
UNKNOWN. This prevents automatic duplicate paid calls, not physical exactly-once.
Only locally confirmed non-execution and HTTP rejection permit another attempt.
"""

import asyncio
import hashlib
import json
from contextlib import aclosing
from contextvars import ContextVar
from decimal import Decimal

from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import ProviderEventRow, ProviderPhaseRow, QueryRunRow
from citeweave.evaluation.lifecycle import lock, owned

evaluation_owner = ContextVar("evaluation_owner", default=None)


def guard(db, query_id, query_owner, query_fence, token, phase):
    now = lock(db)
    if token:
        owned(db, token, now)
    if phase == "answer":
        from citeweave.query_runtime import check_owned

        check_owned(db, query_id, query_owner, query_fence)
    return now


def prepare(query_id, query_owner, query_fence, phase, token=None):
    with transaction() as db:
        now = guard(db, query_id, query_owner, query_fence, token, phase)
        key = f"eval:{token.eval_id}:{token.case_id}:{phase}" if token else f"query:{query_id}:{phase}"
        rows = list(
            db.scalars(
                select(ProviderPhaseRow)
                .where(ProviderPhaseRow.logical_key == key)
                .order_by(ProviderPhaseRow.phase_attempt)
            )
        )
        if rows and rows[-1].state == "COMPLETED":
            return rows[-1]
        if rows and rows[-1].state in {"UNKNOWN", "DISPATCHED"}:
            raise ValueError("provider_outcome_unknown")
        owner, fence = (token.owner, token.fence) if token else (query_owner, query_fence)
        if rows and rows[-1].state == "PREPARED":
            row = rows[-1]
            row.owner, row.fence, row.query_run_id = owner, fence, query_id
            return row
        if len(rows) >= 2:
            raise ValueError("provider_attempts_exhausted")
        row = ProviderPhaseRow(
            eval_run_id=token.eval_id if token else None,
            case_id=token.case_id if token else None,
            query_run_id=query_id,
            logical_key=key,
            phase=phase,
            phase_attempt=len(rows) + 1,
            owner=owner,
            fence=fence,
            reserved_at=now,
            reserved_yuan=Decimal("0.10"),
        )
        db.add(row)
        db.flush()
        return row


def dispatch(identity, query_owner, query_fence, token=None):
    with transaction() as db:
        lock(db)
        row = db.get(ProviderPhaseRow, identity)
        now = guard(db, row.query_run_id, query_owner, query_fence, token, row.phase)
        owner, fence = (token.owner, token.fence) if token else (query_owner, query_fence)
        if row.state != "PREPARED" or row.owner != owner or row.fence != fence:
            raise ValueError("provider_phase_not_dispatchable")
        row.state, row.dispatched_at, row.outcome = "DISPATCHED", now, "unknown"


def complete(identity, query_owner, query_fence, token, parts=None, code=None, observed=None):
    with transaction() as db:
        lock(db)
        row = db.get(ProviderPhaseRow, identity)
        try:
            guard(db, row.query_run_id, query_owner, query_fence, token, row.phase)
            expected = (token.owner, token.fence) if token else (query_owner, query_fence)
            if (row.owner, row.fence) != expected or row.state != "DISPATCHED":
                raise ValueError("stale_phase")
        except (ValueError, TimeoutError):
            db.add(
                ProviderEventRow(
                    phase_id=identity,
                    kind="late_outcome_rejected",
                    detail={"result_received": parts is not None},
                )
            )
            return False
        if parts is not None:
            row.state, row.outcome, row.result = "COMPLETED", "known", parts
            row.result_hash = hashlib.sha256(
                json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            usage = next((p for p in reversed(parts) if "usage" in p), {})
            row.usage, row.request_id = usage.get("usage"), usage.get("provider_id")
            from citeweave.costs import estimated_cost

            row.estimated_yuan = estimated_cost(row.usage)
        else:
            usage = next((p for p in reversed(observed or []) if "usage" in p), {})
            row.usage, row.request_id = usage.get("usage"), usage.get("provider_id")
            if row.usage:
                from citeweave.costs import estimated_cost

                row.estimated_yuan = estimated_cost(
                    row.usage
                )  # visible lower-bound estimate, reservation retained
            safe = code in {
                "llm_connection_failed",
                "llm_key_missing",
                "circuit_open",
                "llm_http_429",
                "llm_http_400",
                "llm_http_401",
                "llm_http_403",
            }
            row.state, row.outcome, row.error_code = (
                ("REJECTED", "known_not_executed", code) if safe else ("UNKNOWN", "unknown", code)
            )
            if safe:
                row.estimated_yuan = Decimal(0)
        return True


class DurableProvider:
    """One wrapped stream == at most one HTTP send. Completed transport can replay."""

    def __init__(self, provider, query_id, query_owner=None, query_fence=None, phase="answer", token=None):
        self.provider, self.query_id = provider, query_id
        self.owner, self.fence, self.phase = query_owner, query_fence, phase
        self.token = token if token is not None else evaluation_owner.get()
        self.attempts = getattr(provider, "attempts", [])
        if hasattr(provider, "max_attempts"):
            provider.max_attempts = 1

    async def stream(self, messages):
        row = await asyncio.to_thread(prepare, self.query_id, self.owner, self.fence, self.phase, self.token)
        if row.state == "COMPLETED":
            for part in row.result:
                yield part
            return
        await asyncio.to_thread(dispatch, row.id, self.owner, self.fence, self.token)
        parts, size = [], 0
        try:
            async with aclosing(self.provider.stream(messages)) as stream:
                async for part in stream:
                    # Check cancellation/ownership between stream events as well as before send.
                    await asyncio.to_thread(self.check)
                    size += len(json.dumps(part, ensure_ascii=False))
                    if size > 131072 or len(parts) >= 8192:
                        raise ValueError("provider_output_limit")
                    parts.append(part)
                    yield part
            if not await asyncio.to_thread(complete, row.id, self.owner, self.fence, self.token, parts):
                raise ValueError("provider_result_owner_lost")
        except BaseException as exc:
            await asyncio.shield(
                asyncio.to_thread(
                    complete,
                    row.id,
                    self.owner,
                    self.fence,
                    self.token,
                    None,
                    getattr(exc, "code", type(exc).__name__),
                    parts,
                )
            )
            raise

    def check(self):
        with transaction() as db:
            guard(db, self.query_id, self.owner, self.fence, self.token, self.phase)


def reconcile_queries(db, now):
    """Standalone query expiry keeps reservations and records uncertain dispatch."""
    for row in db.scalars(
        select(ProviderPhaseRow)
        .join(QueryRunRow, ProviderPhaseRow.query_run_id == QueryRunRow.id)
        .where(
            ProviderPhaseRow.eval_run_id.is_(None),
            ProviderPhaseRow.state == "DISPATCHED",
            QueryRunRow.absolute_deadline <= now,
        )
    ):
        row.state, row.outcome = "UNKNOWN", "unknown"
