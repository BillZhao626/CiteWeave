"""Real UUID-isolated PG; original PDF spans, fake selector/proxy/answers only."""

import pytest
import test_conversation_postgres as pg
from sqlalchemy import func, select
from test_v02_dev_execution import ROOT

from citeweave.conversation_models import ConversationAcceptanceRow, ConversationRunRow
from citeweave.db import transaction
from citeweave.domain import (
    ChildSpanRow,
    ChunkRow,
    DocumentRow,
    IndexRow,
    KnowledgeBaseRow,
    RetrievalChildRow,
    StructureArtifactRow,
    StructureNodeRow,
    VersionRow,
)
from citeweave.evaluation.dev_dataset import identity, load_dev
from citeweave.evaluation.dev_execution import execute_l1
from citeweave.evaluation.dev_fixtures import FixtureRepository
from citeweave.evaluation.dev_postgres import PgBackend, require_isolated
from citeweave.tokenization import TOKENIZERS

isolated_pg = pg.isolated_pg
pytestmark = pg.pytestmark


@pytest.fixture(scope="module")
def original_sources():
    require_isolated()
    data, _ = load_dev(ROOT)
    repo = FixtureRepository(data)
    with transaction() as db:
        db.add(
            KnowledgeBaseRow(
                id=repo.kb,
                workspace_id=repo.workspace,
                name="Original DEV L1 proposals",
                key=str(repo.kb),
                fingerprint="0" * 64,
            )
        )
        db.flush()
        for s in data.sources:
            b = repo.bindings[str(s.version_id)]
            db.add(DocumentRow(id=s.document_id, kb_id=repo.kb, title=s.id, active_version_id=s.version_id))
            db.flush()
            db.add(
                VersionRow(
                    id=s.version_id,
                    document_id=s.document_id,
                    kb_id=repo.kb,
                    sequence=1,
                    filename=b.filename,
                    license="MIT original AI-assisted",
                    source_sha256=s.pdf_sha256,
                    blob_key=s.pdf_sha256,
                    status="READY",
                    profile=repo.profile,
                    key=str(s.version_id),
                    fingerprint=s.canonical_sha256,
                    index_collection=b.index_name,
                )
            )
            db.flush()
            child = repo.children[str(identity(s.id + ":child"))]
            atom = repo.atoms[child["span_ids"][0]]
            db.add(ChunkRow(**vars(atom)))
            db.add(
                StructureArtifactRow(
                    id=child["row"].artifact_id,
                    version_id=s.version_id,
                    parser_revision=repo.profile["parser_revision"],
                    profile_hash=b.index_profile_hash,
                    profile=repo.profile,
                    canonical_sha=b.canonical_sha,
                    tree_hash=b.tree_hash,
                    membership_hash=b.membership_hash,
                    tokenizers=TOKENIZERS,
                    state="DRAFT",
                )
            )
            db.flush()
            parent = child["parent"]
            db.add(
                StructureNodeRow(
                    id=parent.id,
                    artifact_id=child["row"].artifact_id,
                    parent_node_id=None,
                    kind="section",
                    number=None,
                    title=s.id,
                    heading_ids=[],
                    content_ids=parent.content_ids,
                    reading_order=0,
                    page_start=0,
                    page_end=0,
                    confidence="FALLBACK_PAGE",
                    reasons=[],
                    details={},
                )
            )
            from citeweave.retrieval import BM25Encoder

            bm25 = vars(BM25Encoder.fit([s.text]))
            db.add(
                IndexRow(
                    name=b.index_name,
                    workspace_id=repo.workspace,
                    version_id=s.version_id,
                    state="PUBLISHED",
                    unit_kind="structural_child",
                    artifact_id=child["row"].artifact_id,
                    index_profile_hash=b.index_profile_hash,
                    embedding_identity=b.embedding_identity,
                    bm25=bm25,
                    bm25_hash=b.bm25_hash,
                )
            )
            db.flush()
            db.add(RetrievalChildRow(**vars(child["row"]), tokenizers=TOKENIZERS, details={}))
            db.flush()
            db.add(
                ChildSpanRow(
                    child_id=child["row"].id, evidence_id=atom.id, version_id=s.version_id, position=0
                )
            )
            db.flush()
            db.get(StructureArtifactRow, child["row"].artifact_id).state = "PUBLISHED"
    return repo


def test_real_admission_acceptance_and_same_key_recovery_do_not_regenerate(original_sources):
    first = execute_l1(ROOT, "D2.V1", "cp-ab0-v1", retriever=original_sources, backend_factory=PgBackend)
    assert first["status"] == "COMPLETED", first.get("error_code")
    assert first["acceptance"]["durable"] and first["acceptance"]["accepted_id"]
    again = execute_l1(ROOT, "D2.V1", "cp-ab0-v1", retriever=original_sources, backend_factory=PgBackend)
    assert again["status"] == "RECOVERED" and not again["calls"]
    assert first["run_id"] == again["run_id"] and first["acceptance"] == again["acceptance"]
    from uuid import UUID

    with transaction() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ConversationAcceptanceRow)
                .where(ConversationAcceptanceRow.run_id == UUID(first["run_id"]))
            )
            == 1
        )


@pytest.mark.parametrize("config", ["cp-r-v1", "cp-a-v1"])
def test_r_a_real_pg_raw_reads_never_include_old_correction(original_sources, config):
    result = execute_l1(ROOT, "D3.V2", config, retriever=original_sources, backend_factory=PgBackend)
    assert result["error_code"] == "incomplete_group" and not result["calls"]
    assert result["acceptance"] is None and result["history"]["round_trips"] <= 8
    from uuid import UUID

    with transaction() as db:
        rows = list(
            db.scalars(
                select(ConversationRunRow)
                .where(ConversationRunRow.conversation_id == UUID(result["conversation_id"]))
                .order_by(ConversationRunRow.fence)
            )
        )
        old = db.scalar(
            select(ConversationAcceptanceRow).where(ConversationAcceptanceRow.run_id == rows[0].id)
        )
        assert old.id not in {UUID(r["acceptance_id"]) for r in result["raw_fetches"]}
        assert rows[-1].status == "FAILED"


def test_ab0_real_pg_b_recovers_atomic_group_and_commits(original_sources):
    result = execute_l1(ROOT, "D3.V2", "cp-ab0-v1", retriever=original_sources, backend_factory=PgBackend)
    assert result["status"] == "COMPLETED", result.get("error_code")
    assert result["acceptance"]["durable"]
    assert len(result["history"]["selected"][0]["sources"]) == 2
    assert "B" in result["history"]["selected"][0]["origins"]


def test_v0_delegates_existing_single_turn_execution_and_reads_durable_result(original_sources):
    import asyncio
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from citeweave.domain import QueryRunRow
    from citeweave.evaluation.dev_v0 import execute_v0

    data, _ = load_dev(ROOT)
    view = next(v for v in data.views if v.id == "D2.V1")
    from citeweave.conversation_contract import Scope

    scope = Scope(kb_id=original_sources.kb, version_ids=(identity("D2.manual:version:1"),))
    material = original_sources.retrieve(original_sources.workspace, scope, view.question)
    stamp = datetime.now(timezone.utc)
    with transaction() as db:
        row = QueryRunRow(
            id=uuid4(),
            workspace_id=original_sources.workspace,
            kb_id=scope.kb_id,
            key="v0-seeded-l1",
            fingerprint="0" * 64,
            question=view.question,
            trace_schema_revision="structural-trace-v1",
            structural_snapshot=material.snapshot.model_dump(mode="json"),
            versions=[str(v) for v in scope.version_ids],
            index_bindings={b.version_id: b.index_name for b in material.snapshot.bindings},
            runtime_config={"query_profile": "telecom-structural-v1", "prompt_identity": "answer-telecom-v1"},
            created_at=stamp,
            absolute_deadline=stamp + timedelta(seconds=45),
            owner=uuid4(),
            fence=1,
            runtime_policy="explicit_fake_l1_seed_no_paid_admission",
        )
        db.add(row)
        db.flush()

    class Retriever:
        pack = material.pack
        binding_remaining = 30

        def retrieve(self, question, versions):
            assert question == view.question and versions == [str(v) for v in scope.version_ids]
            return [original_sources.atoms[s.evidence_id] for s in self.pack.spans], []

    class Provider:
        def __init__(self):
            self.messages = []

        async def stream(self, messages):
            self.messages.append(messages)
            yield {"text": material.citations[0].span.quote + " [E1]"}

    provider = Provider()
    receipt = asyncio.run(execute_v0(row, provider=provider, retriever=Retriever()))
    assert receipt["terminal"]["type"] == "final" and len(provider.messages) == 1
    assert receipt["conversation_id"] is None and receipt["turn_id"] is None
    with transaction() as db:
        stored = db.get(QueryRunRow, row.id)
        assert stored.status == "COMPLETED" and stored.evidence_pack == material.pack.model_dump(mode="json")
        assert stored.result == receipt["terminal"]["answer"]


def test_closed_loop_real_pg_commits_clarification_then_resolves_head(original_sources):
    from uuid import UUID

    from citeweave import conversations as core
    from citeweave.evaluation.dev_execution import closed_loop_l1

    result = closed_loop_l1(ROOT, "cp-ab0-v1", retriever=original_sources, backend_factory=PgBackend)
    first, second = result["receipts"]
    assert first["acceptance"]["durable"] and second["acceptance"]["durable"]
    assert first["conversation_id"] == second["conversation_id"]
    truth = core.read_run_id(
        original_sources.workspace, UUID(second["conversation_id"]), UUID(second["run_id"])
    )
    assert truth.conversation.head.id == UUID(second["acceptance"]["accepted_id"])
    assert not any(e.active and e.item.kind == "ambiguity" for e in truth.accepted.state.entries)


@pytest.mark.parametrize("vid", ["D1.V2", "D3.V1"])
def test_pg_state_intent_no_old_raw_read_and_no_product_publication(original_sources, vid):
    from uuid import UUID

    result = execute_l1(ROOT, vid, "cp-a-v1", retriever=original_sources, backend_factory=PgBackend)
    assert result["status"] == "COMPLETED", result.get("error_code")
    assert result["acceptance"] is None and result["evaluation_output"]["kind"] == "documentary_answer"
    old = result["prefix_receipts"][0]["acceptance_id"]
    assert old not in {s["acceptance_id"] for s in result["raw_fetches"]}
    assert not result["calls"][-1]["context"]["history"]
    assert result["interpretation"]["topic_relation"] == "return"
    assert result["calls"][-1]["context"]["working_state"][0]["active"]
    with transaction() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ConversationAcceptanceRow)
                .where(ConversationAcceptanceRow.run_id == UUID(result["run_id"]))
            )
            == 0
        )
        assert db.get(ConversationRunRow, UUID(result["run_id"])).status == "FAILED"


def test_pg_d1_return_preserves_active_ferrule_state_and_b_recovery(original_sources):
    from uuid import UUID

    from citeweave import conversations as core

    result = execute_l1(ROOT, "D1.V2", "cp-ab0-v1", retriever=original_sources, backend_factory=PgBackend)
    assert result["status"] == "COMPLETED", result.get("error_code")
    assert result["interpretation"]["topic_relation"] == "return"
    assert result["acceptance"]["durable"]
    old = result["prefix_receipts"][0]["acceptance_id"]
    assert old in {r["acceptance_id"] for r in result["raw_fetches"]}
    assert any("B" in g["origins"] for g in result["history"]["selected"])
    truth = core.read_run_id(
        original_sources.workspace, UUID(result["conversation_id"]), UUID(result["run_id"])
    )
    assert truth.accepted.state.delta.topic_relation == "return"
    assert any(e.active and e.item.value == "Ferrule-Q" for e in truth.accepted.state.entries)
