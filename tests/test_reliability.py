import threading
import time

import pytest

from citeweave.reliability import CircuitOpen, CircuitState, FairGate, ModelCapacityError, error_category


def test_breaker_recovery_single_probe_and_stale_success():
    state = CircuitState()
    old = state.acquire(0)
    for _ in range(3):
        state.failure(old, 1)
    assert state.state == "open"
    state.success(old)
    assert state.state == "open"
    with pytest.raises(CircuitOpen):
        state.acquire(2)
    probe = state.acquire(22)
    assert state.state == "half_open"
    with pytest.raises(CircuitOpen):
        state.acquire(23)
    state.success(probe)
    assert state.state == "closed" and state.failures == 0


def test_dead_probe_and_cancelled_probe_recover_without_false_success():
    state = CircuitState("open", 3, 1, 4)
    first = state.acquire(2, probe_seconds=5)
    second = state.acquire(8)
    state.success(first)
    assert state.state == "half_open"
    state.abandon(second, 9)
    assert state.state == "open"
    state.failure(state.acquire(30), 31)
    assert state.state == "open"


def test_fifo_gate_bounds_deadline_and_exclusive_execution():
    gate = FairGate(max_waiters=2)
    order = []
    gate.acquire()

    def job(number):
        gate.acquire(timeout=2)
        order.append(number)
        gate.release()

    workers = []
    for number in range(2):
        worker = threading.Thread(target=job, args=(number,))
        worker.start()
        workers.append(worker)
        deadline = time.monotonic() + 1
        while gate.snapshot()["queued"] != number + 1 and time.monotonic() < deadline:
            time.sleep(0.001)
        assert gate.snapshot()["queued"] == number + 1
    with pytest.raises(ModelCapacityError, match="model_busy"):
        gate.acquire(0.01)
    gate.release()
    for worker in workers:
        worker.join(3)
        assert not worker.is_alive()
    assert order == [0, 1]
    gate.acquire()
    with pytest.raises(ModelCapacityError, match="model_queue_timeout"):
        gate.acquire(0.01)
    gate.release()
    assert gate.snapshot()["active"] == gate.snapshot()["queued"] == 0


@pytest.mark.parametrize(
    "code,category",
    [
        ("llm_http_429", "retryable"),
        ("llm_http_503", "retryable"),
        ("llm_http_401", "non_retryable"),
        ("invalid_or_missing_citation", "non_retryable"),
        ("llm_stream_incomplete", "unknown_outcome"),
        ("client_cancelled", "cancelled"),
    ],
)
def test_error_taxonomy(code, category):
    assert error_category(code) == category
