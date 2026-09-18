"""Actual product retriever workload, with no answer provider."""

import asyncio
import json
import time
from uuid import UUID

from benchmarks.concurrent import run_workload
from benchmarks.end_to_end import arguments, inputs
from citeweave import answering, schemas
from citeweave.hybrid import HybridRetriever
from citeweave.structural_retrieval import StructuralRetriever
from citeweave.trace import RunTrace, current_trace


def operation(workspace: UUID, kb_id: UUID, profile: str):
    async def request(question, row):
        run = await asyncio.to_thread(
            answering.begin_query,
            workspace,
            schemas.QueryCreate(kb_id=kb_id, question=question, profile=profile),
            "benchmark-retrieval:" + row["request_id"],
        )
        row.update(admission=time.perf_counter(), start=time.perf_counter(), run_id=str(run.id))
        trace = RunTrace(run.id, run.owner, run.fence)
        token = current_trace.set(trace)
        try:
            retriever = (
                StructuralRetriever(run.structural_snapshot)
                if run.structural_snapshot
                else HybridRetriever(index_bindings=run.index_bindings, profile=profile)
            )
            chunks, candidates = await asyncio.to_thread(retriever.retrieve, question, run.versions)
            pack = getattr(retriever, "pack", None)
            await asyncio.to_thread(answering.save_trace, run.id, candidates, run.owner, run.fence, pack)
            row.update(
                status="success",
                candidate_count=len(candidates),
                seed_count=sum(bool(c.get("seed_rank")) for c in candidates),
                evidence_count=len(chunks),
                stages=trace.stages,
                calls=trace.calls,
                estimated_yuan=0,
                degraded=bool(pack and pack.degraded),
            )
        finally:
            trace.cancelled.set()
            current_trace.reset(token)
            # A retrieval-only benchmark does not fabricate a completed answer QueryRun.
            await asyncio.to_thread(answering.failed, run.id, "benchmark_retrieval_only", False)

    return request


if __name__ == "__main__":
    args = arguments()
    manifest, questions = inputs(args)
    if args.provider != "mock":
        raise ValueError("retrieval_has_no_provider")
    print(
        json.dumps(
            asyncio.run(
                run_workload(
                    operation(args.workspace, args.kb, args.profile), questions, manifest, args.output
                )
            )
        )
    )
