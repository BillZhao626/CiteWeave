"""Real PostgreSQL admission/recovery/auth; provider-free controlled fixtures."""

import asyncio
import os
from contextlib import aclosing
from dataclasses import asdict
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from citeweave import answering, catalog, schemas
from citeweave.api import create_app
from citeweave.circuit import Circuit
from citeweave.db import migrate, transaction
from citeweave.domain import CircuitRow, DocumentRow, EvalCaseRow, QueryRunRow, VersionRow
from citeweave.evaluation import service
from citeweave.evaluation.dataset import load_dataset
from citeweave.reliability import CircuitOpen, CircuitState
from citeweave.settings import settings
from citeweave.trace import record_call

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="isolated PostgreSQL required"),
]
TOKEN = "m2-test-owner-only-not-production"


def corpus_metadata():
    migrate()
    workspace = uuid4()
    kb, _ = catalog.create_kb(
        workspace, schemas.KnowledgeBaseCreate(name="Evaluation contract fixture"), "kb"
    )
    dataset, _ = load_dataset()
    with transaction() as db:
        for source in dataset["sources"]:
            doc = DocumentRow(id=uuid4(), kb_id=kb.id, title=source["source_id"])
            db.add(doc)
            db.flush()
            version = VersionRow(
                id=uuid4(),
                document_id=doc.id,
                kb_id=kb.id,
                sequence=1,
                filename="metadata-only.pdf",
                license="fixture",
                source_sha256=source["sha256"],
                blob_key=source["sha256"],
                status="READY",
                index_collection="fixture_" + uuid4().hex,
                profile={},
                key=source["source_id"],
                fingerprint="0" * 64,
            )
            db.add(version)
            doc.active_version_id = version.id
    return workspace, kb


def test_eval_api_frozen_scope_auth_pagination_idempotency_and_cancel():
    workspace, kb = corpus_metadata()
    headers = {"Authorization": "Bearer " + TOKEN, "Idempotency-Key": "evaluation"}
    with TestClient(create_app(TOKEN, workspace)) as client:
        body = {
            "kb_id": str(kb.id),
            "dataset_id": "public-standards-v1",
            "split": "test",
            "profile": "m2",
            "judge_profile": "judge-v1",
        }
        assert client.post("/v1/evaluations", json=body).status_code == 401
        response = client.post("/v1/evaluations", json=body, headers=headers)
        assert response.status_code == 202
        value = response.json()
        identity = value["id"]
        assert len(value["versions"]) == len(value["runtime_config"]["index_bindings"]) == 3
        assert client.post("/v1/evaluations", json=body, headers=headers).json()["id"] == identity
        assert (
            client.post("/v1/evaluations", json=dict(body, profile="m3-context"), headers=headers).status_code
            == 409
        )
        assert (
            client.post(
                "/v1/evaluations", json=dict(body, judge_profile="judge-v4"), headers=headers
            ).status_code
            == 409
        )
        assert (
            client.post("/v1/evaluations", json=dict(body, split="dev"), headers=headers).status_code == 409
        )
        endpoint = "/v1/evaluations/" + identity
        first = client.get(endpoint + "/cases?limit=1", headers=headers).json()
        second = client.get(endpoint + "/cases?limit=1&offset=1", headers=headers).json()
        assert len(first) == len(second) == 1 and first[0]["case_id"] != second[0]["case_id"]
        assert client.get(endpoint + "/cases?limit=101", headers=headers).status_code == 422
        assert client.get(endpoint + "/report", headers=headers).status_code == 200
        with TestClient(create_app(TOKEN, uuid4())) as other:
            for path in (endpoint, endpoint + "/cases", endpoint + "/artifact", endpoint + "/report"):
                assert other.get(path, headers=headers).status_code == 404
            assert (
                other.get(
                    endpoint + "/compare", params={"baseline_id": identity}, headers=headers
                ).status_code
                == 404
            )
            assert other.post(endpoint + "/cancel", headers=headers).status_code == 404
        assert client.post(endpoint + "/cancel", headers=headers).json()["status"] == "CANCELLED"
        assert client.post(endpoint + "/cancel", headers=headers).json()["status"] == "CANCELLED"
        cases = client.get(endpoint + "/cases?limit=100", headers=headers).json()
        assert len(cases) == 24 and all(c["status"] == "CANCELLED" for c in cases)


def test_historical_terminal_evaluation_never_reopens_or_reissues_reserved_judge():
    workspace, kb = corpus_metadata()
    evaluation = service.create(workspace, kb.id, "public-standards-v1", "dev", "legacy-terminal")
    with transaction() as db:
        case = db.scalar(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == evaluation.id))
        case_id = case.case_id
        case.status = "COMPLETED"
        case.result = {"status": "COMPLETED", "answer": {"text": "saved original fixture"}}
        case.judge = {"status": "FAILED", "error_code": "judge_unknown_after_interruption"}
        case.judge_reserved_yuan = Decimal("0.10")
        expected = (case.result, case.judge)
    service.run_case(str(evaluation.id), case_id)  # pre-generation historical message
    service.run_case(str(evaluation.id), case_id, 0)
    service.reconcile(lambda *args: None)
    with transaction() as db:
        row = db.get(EvalCaseRow, (evaluation.id, case_id))
        assert row.status == "COMPLETED"
        assert (row.result, row.judge) == expected
        assert row.execution_attempt == 0
        assert row.judge_estimated_yuan is None
    service.cancel(workspace, evaluation.id)


def test_shared_pg_breaker_rejects_second_probe_and_recovers():
    migrate()
    first, second = Circuit("deepseek"), Circuit("deepseek")
    with transaction() as db:
        row = db.get(CircuitRow, "deepseek")
        if row:
            row.value = asdict(CircuitState())
    for _ in range(settings().breaker_threshold):
        first.change("failure", first.change("acquire"))
    with pytest.raises(CircuitOpen):
        second.change("acquire")
    with transaction() as db:
        row = db.get(CircuitRow, "deepseek")
        row.value = dict(row.value, until=0)
    probe = second.change("acquire")
    with pytest.raises(CircuitOpen):
        first.change("acquire")
    second.change("success", probe)
    assert first.change("acquire") == probe
    with transaction() as db:
        assert db.get(CircuitRow, "deepseek").value["state"] == "closed"


def test_query_consumer_close_persists_cancel_and_failed_attempt_cost(monkeypatch):
    workspace, kb = corpus_metadata()
    run = answering.begin_query(
        workspace, schemas.QueryCreate(kb_id=kb.id, question="cancel fixture"), "query"
    )
    from types import SimpleNamespace

    class Retriever:
        def retrieve(self, *args):
            return [SimpleNamespace()], []

    monkeypatch.setattr(
        answering,
        "citation_for",
        lambda *args: SimpleNamespace(label="E1", span=SimpleNamespace(quote="fixture")),
    )
    closed = []

    class Provider:
        async def stream(self, messages):
            try:
                yield {"usage": {"prompt_tokens": 10, "completion_tokens": 1}}
                yield {"text": "provisional [E1]"}
                raise AssertionError("Cancelled consumer must not advance upstream")
            finally:
                closed.append(True)
                record_call(dict(upstream="deepseek", status="CANCELLED", estimated_yuan=0.01234))

    async def consume():
        async with aclosing(
            answering.stream_answer(run, provider=Provider(), retriever=Retriever())
        ) as stream:
            async for part in stream:
                if '"type":"delta"' in part:
                    break

    asyncio.run(consume())
    assert closed == [True]
    with transaction() as db:
        row = db.get(QueryRunRow, run.id)
        assert row.status == "FAILED" and row.error_code == "client_cancelled"
        assert row.result is None and row.usage["completion_tokens"] == 1
        assert row.estimated_yuan is None and row.completed_at  # incomplete paid outcome retains reservation
        assert row.calls[0]["estimated_yuan"] == 0.01234  # visible partial accounting is retained
        assert row.calls[0]["status"] == "CANCELLED"
        from citeweave.domain import ProviderPhaseRow

        phase = db.scalar(select(ProviderPhaseRow).where(ProviderPhaseRow.query_run_id == run.id))
        assert phase.state == "UNKNOWN" and phase.reserved_yuan == Decimal("0.10")
        assert phase.usage["completion_tokens"] == 1
