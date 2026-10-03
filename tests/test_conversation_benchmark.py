"""Measurement integrity risks; no real DB, network or provider."""

import asyncio

import httpx
import pytest

from benchmarks.conversation import operation, summarize, workload


def sample(identity):
    return dict(identity=identity, conversation="synthetic", body={"expected_head": None})


def test_every_failed_attempt_is_recorded_in_all_latency_and_throughput():
    async def run():
        async def respond(request):
            if request.headers["idempotency-key"] == "slow":
                await asyncio.sleep(1)
            return httpx.Response(503, json={"error": {"code": "synthetic"}})

        async with httpx.AsyncClient(
            base_url="http://synthetic", transport=httpx.MockTransport(respond)
        ) as client:
            return await workload(client, [sample("slow"), sample("failed"), sample("failed2")], 2, 0.02)

    rows, wall = asyncio.run(run())
    assert len(rows) == 3 and {r["identity"] for r in rows} == {"slow", "failed", "failed2"}
    assert {r["status"] for r in rows} == {"failure", "timeout"}
    result = summarize(rows, wall)
    assert result["attempted"] == result["failed"] == 3 and result["timeouts"] == 1
    assert result["latency_ms"]["n"] == 3 and result["latency_ms"]["p95"] >= 20
    assert result["throughput_rps"] == 0 and result["success_rate"] == 0
    assert result["latency_ms"]["p99"] is None


def test_malformed_success_is_failure_and_retains_termination_latency():
    async def run():
        def response(request):
            if request.method == "POST":
                return httpx.Response(200, json={"id": "bad", "status": "ACCEPTED"})
            return httpx.Response(200, json={"raw": "malformed"})

        async with httpx.AsyncClient(
            base_url="http://synthetic", transport=httpx.MockTransport(response)
        ) as client:
            return await operation(client, sample("malformed"), 1)

    row = asyncio.run(run())
    assert row["status"] == "failure" and row["error"] == "KeyError"
    assert row["latency_ms"] >= 0 and "post_ms" in row


def test_duplicate_records_or_invalid_timing_cannot_be_reported():
    rows = [dict(identity="same", status="failure", latency_ms=2, enqueue_to_finish_ms=4)]
    with pytest.raises(ValueError, match="duplicate_outcome"):
        summarize(rows * 2, 1)
    with pytest.raises(ValueError, match="invalid_timing"):
        summarize([dict(rows[0], latency_ms=float("nan"))], 1)


def test_summary_uses_nearest_rank_and_includes_failure_tail():
    rows = [
        dict(
            identity=str(i),
            status="success" if i < 19 else "timeout",
            latency_ms=i + 1,
            post_ms=i + 1,
            enqueue_to_finish_ms=i + 1,
        )
        for i in range(20)
    ]
    result = summarize(rows, 2)
    assert result["latency_ms"]["p50"] == 10 and result["latency_ms"]["p95"] == 19
    assert result["latency_ms"]["max"] == 20 and result["success_latency_ms"]["max"] == 19
    assert result["throughput_rps"] == 9.5 and result["success_rate"] == 0.95
