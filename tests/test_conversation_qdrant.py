"""Opt-in actual Qdrant + local E5/BGE; isolated PG and disposable collection.

Never invokes an external model. Original fixture, physical identity assertions.
"""

import json
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient
from qdrant_client import models as qm
from test_conversation_postgres import execution, history_accept, metadata
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark

from citeweave import conversations as core
from citeweave.conversation_contract import CoreConflict, ResolvedSignals, StateSnapshot
from citeweave.conversation_evidence import assemble, make_result
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_history import HistoryQuery
from citeweave.conversation_history_pg import RuntimeHistoryRead, read_history
from citeweave.conversation_interpretation import (
    IntentFact,
    InterpretationDraft,
    InterpretationInput,
    RetrievalRewrite,
    interpret,
)
from citeweave.conversation_runtime import generation_messages
from citeweave.costs import maximum_cost
from citeweave.db import transaction
from citeweave.domain import DocumentRow, VersionRow
from citeweave.llm import completion_payload
from citeweave.model_client import ModelGateway
from citeweave.provider_accounting import DeepSeekAccounting, serialize_request
from citeweave.retrieval import BM25Encoder
from citeweave.schemas import Answer
from citeweave.settings import ROOT, settings
from citeweave.tokenization import GatewayTokenizer


@pytest.fixture
def evidence_case(tmp_path, monkeypatch):
    from io import BytesIO

    from conversation_evidence_fixtures import Fixture
    from reportlab.pdfgen.canvas import Canvas

    from citeweave.blobs import LocalBlobStore
    from citeweave.conversation_contract import Admission

    workspace, scope = metadata()
    buffer = BytesIO()
    pdf = Canvas(buffer, pagesize=(600, 800), invariant=True)
    pdf.drawString(60, 680, "The receiver discards the damaged message.")
    pdf.save()
    monkeypatch.setattr(settings(), "blob_root", tmp_path / "blobs")
    key = LocalBlobStore(settings().blob_root).put(buffer.getvalue())
    with transaction() as db:
        version = db.get(VersionRow, scope.version_ids[0])
        version.source_sha256 = version.blob_key = key
        document = version.document_id
    fixture = Fixture(workspace, scope, document, source_sha256=key)
    fixture.child["row"].token_counts = GatewayTokenizer(ModelGateway()).count([fixture.atom.text])[0]
    fixture.persist()
    conversation = core.create(workspace, "original-qdrant-smoke")
    return (
        workspace,
        conversation.id,
        Admission(
            question="What does the receiver do with a damaged message?", scope=scope, expected_head=None
        ),
    ), fixture


@pytest.mark.parametrize("rewrite", [False, True])
def test_real_qdrant_scope_identity_and_smoke_payload(evidence_case, rewrite):
    sample, fixture = evidence_case
    model = ModelGateway()
    # Capture exactly the original/rewrite query entering the real local embedder.
    original_embed = model.embed
    seen = []

    def embed(texts, **kwargs):
        if kwargs.get("query"):
            seen.extend(texts)
        return original_embed(texts, **kwargs)

    model.embed = embed
    vector = model.embed([fixture.atom.text])[0]
    sparse = BM25Encoder(**fixture.bm25).document_vector(0)
    client = QdrantClient(url=settings().qdrant_url, check_compatibility=False, trust_env=False)
    name = fixture.binding.index_name
    assert name.startswith("synthetic-") and len(name) == 42
    created = False
    try:
        client.create_collection(
            name,
            vectors_config={"dense": qm.VectorParams(size=len(vector), distance=qm.Distance.COSINE)},
            sparse_vectors_config={"bm25": qm.SparseVectorParams()},
        )
        created = True
        payload = fixture.branch(fixture.binding, fixture.snapshot, "dense", vector, None)[0].payload
        vectors = {"dense": vector, "bm25": qm.SparseVector(indices=sparse.indices, values=sparse.values)}
        client.upsert(
            name,
            points=[
                qm.PointStruct(id=str(fixture.child_id), vector=vectors, payload=payload),
                qm.PointStruct(
                    id=str(uuid4()), vector=vectors, payload=dict(payload, version_id=str(uuid4()))
                ),
                qm.PointStruct(
                    id=str(uuid4()), vector=vectors, payload=dict(payload, workspace_id=str(uuid4()))
                ),
            ],
            wait=True,
        )
        question = "What does the receiver do with a damaged message?"
        previous = None
        draft = InterpretationDraft(topic_relation="continue", dependency="none")
        if rewrite:
            previous = history_accept(
                sample, question="the receiver", signals=ResolvedSignals(entities=("the receiver",))
            )
            question = "What does it do with a damaged message?"
            fact = IntentFact(kind="entity", value="the receiver", source=previous.state.source)
            draft = InterpretationDraft(
                topic_relation="continue",
                dependency="required",
                facts=(fact,),
                rewrite=RetrievalRewrite(text=question + "\nthe receiver", scope=sample[2].scope),
            )
        body = sample[2].model_copy(
            update={"question": question, "expected_head": previous.id if previous else None}
        )
        run = core.admit(*sample[:2], uuid4().hex, body, execution())
        history = read_history(
            *sample[:2],
            HistoryQuery(
                scope=body.scope,
                expected_head=body.expected_head,
                explicit=(previous.state.source,) if previous else (),
            ),
            permit=RuntimeHistoryRead(run=run, scan_limit=512, statement_ms=1000),
        )
        context = InterpretationInput(
            conversation_id=sample[1], turn_id=run.turn_id, request=body, previous=previous, history=history
        )
        decision = interpret(context, draft=draft)
        retriever = StructuralEvidenceRetriever(model=model)
        material = retriever.retrieve(sample[0], body.scope, decision.selected_query)
        assert seen == [decision.selected_query]
        assert material.citations == (fixture.citation,)
        assert [s.evidence_id for s in material.pack.spans] == [str(fixture.atom.id)]
        assembled = assemble(sample[0], run.id, context, decision, material, max_input_bytes=131072)
        # Synthetic output is solely for physical validation/atomic Acceptance.
        answer = Answer(
            run_id=run.id,
            text=fixture.atom.text + " [E1]",
            citations=[fixture.citation],
            prompt_version="SYNTHETIC-PROVIDER-NOT-CALLED",
        )
        result = make_result(assembled, answer)
        core.accept(
            sample[0],
            run.conversation_id,
            run.turn_id,
            run.id,
            run.owner,
            run.fence,
            result,
            StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=run.expected_head),
            delta=decision.delta,
            interpretation=(context, draft),
        )
        assert core.read_run_id(*sample[:2], run.id).accepted.result.answer.citations == [fixture.citation]
        if not rewrite:
            tokenizer = ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
            accounting = DeepSeekAccounting(tokenizer)
            prompt = (ROOT / "prompts" / f"{settings().telecom_answer_prompt}.txt").read_text(
                encoding="utf-8"
            )
            payload = completion_payload(generation_messages(assembled, prompt), settings().deepseek_model)
            measured = accounting.measure(payload)
            receipt = dict(
                question=question,
                workspace_id=str(sample[0]),
                conversation_id=str(sample[1]),
                scope=body.scope.model_dump(mode="json"),
                snapshot=material.snapshot.model_dump(mode="json"),
                evidence=material.model_dump(mode="json"),
                measurement=measured,
                proposed_peak_yuan=str(maximum_cost(measured["input_tokens"], payload["max_tokens"])),
                resource_status="isolated_fixture_cleaned_after_test",
                provider_calls=0,
            )
            target = ROOT / ".runtime/provider-accounting"
            (target / "smoke-request.json").write_bytes(serialize_request(payload))
            (target / "smoke-measurement.json").write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        # A stale version never reaches the real retriever even if Qdrant retains it.
        with transaction() as db:
            db.get(DocumentRow, fixture.document).active_version_id = None
        with pytest.raises(CoreConflict, match="scope_changed"):
            retriever.retrieve(sample[0], body.scope, question)
    finally:
        if created:
            client.delete_collection(name)
        client.close()
