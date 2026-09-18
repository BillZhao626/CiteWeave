"""Real local E5/BGE/PG/Qdrant against an original legal PDF; mock generation."""

import asyncio
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from structure_fixtures import original_pdf

from citeweave import answering, catalog, schemas
from citeweave.api import create_app
from citeweave.db import transaction
from citeweave.domain import IndexRow, IngestionJobRow, QueryRunRow, VersionRow
from citeweave.ingestion import run_ingestion
from citeweave.model_client import GatewayError, ModelGateway
from citeweave.query_evidence import read_query
from citeweave.structural_retrieval import StructuralRetriever

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="needs isolated services/models"),
]


class EngineeringProvider:
    calls = 0

    async def stream(self, messages):
        type(self).calls += 1
        pack = json.loads(messages[1]["content"].split("\n", 1)[1])
        assert len(messages[0]["content"]) + len(messages[1]["content"]) <= 12000
        yield {
            "text": "Engineering fixture evidence "
            + " ".join("[" + e["label"] + "]" for e in pack["evidence"])
        }


@pytest.fixture(scope="module")
def ready():
    workspace = uuid4()
    kb, _ = catalog.create_kb(
        workspace, schemas.KnowledgeBaseCreate(name="Original C3 integration"), str(uuid4())
    )
    result = catalog.upload(
        workspace,
        kb.id,
        original_pdf(),
        "original-c3.pdf",
        "original",
        "source",
        None,
        "telecom-protocol-pdf-v1",
    )
    run_ingestion(str(result.job.id))
    with transaction() as db:
        assert db.get(IngestionJobRow, result.job.id).status == "READY"
    return workspace, kb, result


def body(ready, **overrides):
    _, kb, _ = ready
    return schemas.QueryCreate(
        kb_id=kb.id,
        question="What must a receiver do with a damaged message?",
        profile="telecom-structural-v1",
        **overrides,
    )


def consume(run, model=None, query=None):
    kwargs = {"model": model} if model else {}
    if query:
        kwargs["branch_query"] = query
    retriever = StructuralRetriever(run.structural_snapshot, **kwargs)

    async def collect():
        return [
            part
            async for part in answering.stream_answer(
                run, provider=EngineeringProvider(), retriever=retriever
            )
        ]

    events = asyncio.run(collect())
    with transaction() as db:
        saved = db.get(QueryRunRow, run.id)
        read_query(saved)
    return saved, events


def test_real_target_ask_bge_trace_pdf_api_and_replay(ready, monkeypatch):
    workspace, _, _ = ready
    monkeypatch.setattr(answering, "DeepSeekProvider", EngineeringProvider)
    token = "original-c3-test-authorization-only"
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": uuid4().hex}
    with TestClient(create_app(token, workspace)) as client:
        response = client.post("/v1/queries", json=body(ready).model_dump(mode="json"), headers=headers)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert events[-1]["type"] == "final", events[-1]
        assert any(e["type"] == "delta" and e["provisional"] for e in events)
        answer = events[-1]["answer"]
        row = client.get("/v1/runs/" + answer["run_id"], headers=headers).json()
        assert row["trace_schema_revision"] == "structural-trace-v1"
        pool = [c for c in row["candidates"] if c["pool_reason"] == "top20"]
        assert pool and all(c["bge"] and c["bge"]["pair_tokens"] <= 512 for c in pool)
        assert all(c["candidate_id"] not in c["evidence_ids"] for c in pool)
        assert {hit["branch"] for c in pool for hit in c["retrieval"]} == {"dense", "bm25"}
        pack = row["evidence_pack"]
        assert pack["serialized_chars"] <= 6400 and pack["serialized_tokens"] <= 2048
        for citation in answer["citations"]:
            resolved = client.get(
                "/v1/evidence/" + citation["evidence_id"],
                params={"run_id": answer["run_id"]},
                headers=headers,
            )
            assert resolved.status_code == 200 and resolved.json()["span"] == citation["span"]
            assert client.get(citation["content_url"], headers=headers).content.startswith(b"%PDF-")
        before = EngineeringProvider.calls
        replay = client.post("/v1/queries", json=body(ready).model_dump(mode="json"), headers=headers)
        assert '"type":"final"' in replay.text and EngineeringProvider.calls == before


def test_transient_bge_only_degrades_and_protocol_fails_closed(ready):
    workspace, _, _ = ready

    class Fault(ModelGateway):
        def structural_rerank(self, question, texts):
            raise GatewayError("model_http_503")

    run = answering.begin_query(workspace, body(ready), uuid4().hex)
    saved, _ = consume(run, Fault())
    assert saved.status == "COMPLETED"
    assert saved.evidence_pack["degraded"] == "degraded_reranker_unavailable"
    assert all(s["origin"] == "seed" for s in saved.evidence_pack["spans"])
    assert all(c["bge"] is None for c in saved.candidates)

    class Invalid(ModelGateway):
        def structural_rerank(self, question, texts):
            raise ValueError("reranker_identity_mismatch")

    before = EngineeringProvider.calls
    run = answering.begin_query(workspace, body(ready), uuid4().hex)
    saved, _ = consume(run, Invalid())
    assert saved.status == "FAILED" and saved.error_code == "reranker_identity_mismatch"
    assert saved.evidence_pack is None and EngineeringProvider.calls == before


def test_no_candidates_refuses_without_generation_and_branch_failure_is_not_partial(ready):
    workspace, _, _ = ready
    before = EngineeringProvider.calls
    run = answering.begin_query(workspace, body(ready), uuid4().hex)
    saved, _ = consume(run, query=lambda *args: [])
    assert saved.result["text"] == answering.REFUSAL and EngineeringProvider.calls == before
    assert saved.evidence_pack["source_coverage"]["selected"] == []

    def timeout(*args):
        raise TimeoutError("qdrant_stage_timeout")

    run = answering.begin_query(workspace, body(ready), uuid4().hex)
    saved, _ = consume(run, query=timeout)
    assert saved.status == "FAILED" and EngineeringProvider.calls == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit_kind", "legacy_span"),
        ("artifact_id", None),
        ("index_profile_hash", "0" * 64),
        ("embedding_identity", {}),
    ],
)
def test_missing_or_mixed_binding_rejected(ready, field, value, monkeypatch):
    workspace, _, result = ready
    with transaction() as db:
        index = db.get(IndexRow, db.get(VersionRow, result.version.id).index_collection)
        name = index.name
    # Published bindings are DB-immutable. Inject a malformed read at the adapter
    # boundary instead of weakening that trigger or mutating accepted data.
    get = Session.get

    def faulty_read(session, entity, identity, **kwargs):
        row = get(session, entity, identity, **kwargs)
        if entity is IndexRow and identity == name:
            return SimpleNamespace(**{**vars(row), field: value})
        return row

    monkeypatch.setattr(Session, "get", faulty_read)
    with pytest.raises(HTTPException) as err:
        answering.begin_query(workspace, body(ready), uuid4().hex)
    assert err.value.status_code == 409 and err.value.detail == "structure_not_ready"


def test_scope_and_real_query_token_rejection(ready):
    workspace, _, _ = ready
    with pytest.raises(HTTPException) as err:
        answering.begin_query(workspace, body(ready, document_ids=[uuid4()]), uuid4().hex)
    assert err.value.status_code == 404
    request = body(ready).model_copy(update={"question": "界" * 512})
    with pytest.raises(HTTPException) as err:
        answering.begin_query(workspace, request, uuid4().hex)
    assert err.value.status_code == 422
    with pytest.raises(ValueError, match="reranker_token_limit"):
        ModelGateway().structural_rerank("Original token limit fixture?", ["界" * 321])


def test_stale_target_fence_cannot_save_pack_or_final(ready):
    workspace, _, _ = ready
    run = answering.begin_query(workspace, body(ready), uuid4().hex)
    with transaction() as db:
        row = db.get(QueryRunRow, run.id)
        row.fence += 1
    with pytest.raises(ValueError, match="run_no_longer_active"):
        answering.save_trace(run.id, [], run.owner, run.fence)
    answering.failed(run.id, "fixture_complete", False)
