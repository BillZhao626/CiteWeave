"""Killed by a parent test at durable boundaries; never uses real transport."""

import json
import pickle
import sys
import time
from pathlib import Path

from conversation_evidence_fixtures import FakeModel, Fixture
from pydantic import SecretStr
from test_conversation_runtime_postgres import SyntheticAccounting, policy

from citeweave import conversation_provider as ledger
from citeweave import conversations as core
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_runtime import ProductionRuntime
from citeweave.db import engine
from citeweave.settings import settings


def main():
    payload, marker, stage = sys.argv[1:]
    with Path(payload).open("rb") as stream:
        sample, fields = pickle.load(stream)
    fixture = Fixture.__new__(Fixture)
    fixture.__dict__.update(fields)
    assert engine().url.database.startswith("cw_conversation_test_")
    if stage == "replay":
        from test_conversation_api import client
        from test_conversation_api_postgres import submit

        result = submit(client(sample[0]), sample)
        assert result.status_code == 200
        print(json.dumps({key: result.json()[key] for key in ("id", "status")}))
        return
    settings().deepseek_api_key = SecretStr("synthetic-key-never-sent")
    dispatch = ledger.dispatch
    complete = ledger.complete

    def stop_at_boundary():
        Path(marker).write_text(stage, encoding="utf-8")
        time.sleep(45)
        raise AssertionError("parent must terminate this test worker")

    def boundary(*args, **kwargs):
        if stage in {"after_dispatch", "after_result"}:
            dispatch(*args, **kwargs)
        if stage == "after_result":
            return
        stop_at_boundary()

    def completed_boundary(*args, **kwargs):
        complete(*args, **kwargs)
        stop_at_boundary()

    ledger.dispatch = boundary
    if stage == "after_result":
        ledger.complete = completed_boundary

    class FakeProvider:
        async def stream_request(self, body, *, before_send):
            before_send()
            if stage == "after_result":
                yield {
                    "text": fixture.atom.text + " [E1]",
                    "provider_id": "synthetic-crash-receipt",
                    "usage": {"prompt_tokens": 73, "completion_tokens": 20},
                }
                return
            raise AssertionError("transport must never execute")
            yield

    runtime = ProductionRuntime(
        policy(sample), SyntheticAccounting(), model=FakeModel(), provider_factory=FakeProvider
    )
    runtime.retriever = StructuralEvidenceRetriever(model=FakeModel(), branch_query=fixture.branch)
    run = core.admit(*sample[:2], "crash", sample[2], runtime.prepare())
    runtime.execute(sample[0], run)


if __name__ == "__main__":
    main()
