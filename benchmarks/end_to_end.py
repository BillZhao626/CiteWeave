"""Real product QueryRun/retrieval/citation path with deterministic mock generation."""

import argparse
import asyncio
import json
import time
from contextlib import aclosing
from pathlib import Path
from uuid import UUID

from benchmarks.concurrent import run_workload
from benchmarks.manifest import source_identity, validate
from citeweave import answering, schemas
from citeweave.db import transaction
from citeweave.domain import QueryRunRow
from citeweave.settings import settings


class MockProvider:
    """Deterministic cited response; no semantic quality claim or paid HTTP request."""

    async def stream(self, messages):
        import re

        labels = list(dict.fromkeys(re.findall(r'"label"\s*:\s*"(E\d+)"', messages[1]["content"])))
        yield {"text": "Engineering smoke evidence " + " ".join(f"[{label}]" for label in labels) + "."}
        yield {
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            "model": "deterministic-mock",
            "provider_id": "mock-no-network",
        }


def operation(workspace, kb_id, profile, provider="mock", budget_yuan=0):
    if provider == "real" and budget_yuan <= 0:
        raise ValueError("real_provider_requires_explicit_budget")
    reserved = 0
    budget_lock = asyncio.Lock()

    async def request(question, row):
        nonlocal reserved
        if provider == "real":
            async with budget_lock:
                if reserved + 0.10 > budget_yuan:
                    from fastapi import HTTPException

                    raise HTTPException(429, "benchmark_budget_exhausted")
                reserved += 0.10
        # Admission cancellation cannot leave an unowned blocking thread: begin_query
        # has bounded model/PG waits, and the admitted query owns its own PG deadline.
        run = await asyncio.to_thread(
            answering.begin_query,
            workspace,
            schemas.QueryCreate(kb_id=kb_id, question=question, profile=profile),
            "benchmark:" + row["request_id"],
        )
        row.update(admission=time.perf_counter(), start=time.perf_counter(), run_id=str(run.id))
        try:
            async with aclosing(
                answering.stream_answer(run, provider=MockProvider() if provider == "mock" else None)
            ) as stream:
                async for event in stream:
                    value = json.loads(event.removeprefix("data: "))
                    if value["type"] == "delta" and "ttft" not in row:
                        row["ttft"] = time.perf_counter()
                    if value["type"] == "final":
                        row["validated_final"] = time.perf_counter()
        finally:
            with transaction() as db:
                saved = db.get(QueryRunRow, run.id)
            pack = saved.evidence_pack or {}
            row.update(
                status="success" if saved.status == "COMPLETED" else "failure",
                error_code=saved.error_code,
                stages=saved.stages,
                calls=saved.calls,
                candidate_count=len(saved.candidates),
                seed_count=sum(bool(c.get("seed_rank")) for c in saved.candidates),
                evidence_count=len(pack.get("spans", [])),
                degraded=bool(pack.get("degraded")),
                usage=saved.usage,
                estimated_yuan=float(saved.estimated_yuan) if saved.estimated_yuan is not None else None,
            )
            checks = []
            for citation in (saved.result or {}).get("citations", []):
                actual = answering.get_citation(workspace, saved.id, UUID(citation["evidence_id"]))
                checks.append(actual.span.model_dump(mode="json") == citation["span"])
            row["physical_citations"] = dict(valid=sum(checks), count=len(checks))

    return request


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--questions", type=Path, required=True, help="Independent performance pool JSON list; never Holdout"
    )
    parser.add_argument("--workspace", type=UUID, default=settings().workspace_id)
    parser.add_argument("--kb", type=UUID, required=True)
    parser.add_argument("--profile", default="telecom-structural-v1")
    parser.add_argument("--provider", choices=["mock", "real"], default="mock")
    parser.add_argument("--budget-yuan", type=float, default=0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def inputs(args):
    manifest = validate(json.loads(args.manifest.read_text(encoding="utf-8")))
    if (
        manifest["source"] != source_identity()
        or manifest["provider"] != args.provider
        or manifest["budget_yuan"] != args.budget_yuan
    ):
        raise ValueError("benchmark_frozen_configuration_changed")
    if "holdout" in args.questions.name.lower():
        raise ValueError("holdout_not_a_performance_pool")
    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    if (
        not isinstance(questions, list)
        or not questions
        or any(not isinstance(q, str) or len(q) > 512 for q in questions)
    ):
        raise ValueError("performance_pool_invalid")
    return manifest, questions


if __name__ == "__main__":
    args = arguments()
    manifest, questions = inputs(args)
    print(
        json.dumps(
            asyncio.run(
                run_workload(
                    operation(args.workspace, args.kb, args.profile, args.provider, args.budget_yuan),
                    questions,
                    manifest,
                    args.output,
                )
            )
        )
    )
