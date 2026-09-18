"""Original counting-provider fault workload; real Celery task/PG lifecycle/ledger.

Run only in an isolated test process. No credentials or remote paid endpoint.
The product answer/retrieval integration is exercised separately.
"""

import asyncio
import os
from uuid import uuid4

import httpx

from citeweave.celery_app import app
from citeweave.db import transaction
from citeweave.domain import QueryRunRow
from citeweave.evaluation import execution
from citeweave.evaluation import lifecycle as lc
from citeweave.provider_phases import DurableProvider, evaluation_owner, prepare


class CountingProvider:
    attempts = []

    def __init__(self, token, phase, scenario):
        self.token, self.phase, self.scenario = token, phase, scenario

    async def stream(self, messages):
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.post(
                os.environ["CW_COUNTING_ENDPOINT"],
                json=dict(run_id=str(self.token.eval_id), phase=self.phase, scenario=self.scenario),
            )
        if response.status_code == 429:
            from citeweave.llm import ProviderError

            raise ProviderError("llm_http_429")
        if self.scenario == self.phase + "_unknown":
            raise TimeoutError("controlled_after_dispatch")
        if self.scenario in {self.phase + "_kill", "cancel_running", "stale_result"}:
            await asyncio.sleep(45)
        yield {"text": "Original counted fixture response"}
        yield {"usage": {"prompt_tokens": 2, "completion_tokens": 3}}


async def workload(eval_id, case_id, owner):
    token = evaluation_owner.get()
    with transaction() as db:
        case, run, now = lc.owned(db, token)
        scenario = run.runtime_config["fault_scenario"]
        q = db.get(QueryRunRow, case.query_run_id) if case.query_run_id else None
        if q is None or q.status == "FAILED":
            from datetime import timedelta

            q = QueryRunRow(
                id=uuid4(),
                workspace_id=run.workspace_id,
                kb_id=run.kb_id,
                key=str(uuid4()),
                fingerprint="0" * 64,
                question="Original counting fixture?",
                owner=uuid4(),
                fence=1,
                absolute_deadline=now + timedelta(seconds=60),
                runtime_policy="provider-phases-v1",
            )
            db.add(q)
            db.flush()
            case.query_run_id = q.id
    if scenario == "prepared_kill":
        prepare(q.id, q.owner, q.fence, "answer", token)
        await asyncio.sleep(45)
    if q.status != "COMPLETED":
        provider = DurableProvider(
            CountingProvider(token, "answer", scenario), q.id, q.owner, q.fence, token=token
        )
        async for _ in provider.stream([]):
            pass
        with transaction() as db:
            lc.owned(db, token)
            query = db.get(QueryRunRow, q.id)
            query.status, query.result = "COMPLETED", {"text": "durable original answer", "citations": []}
        if scenario == "answer_committed_kill":
            await asyncio.sleep(45)
    provider = DurableProvider(CountingProvider(token, "judge", scenario), q.id, phase="judge", token=token)
    async for _ in provider.stream([]):
        pass
    lc.save(token, judge={"status": "COMPLETED", "scores": None}, status="COMPLETED")


if __name__ == "__main__":
    execution.execute_case = workload
    app.worker_main(
        [
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--queues=cw-evaluation",
            "--loglevel=ERROR",
            "--hostname=c4-fixture@local",
        ]
    )
