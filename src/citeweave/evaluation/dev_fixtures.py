"""Explicit deterministic L1 fixtures, never production retrieval or model quality.

Reuse the real structural selector/typed spans. Fake proxy counts and branch ranks
do not establish real E5/BGE/Qdrant ingestion; receipts identify this limitation.
"""

from types import SimpleNamespace as NS

from citeweave.conversation_evidence import CurrentEvidence
from citeweave.document_profiles import content_hash, document_profile
from citeweave.embeddings import E5
from citeweave.evaluation.dev_dataset import identity
from citeweave.evidence import Block, Box, bind_span
from citeweave.evidence import Scope as EvidenceScope
from citeweave.evidence_selection import select_evidence
from citeweave.query_evidence import StructuralBinding, StructuralCandidate, StructuralSnapshot
from citeweave.retrieval import BM25Encoder
from citeweave.schemas import Citation
from citeweave.structural_contract import QUERY_CONTRACT
from citeweave.tokenization import TOKENIZERS


class FixtureProxy:
    def count(self, texts):
        return [{"bge": 20} for _ in texts]


class FixtureRepository:
    kind = "L1_FAKE_RETRIEVAL_FAKE_BGE_NO_QDRANT"

    def __init__(self, data):
        self.data = data
        self.workspace, self.kb = identity("workspace"), identity("kb")
        self.profile = document_profile("telecom-protocol-pdf-v1")
        self.atoms, self.children, self.bindings = {}, {}, {}
        for source in data.sources:
            version = source.version_id
            block = Block(
                scope=EvidenceScope(workspace_id=self.workspace, kb_id=self.kb, revision_id=version),
                source_sha256=source.pdf_sha256,
                block_id=source.id,
                text=source.text,
                locator_kind="pdf_bbox",
                boxes=(
                    Box(
                        page_index=0,
                        left=source.pdf_box[0],
                        top=source.pdf_box[1],
                        right=source.pdf_box[2],
                        bottom=source.pdf_box[3],
                    ),
                ),
            )
            span = bind_span(block, 0, len(source.text), source.text)
            self.atoms[str(span.id)] = NS(
                id=span.id,
                version_id=version,
                text=span.quote,
                block=block.model_dump(mode="json"),
                evidence=span.model_dump(mode="json"),
            )
            bm25 = vars(BM25Encoder.fit([source.text]))
            ids = [str(span.id)]
            binding = StructuralBinding(
                document_id=str(source.document_id),
                version_id=str(version),
                filename=source.id + ".pdf",
                source_sha256=source.pdf_sha256,
                artifact_id=str(identity(source.id + ":artifact")),
                canonical_sha=source.canonical_sha256,
                tree_hash=content_hash([source.id, ids]),
                membership_hash=content_hash(ids),
                index_name="dev-l1-" + version.hex,
                index_profile_hash=content_hash(self.profile),
                bm25_hash=content_hash(bm25),
                embedding_identity=E5,
                tokenizers=TOKENIZERS,
            )
            parent = NS(
                id=identity(source.id + ":parent"),
                content_ids=ids,
                heading_ids=[],
                confidence="FALLBACK_PAGE",
            )
            child_id = identity(source.id + ":child")
            self.bindings[str(version)] = binding
            self.children[str(child_id)] = dict(
                row=NS(
                    id=child_id,
                    version_id=version,
                    artifact_id=identity(source.id + ":artifact"),
                    parent_node_id=parent.id,
                    ordinal=0,
                    retrieval_text=source.text,
                    text_hash=source.canonical_sha256,
                    membership_hash=content_hash(ids),
                    token_counts={"bge": 20},
                ),
                parent=parent,
                span_ids=ids,
                binding=binding,
                section_path=[],
            )

    def retrieve(self, workspace, scope, query):
        if workspace != self.workspace or scope.kb_id != self.kb:
            raise ValueError("dev_fixture_scope_mismatch")
        bindings = [self.bindings[str(v)] for v in scope.version_ids]
        snapshot = StructuralSnapshot(
            workspace_id=str(workspace),
            kb_id=str(scope.kb_id),
            evidence_mode="single",
            requested_documents=[],
            bindings=bindings,
            query_tokens=dict(contract=QUERY_CONTRACT, tokenizers=TOKENIZERS, e5_input=12, bge_query=8),
        )
        repository = NS(
            snapshot=snapshot,
            atoms=lambda ids: {i: self.atoms[i] for i in ids if i in self.atoms},
            neighbors=lambda seeds: {},
        )
        chosen = {
            i: c
            for i, c in self.children.items()
            if c["binding"].version_id in {str(v) for v in scope.version_ids}
        }
        ordered = sorted(chosen)
        candidates = {
            i: StructuralCandidate(
                candidate_id=i,
                child_id=i,
                document_id=chosen[i]["binding"].document_id,
                version_id=chosen[i]["binding"].version_id,
                artifact_id=chosen[i]["binding"].artifact_id,
                parent_id=str(chosen[i]["parent"].id),
                section_path=[],
                evidence_ids=chosen[i]["span_ids"],
                retrieval=[],
                rrf_rank=n,
                rrf_score=1 / (60 + n),
                pool_reason="top20",
            )
            for n, i in enumerate(ordered, 1)
        }
        _, pack = select_evidence(ordered, candidates, chosen, repository, FixtureProxy())
        citations = []
        for p in pack.spans:
            from citeweave.evidence import EvidenceSpan

            span = EvidenceSpan.model_validate(self.atoms[p.evidence_id].evidence)
            b = self.bindings[p.version_id]
            citations.append(
                Citation(
                    label=p.label,
                    evidence_id=span.id,
                    document_version_id=span.scope.revision_id,
                    filename=b.filename,
                    span=span,
                    content_url=f"/v1/document-versions/{b.version_id}/content",
                )
            )
        return CurrentEvidence(snapshot=snapshot, pack=pack, citations=tuple(citations))
