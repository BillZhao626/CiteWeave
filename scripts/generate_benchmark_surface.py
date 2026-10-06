"""Build a local, read-only Benchmark view from preserved raw measurements.

This never executes a workload or changes the source receipts. Generated assets
are local evidence and are excluded from the publication tree.
"""

import argparse
import hashlib
import json
import math
import zipfile
from collections import Counter
from pathlib import Path

from benchmarks.report import percentiles

ROOT = Path(__file__).resolve().parents[1]
PROFILES = (
    ("baseline", "baseline-a-v2", "A", "优化前"),
    ("final", "final-a-v2", "A", "优化后"),
    ("qdrant", "retrieval-b-v2", "B", "Qdrant 检索路径"),
)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected):
    if isinstance(actual, (float, int)) and isinstance(expected, (float, int)):
        return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9)
    return actual == expected


def generate(receipts, output):
    frozen_path = receipts / "frozen-contract.json"
    frozen = read(frozen_path)
    contract = frozen["contract"]
    levels = contract["concurrency"]
    if levels != [1, 5, 10, 20] or contract["revision"] != "conversation-m3-v2":
        raise ValueError("unsupported_benchmark_contract")
    archive_files = {"frozen-contract.json": frozen_path}
    profiles = []
    for key, folder, profile, label in PROFILES:
        directory = receipts / folder
        manifest = read(directory / "manifest.json")
        recorded = read(directory / "summary.json")
        hashes = read(directory / "hashes.json")
        if manifest["contract_sha256"] != frozen["contract_sha256"]:
            raise ValueError("benchmark_contract_mismatch")
        if manifest["contract"] != contract or manifest["profile"] != profile:
            raise ValueError("benchmark_profile_mismatch")
        if manifest["source"]["harness_hashes"] != frozen["source"]["harness_hashes"]:
            raise ValueError("benchmark_harness_mismatch")
        if manifest["provider_model_judge_calls"] != 0 or manifest["monetary_spend_cny"] != 0:
            raise ValueError("unexpected_live_measurement")
        for name, digest in hashes.items():
            path = (directory / name).resolve()
            if path.parent != directory.resolve() or sha(path) != digest:
                raise ValueError("preserved_receipt_hash_mismatch")
        results, sources = [], []
        for concurrency in levels:
            repeats, warmups, rows = [], [], []
            for repeat in range(1, contract["repeats"] + 1):
                filename = f"c{concurrency:02}-r{repeat}.json"
                raw_path = directory / filename
                raw = read(raw_path)
                warmup_path = directory / f"c{concurrency:02}-r{repeat}-warmup.json"
                warmup = read(warmup_path)
                if raw["concurrency"] != concurrency or raw["repeat"] != repeat:
                    raise ValueError("raw_workload_identity_mismatch")
                if len(raw["rows"]) != contract["requests_per_repeat"]:
                    raise ValueError("raw_attempt_count_mismatch")
                if len(warmup["rows"]) != contract["warmup_per_repeat"]:
                    raise ValueError("raw_warmup_count_mismatch")
                rows.extend(raw["rows"])
                repeats.append(raw)
                warmups.extend(warmup["rows"])
                for path in (raw_path, warmup_path):
                    archive_files[f"{folder}/{path.name}"] = path
                    sources.append({"path": f"{folder}/{path.name}", "sha256": sha(path)})
            if len({row["identity"] for row in rows}) != len(rows):
                raise ValueError("duplicate_measured_identity")
            successful = sum(row["status"] == "success" for row in rows)
            wall = sum(raw["summary"]["wall_seconds"] for raw in repeats)
            latencies = percentiles(row["latency_ms"] for row in rows)
            result = {
                "concurrency": concurrency,
                "attempted": len(rows),
                "successful": successful,
                "failed": len(rows) - successful,
                "timeouts": sum(row["status"] == "timeout" for row in rows),
                "statuses": dict(sorted(Counter(row["status"] for row in rows).items())),
                "p50_ms": latencies["p50"],
                "p95_ms": latencies["p95"],
                "max_ms": latencies["max"],
                "successful_per_second": successful / wall,
                "wall_seconds": wall,
                "warmup_attempted": len(warmups),
                "warmup_failed": sum(row["status"] != "success" for row in warmups),
                "correctness_cardinality": all(raw["correctness_cardinality"] for raw in repeats),
                "warmup_correct": all(raw["warmup_correct"] for raw in repeats),
                "repeat_p95_ms": [raw["summary"]["latency_ms"]["p95"] for raw in repeats],
                "repeat_successful": [raw["summary"]["successful"] for raw in repeats],
            }
            expected = recorded[str(concurrency)]
            comparisons = {
                "attempted": "attempted",
                "successful": "successful",
                "failed": "failed",
                "timeouts": "timeouts",
                "wall_seconds": "wall_seconds",
                "successful_per_second": "throughput_rps",
                "correctness_cardinality": "correctness_cardinality",
                "warmup_correct": "warmup_correct",
            }
            for actual_key, expected_key in comparisons.items():
                if not close(result[actual_key], expected[expected_key]):
                    raise ValueError("recomputed_summary_mismatch")
            if not close(result["p95_ms"], expected["latency_ms"]["p95"]):
                raise ValueError("recomputed_percentile_mismatch")
            results.append(result)
        for name in ("manifest.json", "summary.json", "hashes.json", "completed.json", "duplicate.json"):
            archive_files[f"{folder}/{name}"] = directory / name
        profiles.append(
            {
                "id": key,
                "label": label,
                "profile": profile,
                "measured_at": manifest["timestamp"],
                "source_commit": manifest["source"]["commit"],
                "source_tree": manifest["source"]["tree"],
                "source_dirty": manifest["source"]["dirty"],
                "raw_sources": sources,
                "results": results,
            }
        )
    environment = read(receipts / "final-a-v2/manifest.json")["environment"]
    artifact = {
        "schema_revision": "benchmark-surface-v1",
        "origin": "preserved-local-raw-measurements",
        "measurement_date": "2026-10-03",
        "contract_sha256": frozen["contract_sha256"],
        "contract_frozen_at": frozen["frozen_at"],
        "contract": contract,
        "environment": {
            key: environment[key]
            for key in (
                "os",
                "os_release",
                "architecture",
                "python",
                "logical_cpus",
                "total_memory_bytes",
                "postgres",
            )
        },
        "profiles": profiles,
        "scope": "Real loopback FastAPI/ProductionRuntime/PostgreSQL; synthetic model and provider transport. Profile B adds real Qdrant with three original points and synthetic 2D embedding/reranking.",
        "method": "Finite closed-loop workload. Each level: 3 repeats × 40 measured + 20 warmup per repeat. p95 pools all attempted workflow termination latencies, including failures. Successful throughput divides accepted/readback workflows by summed measured wall time.",
        "raw_archive": "conversation-v2-raw.zip",
    }
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / artifact["raw_archive"]
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sorted(archive_files.items()):
            archive.write(path, name)
    artifact["raw_archive_sha256"] = sha(archive_path)
    (output / "conversation-v2.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Recomputed {len(profiles)} profiles / {len(profiles) * len(levels) * 120} measured attempts; original receipts unchanged."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path, default=ROOT / ".runtime/performance/m3")
    parser.add_argument("--output", type=Path, default=ROOT / "apps/web/public/benchmarks")
    args = parser.parse_args()
    generate(args.receipts.resolve(), args.output.resolve())
