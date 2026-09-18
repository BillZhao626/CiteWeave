"""PostgreSQL serializes the two small upstream circuit states across API/worker processes."""

from dataclasses import asdict

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from citeweave.db import transaction
from citeweave.domain import CircuitRow
from citeweave.reliability import CircuitState
from citeweave.settings import settings


class Circuit:
    def __init__(self, name):
        if name not in {"deepseek", "model_gateway"}:
            raise ValueError("unknown_circuit")
        self.name = name

    def change(self, action, permit=None):
        with transaction() as db:
            db.execute(
                insert(CircuitRow)
                .values(name=self.name, value=asdict(CircuitState()))
                .on_conflict_do_nothing()
            )
            row = db.scalar(select(CircuitRow).where(CircuitRow.name == self.name).with_for_update())
            now = db.scalar(select(func.clock_timestamp())).timestamp()
            state = CircuitState(**row.value)
            result = None
            if action == "acquire":
                result = state.acquire(now, probe_seconds=settings().query_deadline_seconds + 5)
            elif action == "success":
                state.success(permit)
            elif action == "failure":
                state.failure(permit, now, settings().breaker_threshold, settings().breaker_cooldown_seconds)
            elif action == "abandon":
                state.abandon(permit, now, settings().breaker_cooldown_seconds)
            else:
                raise ValueError("unknown_circuit_action")
            row.value = asdict(state)
            return result
