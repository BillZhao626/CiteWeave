import asyncio
import json

import pytest
from fastapi import HTTPException

from benchmarks.concurrent import run_workload
from benchmarks.manifest import ENVIRONMENT_KEYS, create, validate
from benchmarks.report import percentiles, summarize, write_report


def row(identity, status, arrival, finish, warmup=False):
    return dict(
        request_id=identity,
        status=status,
        arrival=arrival,
        finish=finish,
        warmup=warmup,
        admission=arrival if status == "success" else None,
        estimated_yuan=None,
    )


def test_nearest_rank_tail_missing_failures_and_wall_clock_throughput():
    rows = [
        row("late", "timeout", 0, 10),
        row("fast", "success", 0, 1),
        row("429", "429", 0.5, 0.6),
        row("warm", "success", -5, -1, True),
    ]
    result = summarize(rows)
    assert result["sample_count"] == 3 and result["warmup_count"] == 1
    assert result["success_rps"] == 0.1 and result["wall_seconds"] == 10
    assert result["all_termination_latency_ms"]["p95"] == 10000
    assert result["success_latency_ms"]["p95"] == 1000
    assert result["all_termination_latency_ms"]["p99"] is None
    assert percentiles(range(1, 41))["p95"] == 38
    assert percentiles(range(1, 1001))["p99"] == 990


def test_manifest_fails_closed_and_raw_summary_is_reproducible(tmp_path):
    environment = {k: {"fixture": True} for k in ENVIRONMENT_KEYS}
    environment["limits"] = {"request_deadline_seconds": 0.05}
    manifest = create(environment, concurrency=2, requests=4)
    with pytest.raises(ValueError):
        create({}, requests=4)
    with pytest.raises(ValueError):
        create(environment, provider="real")
    dirty = json.loads(json.dumps(manifest))
    dirty["source"]["dirty"] = True
    with pytest.raises(ValueError):
        validate(dirty, final=True)

    async def operation(question, item):
        if question == "timeout":
            await asyncio.sleep(0.2)
        if question == "429":
            raise HTTPException(429, "fixture_capacity")
        if question == "cancel":
            raise asyncio.CancelledError()
        item["status"] = "success"

    output = tmp_path / "original-smoke"
    result = asyncio.run(run_workload(operation, ["timeout", "429", "cancel", "success"], manifest, output))
    assert result["sample_count"] == 4 and result["status_counts"] == {
        "429": 1,
        "cancelled": 1,
        "success": 1,
        "timeout": 1,
    }
    before = (output / "summary.json").read_bytes()
    assert write_report(output) == result
    assert (output / "summary.json").read_bytes() == before
