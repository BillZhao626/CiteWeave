"""Existing structural RAG adapter and durable documentary acceptance checks."""

from sqlalchemy import select

from citeweave.answering import citation_for
from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_evidence import CurrentEvidence, assemble, make_result
from citeweave.db import transaction
from citeweave.domain import VersionRow
from citeweave.schemas import QueryCreate
from citeweave.structural_repository import StructuralRepository, capture
from citeweave.structural_retrieval import StructuralRetriever, qdrant_branch


class StructuralEvidenceRetriever:
    """No default model: local tests explicitly inject deterministic adapters.

    Reuses capture, Dense/BM25/RRF/BGE, selection and citation binding unchanged.
    No QueryRun is fabricated and no v0.1 final is published before acceptance.
    """

    def __init__(self, *, model, branch_query=qdrant_branch):
        self.model = model
        self.branch_query = branch_query

    def retrieve(self, workspace, scope, query):
        from citeweave.conversations import _scope

        # Preserve the existing query admission length/token contracts.
        body = QueryCreate(kb_id=scope.kb_id, question=query, profile="telecom-structural-v1")
        tokens = self.model.query_tokens(query)
        with transaction() as db:
            _scope(db, workspace, scope, current=True)
            snapshot = capture(db, workspace, body, list(scope.version_ids), tokens)
        retriever = StructuralRetriever(snapshot, model=self.model, branch_query=self.branch_query)
        chunks, _ = retriever.retrieve(query, [str(v) for v in scope.version_ids])
        if retriever.pack is None:
            raise CoreConflict("structural_evidence_pack_required")
        return CurrentEvidence(
            snapshot=snapshot,
            pack=retriever.pack,
            citations=tuple(citation_for(c, f"E{i}") for i, c in enumerate(chunks, 1)),
        )


def validate_durable_result(db, workspace, run_id, context, decision, result):
    # The transaction already holds current scope/authorization locks. Re-resolve
    # ALL pack spans, not just cited labels, against immutable stored atoms/builds.
    snapshot = result.snapshot
    scope = context.request.scope
    if (
        snapshot.workspace_id != str(workspace)
        or snapshot.kb_id != str(scope.kb_id)
        or {b.version_id for b in snapshot.bindings} != {str(v) for v in scope.version_ids}
        or len(snapshot.bindings) != len(scope.version_ids)
        or len(result.evidence_pack.spans) > 96
        or len(result.evidence_pack.seed_child_ids) > 6
    ):
        raise CoreConflict("documentary_scope_or_pack_conflict")
    versions = {
        str(v.id): v
        for v in db.scalars(select(VersionRow).where(VersionRow.id.in_(context.request.scope.version_ids)))
    }
    for binding in snapshot.bindings:
        version = versions.get(binding.version_id)
        if not version or str(version.document_id) != binding.document_id:
            raise CoreConflict("documentary_document_identity_conflict")
    repository = StructuralRepository(snapshot)
    repository.builds()
    atoms = repository.atoms({s.evidence_id for s in result.evidence_pack.spans})
    material = CurrentEvidence(
        snapshot=snapshot,
        pack=result.evidence_pack,
        citations=tuple(citation_for(atoms[s.evidence_id], s.label) for s in result.evidence_pack.spans),
    )
    # Verify lineage against the same immutable artifact, without selecting or
    # reranking again. Pack contents cannot point to an unrelated frozen span.
    children = repository.children(set(result.evidence_pack.seed_child_ids))
    if any(
        s.seed_child_id not in children
        or str(children[s.seed_child_id]["row"].parent_node_id) != s.parent_id
        or str(children[s.seed_child_id]["row"].version_id) != s.version_id
        or s.evidence_id
        not in (
            children[s.seed_child_id]["parent"].content_ids + children[s.seed_child_id]["parent"].heading_ids
        )
        for s in result.evidence_pack.spans
    ):
        raise CoreConflict("documentary_pack_lineage_conflict")
    # max_input_bytes is a local assembly bound, not durable provider accounting.
    # Reconstruct identity without imposing a newly chosen product token limit.
    assembled = assemble(workspace, run_id, context, decision, material, max_input_bytes=2**63 - 1)
    if make_result(assembled, result.answer) != result:
        raise CoreConflict("documentary_result_conflict")
