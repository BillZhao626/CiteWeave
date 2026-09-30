"""Original tiny immutable structure; all model/Qdrant responses are synthetic."""

from types import SimpleNamespace as NS
from uuid import uuid4

from citeweave.conversation_evidence import CurrentEvidence
from citeweave.document_profiles import content_hash, document_profile
from citeweave.embeddings import E5
from citeweave.evidence import Block, Box, Scope, bind_span, digest
from citeweave.evidence_selection import select_evidence
from citeweave.index import child_payload
from citeweave.query_evidence import StructuralBinding, StructuralCandidate, StructuralSnapshot
from citeweave.retrieval import BM25Encoder
from citeweave.schemas import Answer, Citation
from citeweave.structural_contract import QUERY_CONTRACT
from citeweave.tokenization import TOKENIZERS


def require_isolated_database(connection):
    from uuid import UUID

    from sqlalchemy import text

    name = connection.scalar(text("SELECT current_database()"))
    prefix = "cw_conversation_test_"
    if not name.startswith(prefix):
        raise RuntimeError("isolated_context_test_database_required")
    suffix = name[len(prefix) :]
    try:
        valid = UUID(suffix).hex == suffix
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError("isolated_context_test_database_required")


class FakeModel:
    def query_tokens(self, question):
        return dict(contract=QUERY_CONTRACT, tokenizers=TOKENIZERS, e5_input=12, bge_query=8)

    def embed(self, texts, **kwargs):
        return [[1.0, 0.0] for _ in texts]

    def structural_rerank(self, question, texts):
        return dict(
            self.query_tokens(question),
            scores=[0.5] * len(texts),
            body_tokens=[20] * len(texts),
            pair_tokens=[32] * len(texts),
            queue_ms=0,
            inference_ms=0,
        )

    def call(self, path, body):
        assert path == "/context-tokenize"
        return dict(
            contract=QUERY_CONTRACT,
            tokenizers=TOKENIZERS,
            hashes=[digest(t) for t in body["texts"]],
            counts=[20] * len(body["texts"]),
        )

    def count(self, texts):
        return [{"bge": 20} for _ in texts]


class FakeGenerator:
    def __init__(self):
        self.inputs = []

    def generate(self, context):
        self.inputs.append(context)
        citation = context.evidence.citations[0]
        return Answer(
            run_id=context.run_id,
            text=citation.span.quote + " [E1]",
            citations=[citation],
            prompt_version="synthetic-only",
            estimated_yuan=0,
        )


class Fixture:
    def __init__(self, workspace, scope, document=None):
        self.workspace, self.scope = workspace, scope
        self.document = document or uuid4()
        self.artifact, self.parent_id, self.child_id = uuid4(), uuid4(), uuid4()
        self.version = scope.version_ids[0]
        self.profile = document_profile("telecom-protocol-pdf-v1")
        block = Block(
            scope=Scope(workspace_id=workspace, kb_id=scope.kb_id, revision_id=self.version),
            source_sha256="0" * 64,
            block_id="original-synthetic",
            text="The receiver discards the damaged message.",
            locator_kind="pdf_bbox",
            boxes=(Box(page_index=0, left=0.1, top=0.1, right=0.9, bottom=0.2),),
        )
        span = bind_span(block, 0, len(block.text), block.text)
        self.atom = NS(
            id=span.id,
            version_id=self.version,
            text=span.quote,
            block=block.model_dump(mode="json"),
            evidence=span.model_dump(mode="json"),
        )
        self.ids = [str(span.id)]
        self.bm25 = vars(BM25Encoder.fit([block.text]))
        self.binding = StructuralBinding(
            document_id=str(self.document),
            version_id=str(self.version),
            filename="synthetic.pdf",
            source_sha256="0" * 64,
            artifact_id=str(self.artifact),
            canonical_sha="1" * 64,
            tree_hash="2" * 64,
            membership_hash="3" * 64,
            index_name="synthetic-" + uuid4().hex,
            index_profile_hash=content_hash(self.profile),
            bm25_hash=content_hash(self.bm25),
            embedding_identity=E5,
            tokenizers=TOKENIZERS,
        )
        self.snapshot = StructuralSnapshot(
            workspace_id=str(workspace),
            kb_id=str(scope.kb_id),
            evidence_mode="single",
            requested_documents=[],
            bindings=[self.binding],
            query_tokens=FakeModel().query_tokens("q"),
        )
        self.parent = NS(id=self.parent_id, content_ids=self.ids, heading_ids=[], confidence="FALLBACK_PAGE")
        self.child = dict(
            row=NS(
                id=self.child_id,
                version_id=self.version,
                artifact_id=self.artifact,
                parent_node_id=self.parent_id,
                ordinal=0,
                retrieval_text=block.text,
                text_hash=digest(block.text),
                membership_hash=content_hash(self.ids),
                token_counts={"bge": 20},
            ),
            parent=self.parent,
            span_ids=self.ids,
            binding=self.binding,
            section_path=[],
        )
        self.repository = NS(
            snapshot=self.snapshot,
            builds=lambda: {str(self.version): self.bm25},
            children=lambda ids: {str(self.child_id): self.child} if ids else {},
            atoms=lambda ids: {str(span.id): self.atom} if ids else {},
            neighbors=lambda seeds: {},
        )
        self.citation = Citation(
            label="E1",
            evidence_id=span.id,
            document_version_id=self.version,
            filename="synthetic.pdf",
            span=span,
            content_url=f"/v1/document-versions/{self.version}/content",
        )
        self.calls = []

    def branch(self, binding, snapshot, branch, query, cancelled):
        payload = child_payload(
            dict(
                id=str(self.child_id),
                artifact_id=str(self.artifact),
                version_id=str(self.version),
                span_ids=self.ids,
                membership_hash=content_hash(self.ids),
                text_hash=self.child["row"].text_hash,
                parent_node_id=str(self.parent_id),
            ),
            {
                k: getattr(binding, k)
                for k in ("unit_kind", "artifact_id", "index_profile_hash", "embedding_identity", "bm25_hash")
            },
            dict(workspace_id=snapshot.workspace_id, kb_id=snapshot.kb_id, version_id=str(self.version)),
        )
        return [NS(id=str(self.child_id), score=1.0, payload=payload)]

    def material(self, empty=False):
        identity = str(self.child_id)
        candidate = StructuralCandidate(
            candidate_id=identity,
            child_id=identity,
            document_id=str(self.document),
            version_id=str(self.version),
            artifact_id=str(self.artifact),
            parent_id=str(self.parent_id),
            section_path=[],
            evidence_ids=self.ids,
            retrieval=[],
            rrf_rank=1,
            rrf_score=0.1,
            pool_reason="top20",
        )
        _, pack = select_evidence(
            [] if empty else [identity],
            {} if empty else {identity: candidate},
            {} if empty else {identity: self.child},
            self.repository,
            FakeModel(),
        )
        return CurrentEvidence(snapshot=self.snapshot, pack=pack, citations=() if empty else (self.citation,))

    def retrieve(self, workspace, scope, query):
        self.calls.append((workspace, scope, query))
        return self.material()

    def persist(self):
        from citeweave.db import transaction
        from citeweave.domain import (
            ChildSpanRow,
            ChunkRow,
            IndexRow,
            RetrievalChildRow,
            StructureArtifactRow,
            StructureNodeRow,
            VersionRow,
        )

        with transaction() as db:
            require_isolated_database(db.connection())
            version = db.get(VersionRow, self.version)
            version.profile = self.profile
            version.index_collection = self.binding.index_name
            db.add(ChunkRow(**vars(self.atom)))
            db.add(
                StructureArtifactRow(
                    id=self.artifact,
                    version_id=self.version,
                    parser_revision=self.profile["parser_revision"],
                    profile_hash=content_hash(self.profile),
                    profile=self.profile,
                    canonical_sha=self.binding.canonical_sha,
                    tree_hash=self.binding.tree_hash,
                    membership_hash=self.binding.membership_hash,
                    tokenizers=TOKENIZERS,
                    state="DRAFT",
                )
            )
            db.flush()
            db.add(
                StructureNodeRow(
                    id=self.parent_id,
                    artifact_id=self.artifact,
                    parent_node_id=None,
                    kind="section",
                    number=None,
                    title="Original fixture",
                    heading_ids=[],
                    content_ids=self.ids,
                    reading_order=0,
                    page_start=0,
                    page_end=0,
                    confidence="FALLBACK_PAGE",
                    reasons=[],
                    details={},
                )
            )
            db.add(
                IndexRow(
                    name=self.binding.index_name,
                    workspace_id=self.workspace,
                    version_id=self.version,
                    state="PUBLISHED",
                    unit_kind="structural_child",
                    artifact_id=self.artifact,
                    index_profile_hash=self.binding.index_profile_hash,
                    embedding_identity=E5,
                    bm25=self.bm25,
                    bm25_hash=self.binding.bm25_hash,
                )
            )
            db.flush()
            db.add(RetrievalChildRow(**vars(self.child["row"]), tokenizers=TOKENIZERS, details={}))
            db.flush()
            db.add(
                ChildSpanRow(
                    child_id=self.child_id, evidence_id=self.atom.id, version_id=self.version, position=0
                )
            )
            db.flush()
            db.get(StructureArtifactRow, self.artifact).state = "PUBLISHED"
