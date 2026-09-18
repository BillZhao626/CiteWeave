"""Run unchanged M1 through adapters that observe, but never alter retrieval results.

This command is the one-time M1 baseline harness. The durable product runner imports
the same frozen dataset/assessor; keep this record to distinguish pre-M2 measurements.
"""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select

from citeweave.answering import PROMPT, begin_query, stream_answer
from citeweave.db import transaction
from citeweave.domain import QueryRunRow
from citeweave.evaluation.assessment import Assessor
from citeweave.evaluation.dataset import load_dataset
from citeweave.hybrid import HybridRetriever
from citeweave.index import QdrantIndex
from citeweave.pipeline import PROFILE
from citeweave.retrieval import ANALYZER_REVISION
from citeweave.schemas import QueryCreate
from citeweave.settings import ROOT, settings


class CaptureIndex(QdrantIndex):
    def __init__(self):
        super().__init__()
        self.observed = []

    def branches(self, collection, version_id, dense, sparse, limit=40):
        start = time.perf_counter()
        result = super().branches(collection, version_id, dense, sparse, limit)
        self.observed.append(
            dict(
                collection=collection,
                version_id=str(version_id),
                dense=result[0],
                bm25=result[1],
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        )
        return result


def prepare(dataset, digest):
    client = httpx.Client(
        base_url="http://127.0.0.1:18080",
        timeout=15,
        headers={"Authorization": "Bearer " + settings().admin_token.get_secret_value()},
    )
    response = client.post(
        "/v1/knowledge-bases",
        json={
            "name": "公开标准 · 冻结评测集 v1",
            "description": "3 public PDFs / 48 frozen questions; source and license in evals manifest.",
        },
        headers={"Idempotency-Key": "eval-corpus-" + digest},
    )
    response.raise_for_status()
    kb = response.json()["id"]
    versions, jobs = {}, []
    for source in dataset["sources"]:
        raw = (ROOT / ".runtime/evaluation/corpus" / source["filename"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("corpus_hash_mismatch")
        response = client.post(
            f"/v1/knowledge-bases/{kb}/documents",
            params={"filename": source["filename"], "license": "permission-held"},
            content=raw,
            headers={"Content-Type": "application/pdf", "Idempotency-Key": source["sha256"]},
        )
        response.raise_for_status()
        value = response.json()
        versions[source["source_id"]] = value["version"]["id"]
        jobs.append(value["job"]["id"])
    deadline = time.monotonic() + 900
    while jobs and time.monotonic() < deadline:
        for job in jobs[:]:
            response = client.get(f"/v1/jobs/{job}")
            response.raise_for_status()
            value = response.json()
            if value["status"] == "READY":
                jobs.remove(job)
                print("PDF READY", job, flush=True)
            elif value["status"] == "FAILED_FINAL":
                raise RuntimeError("corpus_ingestion_failed:" + str(value["error_code"]))
        if jobs:
            time.sleep(3)
    client.close()
    if jobs:
        raise TimeoutError("corpus_ingestion_deadline")
    return kb, versions


async def main():
    dataset, digest = load_dataset()
    identity = str(uuid4())
    directory = ROOT / ".runtime/evaluation/runs" / identity
    directory.mkdir(parents=True)
    kb, versions = prepare(dataset, digest)
    (ROOT / ".runtime/evaluation/corpus-binding.json").write_text(
        json.dumps(dict(kb_id=kb, versions=versions, dataset_hash=digest)), encoding="utf-8"
    )
    config = dict(
        PROFILE,
        bm25_analyzer=ANALYZER_REVISION,
        bm25_k1=1.5,
        bm25_b=0.75,
        chunk_overlap=0,
        prompt_identity="answer-v1",
        prompt_sha256=hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
        provider="deepseek",
        model=settings().deepseek_model,
        query_deadline_seconds=settings().query_deadline_seconds,
        source_code={
            name: hashlib.sha256((ROOT / "src/citeweave" / name).read_bytes()).hexdigest()
            for name in ("hybrid.py", "pipeline.py", "retrieval.py", "answering.py", "llm.py", "index.py")
        },
    )
    report = dict(
        eval_run_id=identity,
        kind="M1 baseline",
        dataset_hash=digest,
        kb_id=kb,
        versions=versions,
        started_at=datetime.now(timezone.utc).isoformat(),
        config=config,
        status="RUNNING",
        cases=[],
    )
    (directory / "run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    assessor = Assessor(settings().workspace_id, versions)
    # Gold validation runs before the first model call; annotations never enter answering inputs.
    for case in dataset["cases"]:
        assessor.gold_ids(case)
    for case in dataset["cases"]:
        index = CaptureIndex()
        start = time.perf_counter()
        run = begin_query(
            settings().workspace_id,
            QueryCreate(kb_id=kb, question=case["question"]),
            identity + ":" + case["case_id"],
        )
        async for _ in stream_answer(run, retriever=HybridRetriever(index=index)):
            pass
        with transaction() as db:
            row = db.scalar(select(QueryRunRow).where(QueryRunRow.id == run.id))
        result = dict(
            case_id=case["case_id"],
            split=case["split"],
            query_run_id=str(run.id),
            status=row.status,
            question=case["question"],
            question_type=case["question_type"],
            answer=row.result,
            error_code=row.error_code,
            usage=row.usage,
            estimated_yuan=float(row.estimated_yuan) if row.estimated_yuan is not None else None,
            latency_ms=(time.perf_counter() - start) * 1000,
            branches=index.observed,
            candidates=row.candidates,
        )
        result["assessment"] = assessor.assess(case, run.id, index.observed, row.candidates, row.result)
        (directory / (case["case_id"] + ".json")).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report["cases"].append(
            {
                k: result[k]
                for k in (
                    "case_id",
                    "split",
                    "query_run_id",
                    "status",
                    "error_code",
                    "estimated_yuan",
                    "latency_ms",
                )
            }
        )
        (directory / "run.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            case["case_id"],
            row.status,
            row.error_code or "ok",
            "final_gold",
            result["assessment"]["evidence"]["final"],
            flush=True,
        )
    report["status"] = "COMPLETED"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    (directory / "run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / ".runtime/evaluation/m1-baseline-id.txt").write_text(identity, encoding="ascii")
    print("BASELINE SAVED", identity, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
