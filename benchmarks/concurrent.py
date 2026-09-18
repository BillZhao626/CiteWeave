"""Closed-loop bounded async driver preserving all terminal request records."""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException

from benchmarks.manifest import validate
from benchmarks.report import write_report


async def run_workload(operation, questions, manifest, output):
    validate(manifest)
    path = Path(output)
    path.mkdir(parents=True, exist_ok=False)
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    rows = []
    queue = asyncio.Queue()
    for i in range(manifest["warmup"]):
        queue.put_nowait(i)

    async def client(session):
        while not queue.empty():
            try:
                i = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            question = questions[i % len(questions)]
            row = dict(
                request_id=str(uuid4()),
                session_id=session,
                sequence=i,
                warmup=i < manifest["warmup"],
                question_sha256=hashlib.sha256(question.encode()).hexdigest(),
                arrival=time.perf_counter(),
                wall_timestamp=datetime.now(timezone.utc).isoformat(),
                admission=None,
                start=None,
                finish=None,
                status="failure",
                error_code=None,
                http_status=None,
                stages=[],
                calls=[],
                degraded=False,
                estimated_yuan=None,
                usage=None,
                candidate_count=0,
                seed_count=0,
                evidence_count=0,
            )
            try:
                async with asyncio.timeout(manifest["environment"]["limits"]["request_deadline_seconds"]):
                    await operation(question, row)
            except HTTPException as exc:
                row.update(
                    status="429" if exc.status_code == 429 else "admission_rejected",
                    http_status=exc.status_code,
                    error_code=str(exc.detail)[:80],
                )
            except TimeoutError:
                row.update(status="timeout", error_code="request_deadline")
            except asyncio.CancelledError:
                row.update(status="cancelled", error_code="cancelled")
            except Exception as exc:
                row.update(status="failure", error_code=type(exc).__name__)
            finally:
                row["finish"] = time.perf_counter()
                rows.append(row)
                with (path / "requests.jsonl").open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                with (path / "stages.jsonl").open("a", encoding="utf-8") as stream:
                    for stage in row["stages"]:
                        stream.write(json.dumps(dict(request_id=row["request_id"], **stage)) + "\n")

    await asyncio.gather(*(client(i) for i in range(manifest["concurrency"])))
    for i in range(manifest["warmup"], manifest["warmup"] + manifest["request_count"]):
        queue.put_nowait(i)
    await asyncio.gather(*(client(i) for i in range(manifest["concurrency"])))
    if len(rows) != manifest["request_count"] + manifest["warmup"]:
        raise ValueError("benchmark_request_loss")
    summary = write_report(path)
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(path.iterdir()) if p.is_file()
    }
    (path / "artifacts.json").write_text(
        json.dumps(dict(completed_at=datetime.now(timezone.utc).isoformat(), sha256=hashes), indent=2) + "\n",
        encoding="utf-8",
    )
    return summary
