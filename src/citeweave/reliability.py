"""Small, explicit reliability primitives; no decorators hiding execution semantics."""

import threading
import time
from collections import deque
from dataclasses import dataclass


def error_category(code: str) -> str:
    if code in {"client_cancelled", "stream_interrupted"}:
        return "cancelled"
    if code in {
        "llm_timeout",
        "llm_stream_incomplete",
        "llm_protocol_error",
        "api_interrupted",
        "query_timeout",
    }:
        return "unknown_outcome"
    if code in {
        "llm_connection_failed",
        "model_connection_failed",
        "model_timeout",
        "circuit_open",
        "model_busy",
        "model_queue_timeout",
        "database_unavailable",
        "index_unavailable",
    }:
        return "retryable"
    if code.startswith(("llm_http_", "model_http_")):
        return (
            "retryable" if code.rsplit("_", 1)[-1] in {"429", "500", "502", "503", "504"} else "non_retryable"
        )
    return "non_retryable"


class CircuitOpen(RuntimeError):
    code = "circuit_open"


@dataclass
class CircuitState:
    state: str = "closed"
    failures: int = 0
    until: float = 0
    generation: int = 0

    def acquire(self, now: float, probe_seconds: float = 45) -> int:
        if self.state != "closed":
            if now < self.until:
                raise CircuitOpen("circuit_open")
            # Also recovers a probe whose process died. Older permits cannot close the new generation.
            self.state, self.until = "half_open", now + probe_seconds
            self.generation += 1
        return self.generation

    def success(self, permit: int):
        if permit == self.generation:
            self.state, self.failures, self.until = "closed", 0, 0

    def failure(self, permit: int, now: float, threshold: int = 3, cooldown: float = 20):
        if permit != self.generation:
            return
        self.failures += 1
        if self.state == "half_open" or self.failures >= threshold:
            self.state, self.until = "open", now + cooldown
            self.generation += 1

    def abandon(self, permit: int, now: float, cooldown: float = 20):
        if permit == self.generation and self.state == "half_open":
            self.state, self.until = "open", now + cooldown
            self.generation += 1


class ModelCapacityError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class FairGate:
    """FIFO by arrival; bounded queue and deadline. One inference owns the GPU at a time."""

    def __init__(self, max_waiters=4):
        self.condition = threading.Condition()
        self.waiters = deque()
        self.busy = False
        self.max_waiters = max_waiters
        self.accepted = self.rejected = self.timed_out = 0

    def acquire(self, timeout=10):
        deadline, ticket = time.monotonic() + timeout, object()
        with self.condition:
            if (self.busy or self.waiters) and len(self.waiters) >= self.max_waiters:
                self.rejected += 1
                raise ModelCapacityError("model_busy")
            self.waiters.append(ticket)
            while self.busy or self.waiters[0] is not ticket:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.waiters.remove(ticket)
                    self.timed_out += 1
                    self.condition.notify_all()
                    raise ModelCapacityError("model_queue_timeout")
                self.condition.wait(remaining)
            self.waiters.popleft()
            self.busy = True
            self.accepted += 1

    def release(self):
        with self.condition:
            if not self.busy:
                raise RuntimeError("gate_not_acquired")
            self.busy = False
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return dict(
                concurrency=1,
                active=int(self.busy),
                queued=len(self.waiters),
                max_waiters=self.max_waiters,
                accepted=self.accepted,
                rejected=self.rejected,
                timed_out=self.timed_out,
            )
