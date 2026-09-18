"""Pure raw-to-summary transformation; failed rows are never discarded."""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def percentiles(values):
    ordered = sorted(values)

    def percentile(p):
        return ordered[max(0, math.ceil(p * len(ordered)) - 1)] if ordered else None

    return dict(
        n=len(ordered),
        p50=percentile(0.5),
        p95=percentile(0.95),
        p99=percentile(0.99) if len(ordered) >= 1000 else None,
        max=max(ordered) if ordered else None,
        convention="nearest-rank",
        p99_claim="eligible" if len(ordered) >= 1000 else "insufficient_sample",
    )


def summarize(rows):
    if len({r["request_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate_request_record")
    measured = [r for r in rows if not r.get("warmup", False)]
    for r in rows:
        if r["finish"] < r["arrival"] or not all(math.isfinite(r[k]) for k in ("arrival", "finish")):
            raise ValueError("invalid_request_clock")
    success = [r for r in measured if r["status"] == "success"]
    wall = max(r["finish"] for r in measured) - min(r["arrival"] for r in measured) if measured else 0
    return dict(
        schema_revision="benchmark-summary-v1",
        scope="SMOKE_or_exploratory_until_Stage_D",
        sample_count=len(measured),
        warmup_count=len(rows) - len(measured),
        status_counts=dict(sorted(Counter(r["status"] for r in measured).items())),
        admitted=sum(r.get("admission") is not None for r in measured),
        completed=len(success),
        success_latency_ms=percentiles([(r["finish"] - r["arrival"]) * 1000 for r in success]),
        all_termination_latency_ms=percentiles([(r["finish"] - r["arrival"]) * 1000 for r in measured]),
        wall_seconds=wall,
        success_rps=len(success) / wall if wall > 0 else None,
        offered_rps=len(measured) / wall if wall > 0 else None,
        degraded_count=sum(bool(r.get("degraded")) for r in measured),
        unknown_cost_count=sum(r.get("estimated_yuan") is None for r in measured),
        raw_sha256=hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        limitation="Closed-loop workload; coordinated omission possible. Small samples do not establish production SLA or eight-user capacity.",
    )


def write_report(directory):
    directory = Path(directory)
    rows = [
        json.loads(line) for line in (directory / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    summary = summarize(rows)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (directory / "report.md").write_text(
        "# Benchmark smoke\n\n" + json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    print(json.dumps(write_report(args.directory)))
