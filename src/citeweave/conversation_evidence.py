"""Internal orchestration only: intent context and documentary authority stay typed.

There is no default generator, provider dispatch, prompt or production admission.
The explicit byte ceiling bounds local synthetic generation inputs only; complete
provider serialization/token accounting remains deferred and must gate real use.
"""

import json
from datetime import datetime, timezone
from typing import Literal, Protocol
from uuid import UUID

from citeweave.answering import REFUSAL, validate_citations
from citeweave.catalog import fingerprint
from citeweave.conversation_contract import (
    CoreConflict,
    DocumentaryResult,
    DocumentaryTrace,
    DurableDTO,
    HistoryRelation,
    RunView,
    Scope,
    SourceRef,
    StateEntry,
    StateSnapshot,
)
from citeweave.conversation_history import HistoryQuery, HistorySelection
from citeweave.conversation_interpretation import (
    InterpretationDraft,
    InterpretationInput,
    InterpretationResult,
    interpret,
)
from citeweave.query_evidence import EvidencePack, StructuralSnapshot
from citeweave.schemas import Answer, Citation
from citeweave.trace import bounded_stage


class IntentHistory(DurableDTO):
    authority: Literal["contextual_intent_not_evidence"] = "contextual_intent_not_evidence"
    source: SourceRef
    original_question: str
    relations: tuple[HistoryRelation, ...]


class CurrentEvidence(DurableDTO):
    snapshot: StructuralSnapshot
    pack: EvidencePack
    citations: tuple[Citation, ...]


class GenerationContext(DurableDTO):
    run_id: UUID
    original_question: str
    retrieval_query: str
    interpretation: InterpretationResult
    history: tuple[IntentHistory, ...]
    working_state: tuple[StateEntry, ...]
    evidence: CurrentEvidence


class DocumentaryRetriever(Protocol):
    def retrieve(self, workspace: UUID, scope: Scope, query: str) -> CurrentEvidence: ...


class AnswerGenerator(Protocol):
    def generate(self, context: GenerationContext) -> Answer: ...


def intent_context(context: InterpretationInput, decision: InterpretationResult):
    # Preserve whole selected source groups required by interpreted dependencies.
    # Correction-only sources are checked on commit, but not injected as intent.
    used = {f.source for f in decision.facts if f.source is not None}
    groups = [g for g in context.history.selected if any(s.ref in used for s in g.sources)]
    sources = {s.ref: s for g in groups for s in g.sources}
    history = tuple(
        IntentHistory(source=s.ref, original_question=s.request.question, relations=s.relations)
        for s in sources.values()
    )
    retired = set(decision.delta.deactivate) | {i for v in decision.delta.put for i in v.replaces}
    state_ids = {f.state_item_id for f in decision.facts if f.state_item_id is not None}
    state = tuple(
        e for e in context.history.state_projection if e.item.id in state_ids and e.item.id not in retired
    )
    return history, state


def validate_evidence(workspace: UUID, scope: Scope, material: CurrentEvidence):
    snapshot, pack, citations = material.snapshot, material.pack, material.citations
    bindings = {b.version_id: b for b in snapshot.bindings}
    if (
        snapshot.workspace_id != str(workspace)
        or snapshot.kb_id != str(scope.kb_id)
        or set(bindings) != {str(v) for v in scope.version_ids}
        or len(bindings) != len(snapshot.bindings)
        or not set(snapshot.requested_documents) <= {b.document_id for b in bindings.values()}
    ):
        raise CoreConflict("documentary_scope_conflict")
    if (
        len(pack.spans) != len(citations)
        or len({s.evidence_id for s in pack.spans}) != len(pack.spans)
        or len(pack.spans) > 96
        or pack.serialized_chars != len(pack.prompt_json)
        or len(pack.prompt_json) > 6400
        or not 0 <= pack.serialized_tokens <= 2048
        or pack.evidence_mode != snapshot.evidence_mode
    ):
        raise CoreConflict("documentary_pack_invalid")
    versions = list(dict.fromkeys(s.version_id for s in pack.spans))
    labels = {v: f"S{i}" for i, v in enumerate(versions, 1)}
    for i, (span, citation) in enumerate(zip(pack.spans, citations, strict=True), 1):
        binding = bindings.get(span.version_id)
        source = citation.span
        if (
            not binding
            or span.document_id != binding.document_id
            or span.label != f"E{i}"
            or citation.label != span.label
            or str(citation.evidence_id) != span.evidence_id
            or citation.evidence_id != source.id
            or str(citation.document_version_id) != span.version_id
            or source.scope.revision_id != citation.document_version_id
            or source.scope.workspace_id != workspace
            or source.scope.kb_id != scope.kb_id
            or source.source_sha256 != binding.source_sha256
            or citation.filename != binding.filename
            or citation.content_url != f"/v1/document-versions/{span.version_id}/content"
        ):
            raise CoreConflict("documentary_citation_identity_conflict")
    # Verify the exact evidence text/labels seen by generation; a typed pack alone
    # does not establish correspondence between prompt_json and immutable spans.
    expected = dict(
        sources=[dict(source=labels[v], title=bindings[v].filename, version=v) for v in versions],
        source_gaps=pack.source_coverage.missing,
        evidence=[
            dict(label=c.label, source=labels[str(c.document_version_id)], text=c.span.quote)
            for c in citations
        ],
    )
    if json.loads(pack.prompt_json) != expected:
        raise CoreConflict("documentary_pack_content_conflict")
    selected = list(dict.fromkeys(s.document_id for s in pack.spans))
    coverage = pack.source_coverage
    if (
        coverage.selected != selected
        or not set(coverage.requested + coverage.eligible) <= {b.document_id for b in bindings.values()}
        or coverage.missing != [d for d in coverage.requested if d not in selected]
        or coverage.coverage_unmet
        != (bool(coverage.missing) or pack.evidence_mode == "compare" and len(selected) < 2)
    ):
        raise CoreConflict("documentary_coverage_conflict")


def assemble(workspace, run_id, context, decision, evidence, *, max_input_bytes):
    if decision.mode == "CLARIFY" or not decision.selected_query:
        raise CoreConflict("documentary_query_required")
    validate_evidence(workspace, context.request.scope, evidence)
    history, state = intent_context(context, decision)
    assembled = GenerationContext(
        run_id=run_id,
        original_question=context.request.question,
        retrieval_query=decision.selected_query,
        interpretation=decision,
        history=history,
        working_state=state,
        evidence=evidence,
    )
    if max_input_bytes <= 0 or len(assembled.model_dump_json().encode("utf-8")) > max_input_bytes:
        raise CoreConflict("conversation_context_overflow")
    return assembled


def make_result(context: GenerationContext, answer: Answer) -> DocumentaryResult:
    answer = Answer.model_validate(answer.model_dump(mode="json"))
    if answer.run_id != context.run_id or not 0 < len(answer.text) <= 8192:
        raise CoreConflict("documentary_answer_identity_conflict")
    citations = validate_citations(answer.text, context.evidence.citations)
    if answer.citations != citations:
        raise CoreConflict("documentary_answer_citation_conflict")
    decision = context.interpretation
    return DocumentaryResult(
        kind="evidence_insufficient" if answer.text == REFUSAL else "documentary_answer",
        text=answer.text,
        answer=answer,
        snapshot=context.evidence.snapshot,
        evidence_pack=context.evidence.pack,
        trace=DocumentaryTrace(
            original_question=context.original_question,
            proposed_rewrite=decision.proposed_rewrite,
            selected_query=context.retrieval_query,
            interpretation_mode=decision.mode,
            interpretation_identity=fingerprint(decision.model_dump(mode="json")),
            history_sources=tuple(h.source for h in context.history),
            state_item_ids=tuple(e.item.id for e in context.working_state),
            scope=decision.scope,
            evidence_identity=fingerprint(context.evidence.pack.model_dump(mode="json")),
        ),
    )


def produce(
    workspace: UUID,
    run_id: UUID,
    context: InterpretationInput,
    *,
    draft: InterpretationDraft | None = None,
    retriever: DocumentaryRetriever,
    generator: AnswerGenerator,
    max_input_bytes: int,
):
    """Pure orchestration seam. Supplied DTO fixtures do not prove PG authority."""
    decision = interpret(context, draft=draft)
    if decision.mode == "CLARIFY":
        if max_input_bytes <= 0 or len(decision.model_dump_json().encode("utf-8")) > max_input_bytes:
            raise CoreConflict("conversation_context_overflow")
        return decision.control_result, decision
    evidence = retriever.retrieve(workspace, context.request.scope, decision.selected_query)
    # Detach mutable adapter objects before exposing a copy to generation.
    evidence = CurrentEvidence.model_validate(evidence.model_dump(mode="json"))
    assembled = assemble(workspace, run_id, context, decision, evidence, max_input_bytes=max_input_bytes)
    answer = (
        generator.generate(assembled.model_copy(deep=True))
        if evidence.citations
        else Answer(run_id=run_id, text=REFUSAL, citations=[], prompt_version="not_invoked", estimated_yuan=0)
    )
    return make_result(assembled, answer), decision


def execute(
    workspace, run: RunView, query: HistoryQuery, *, draft, retriever, generator, max_input_bytes, permit=None
):
    """Admitted Run -> existing history/interpretation -> Evidence -> atomic accept.

    Failure propagates without publication or implicit retries. Existing explicit
    finish/reconciliation owns terminal failure handling and slot fencing.
    """
    from citeweave import conversations as core
    from citeweave.conversation_history_pg import read_history

    request, previous = core.execution_input(workspace, run)
    if query.scope != request.scope or query.expected_head != request.expected_head:
        raise CoreConflict("documentary_history_query_conflict")
    history: HistorySelection = read_history(workspace, run.conversation_id, query, permit=permit)
    context = InterpretationInput(
        conversation_id=run.conversation_id,
        turn_id=run.turn_id,
        request=request,
        previous=previous,
        history=history,
    )
    with bounded_stage((run.deadline - datetime.now(timezone.utc)).total_seconds()):
        result, decision = produce(
            workspace,
            run.id,
            context,
            draft=draft,
            retriever=retriever,
            generator=generator,
            max_input_bytes=max_input_bytes,
        )
    return core.accept(
        workspace,
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
