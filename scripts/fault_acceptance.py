"""Real Docker worker kills at three persisted ingestion stages. No LLM calls."""

import argparse
import json
import os
import subprocess
import time
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select

from citeweave.db import transaction
from citeweave.domain import ChunkRow, DocumentRow, IngestionJobRow, VersionRow
from citeweave.index import QdrantIndex
from citeweave.settings import ROOT, settings

COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".env",
    "-f",
    "deploy/compose.m0.yml",
    "-f",
    "deploy/compose.m1.yml",
]


def command(args, env=None):
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError("container_command_failed: " + args[0])


def wait_until(probe, timeout=100):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = probe()
        if result:
            return result
        time.sleep(0.5)
    raise TimeoutError("acceptance_deadline")


def counts(version_id):
    with transaction() as db:
        version = db.get(VersionRow, version_id)
        doc = db.get(DocumentRow, version.document_id)
        count = db.scalar(select(func.count()).select_from(ChunkRow).where(ChunkRow.version_id == version_id))
        return {
            "status": version.status,
            "active": str(doc.active_version_id) if doc.active_version_id else None,
            "chunks": count,
            "collection": version.index_collection,
            "expected_chunks": version.chunk_count,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--milestone", choices=["m1", "m2", "m3"], default="m3")
    parser.add_argument("--report-prefix")
    options = parser.parse_args()
    label = options.report_prefix or options.milestone
    if not label.replace("-", "").isalnum():
        raise ValueError("invalid_report_prefix")
    headers = {"Authorization": "Bearer " + settings().admin_token.get_secret_value()}
    client = httpx.Client(base_url="http://127.0.0.1:18080", headers=headers, timeout=10)
    env = dict(os.environ, CW_ENABLE_FAULTS="true")
    faults = ROOT / ".runtime/faults"
    faults.mkdir(parents=True, exist_ok=True)
    results, markers = [], []
    try:
        command(COMPOSE + ["up", "-d", "--force-recreate", "m1-worker"], env)
        for stage in ("PARSING", "EMBEDDING", "INDEXING"):
            command(COMPOSE + ["stop", "m1-worker"], env)
            kb = client.post(
                "/v1/knowledge-bases",
                json={"name": "Fault " + stage + " " + str(uuid4())[:8]},
                headers={"Idempotency-Key": str(uuid4())},
            )
            kb.raise_for_status()
            upload = client.post(
                f"/v1/knowledge-bases/{kb.json()['id']}/documents",
                params={"filename": "fault-original.pdf", "license": "original"},
                content=(ROOT / "apps/web/public/original-handbook.pdf").read_bytes(),
                headers={"Content-Type": "application/pdf", "Idempotency-Key": str(uuid4())},
            )
            upload.raise_for_status()
            job_id, version_id = upload.json()["job"]["id"], UUID(upload.json()["version"]["id"])
            marker = faults / f"{job_id}.{stage}.pause"
            marker.write_text("explicit acceptance barrier")
            markers.append(marker)
            command(COMPOSE + ["start", "m1-worker"], env)
            wait_until(lambda: marker.with_suffix(".reached").exists())
            with transaction() as db:
                job = db.get(IngestionJobRow, UUID(job_id))
                first_fence = job.fence
                assert job.status == stage and job.attempt == 1
            before = counts(version_id)
            assert before["chunks"] == 0 and before["active"] is None and before["collection"] is None
            blocked = client.post(
                "/v1/queries",
                json={"kb_id": kb.json()["id"], "question": "温度采样频率？"},
                headers={"Idempotency-Key": str(uuid4())},
            )
            assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "no_ready_documents"
            staging_points = 0
            if stage == "INDEXING":
                staging_points = (
                    QdrantIndex().client.count(f"cw1_v{version_id.hex}_f{first_fence}", exact=True).count
                )
                assert staging_points == 16  # A real partial index exists, still invisible to queries.
            killed_at = time.monotonic()
            command(["docker", "kill", "--signal=KILL", "citeweave-m0-m1-worker-1"])
            marker.unlink()
            command(COMPOSE + ["start", "m1-worker"], env)

            def recovered():
                current = counts(version_id)
                if current["status"] == "FAILED_FINAL":
                    raise AssertionError("recovery_failed_final")
                if current["status"] != "READY":
                    assert current["active"] is None and current["chunks"] == 0
                    return None
                return current

            after = wait_until(recovered)
            assert after["active"] == str(version_id) and after["chunks"] == after["expected_chunks"] > 16
            index = QdrantIndex()
            with transaction() as db:
                job = db.get(IngestionJobRow, UUID(job_id))
                assert job.attempt == 2 and job.status == "READY"
                assert any(e["code"] == "worker_lease_expired" for e in job.events)
                events, fence = job.events, job.fence
                ids = [
                    str(i) for i in db.scalars(select(ChunkRow.id).where(ChunkRow.version_id == version_id))
                ]
            index.verify(after["collection"], ids)
            assert after["collection"] == f"cw1_v{version_id.hex}_f{fence}"
            # Force delivery of the same completed job and inspect durable invariants again.
            from citeweave.ingestion import run_ingestion

            run_ingestion(job_id)
            assert counts(version_id) == after
            result = {
                "stage": stage,
                "status": "PASS",
                "job_id": job_id,
                "version_id": str(version_id),
                "attempts": 2,
                "partial_staging_points": staging_points,
                "before": before,
                "after": after,
                "recovery_seconds": round(time.monotonic() - killed_at, 3),
                "events": events,
                "duplicate_effective_results": 0,
                "fake_ready_observed": False,
            }
            results.append(result)
            print(
                json.dumps({k: result[k] for k in ("stage", "status", "attempts", "recovery_seconds")}),
                flush=True,
            )
    finally:
        for marker in markers:
            marker.unlink(missing_ok=True)
        command(
            COMPOSE + ["up", "-d", "--force-recreate", "m1-worker"],
            dict(os.environ, CW_ENABLE_FAULTS="false"),
        )
        target = ROOT / f"docs/reports/{label}-faults.json"
        target.write_text(
            json.dumps(
                {
                    "scenarios": results,
                    "expected": 3,
                    "passed": len(results),
                    "faults_disabled_after_run": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
