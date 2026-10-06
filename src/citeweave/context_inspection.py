"""Read-only, allowlisted context diagnostics bound to durable Acceptance truth.

Optional local receipts are observations, never business or document authority.
Missing or unverifiable receipts do not become a reconstructed candidate set.
"""

import json
from hashlib import sha256
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select

from citeweave import conversations as core
from citeweave.catalog import fingerprint
from citeweave.conversation_contract import DurableDTO, Scope, SourceRef, StateEntry
from citeweave.conversation_evidence import intent_context
from citeweave.conversation_history import AcceptedHistory, HistorySelection, within
from citeweave.conversation_interpretation import IntentFact, InterpretationInput, interpret
from citeweave.conversation_models import ConversationAcceptanceRow
from citeweave.db import transaction
from citeweave.domain import ProviderPhaseRow
from citeweave.history_relevance import CandidateGroup, CandidateInput, CandidateSource, RelevanceDraft
from citeweave.interpretation_format import decode_format
from citeweave.llm import completion_payload
from citeweave.provider_accounting import request_hash
from citeweave.runtime_inspection import ConversationRunInspection, inspection_view
from citeweave.settings import ROOT

MAX_RECEIPT_BYTES = 2 * 1024 * 1024


class ContextSource(DurableDTO):
    source: SourceRef
    question: str
    run_id: UUID
    origins: tuple[str, ...]
    relevant: bool
    selected_group: bool
    recent_candidate: bool


class ReferenceObservation(DurableDTO):
    mention: str
    start: int
    end: int
    values: tuple[str, ...]
    sources: tuple[SourceRef, ...]


class ContextInputScope(Scope):
    """Keep the existing public documentary Scope schema name stable."""


class ContextStateEntry(StateEntry):
    scope: ContextInputScope


class ContextObservation(DurableDTO):
    revision: Literal["context-observation-v1"] = "context-observation-v1"
    run_id: UUID
    availability: Literal["VERIFIED_LOCAL_RECEIPT", "NOT_RECORDED", "UNVERIFIABLE"]
    # These collections are nullable: missing observations are not empty input.
    candidates: tuple[ContextSource, ...] | None = None
    relevant_sources: tuple[SourceRef, ...] | None = None
    recent_sources: tuple[SourceRef, ...] | None = None
    working_state: tuple[ContextStateEntry, ...] | None = None
    used_state_item_ids: tuple[UUID, ...] | None = None
    references: tuple[ReferenceObservation, ...] | None = None
    inherited_facts: tuple[IntentFact, ...] | None = None
    topic_relation: Literal["continue", "shift", "return"] | None = None
    dependency: Literal["none", "required", "unresolved"] | None = None
    candidate_input_identity: str | None = None
    interpretation_identity: str | None = None


def _source_reader(workspace, conversation_id):
    def read(source_id):
        with transaction() as db:
            run_id = db.scalar(
                select(ConversationAcceptanceRow.run_id).where(
                    ConversationAcceptanceRow.id == source_id,
                    ConversationAcceptanceRow.conversation_id == conversation_id,
                )
            )
        if run_id is None:
            raise ValueError("context_source_unavailable")
        return core.read_run_id(workspace, conversation_id, run_id)

    return read


def verified_projection(value: ConversationRunInspection, receipt: dict, read_source) -> ContextObservation:
    trace = value.trace
    if trace.metadata_availability != "documentary_bundle":
        raise ValueError("context_documentary_binding_unavailable")
    if receipt["kind"] != "interpretation_context_not_evidence":
        raise ValueError("context_receipt_kind")
    messages = receipt["candidate_input"]
    if fingerprint(messages) != receipt["candidate_input_identity"]:
        raise ValueError("context_input_identity")
    raw = receipt["raw_interpretation_response"]
    if not isinstance(raw, str):
        raise ValueError("context_response_type")
    if sha256(raw.encode("utf8")).hexdigest() != receipt["provider_response_sha256"]:
        raise ValueError("context_response_identity")
    wire = RelevanceDraft.model_validate_json(raw)
    if wire != RelevanceDraft.model_validate(receipt["relevance_decision"]):
        raise ValueError("context_decision_identity")
    h = HistorySelection.model_validate(receipt["resolved_history"])
    if fingerprint(h.model_dump(mode="json")) != receipt["resolved_history_identity"]:
        raise ValueError("context_history_identity")
    payload = json.loads(messages[1]["content"])
    if (
        len(messages) != 2
        or messages[0]["role"] != "system"
        or messages[1]["role"] != "user"
        or payload["question"] != trace.original_question
        or payload["scope"] != trace.scope.model_dump(mode="json")
        or h.head != trace.input_head_id
        or h.failure
        or h.search_incomplete
    ):
        raise ValueError("context_request_binding")
    candidate = CandidateInput.model_validate(payload["candidate_history"])
    expected = tuple(
        CandidateGroup(
            identity=g.identity,
            sources=tuple(
                CandidateSource(
                    source=s.ref,
                    original_question=s.request.question,
                    scope=s.request.scope,
                    signals=s.signals,
                    relations=s.relations,
                )
                for s in g.sources
            ),
            superseded=g.superseded,
            partially_superseded=g.partially_superseded,
        )
        for g in h.candidates
    )
    if candidate.groups != expected or candidate.working_state != h.state_projection:
        raise ValueError("context_candidate_binding")
    available = {s.ref: s for g in h.candidates for s in g.sources}
    relevant = set(wire.relevant_sources)
    selected = {s.ref for g in h.selected for s in g.sources}
    if (
        len(relevant) != len(wire.relevant_sources)
        or not relevant <= selected <= available.keys()
        or not set(h.a_inputs) <= available.keys()
    ):
        raise ValueError("context_selection_binding")
    for s in available.values():
        durable = read_source(s.acceptance.id)
        if (
            durable.run.conversation_id != trace.conversation_id
            or durable.run.status != "ACCEPTED"
            or durable.accepted is None
            or AcceptedHistory.from_acceptance(durable.accepted)
            != AcceptedHistory.from_acceptance(s.acceptance)
            or durable.turn.request != s.request
            or not within(s.request.scope, trace.scope)
        ):
            raise ValueError("context_durable_source_binding")
    previous = read_source(h.head).accepted if h.head else None
    context = InterpretationInput(
        conversation_id=trace.conversation_id,
        turn_id=trace.turn_id,
        request=dict(
            question=trace.original_question,
            scope=trace.scope.model_dump(mode="json"),
            expected_head=trace.input_head_id,
        ),
        history=h,
        previous=previous,
        required=payload["required"],
    )
    draft = decode_format(wire.model_dump_json(exclude={"relevant_sources"}), context)
    decision = interpret(context, draft=draft)
    history, state = intent_context(context, decision)
    if (
        fingerprint(decision.model_dump(mode="json")) != trace.interpretation_identity
        or decision.selected_query != trace.selected_query
        or tuple(s.source for s in history) != trace.history_sources
        or tuple(s.item.id for s in state) != trace.input_state_item_ids
    ):
        raise ValueError("context_accepted_interpretation_binding")
    return ContextObservation(
        run_id=trace.run_id,
        availability="VERIFIED_LOCAL_RECEIPT",
        candidates=tuple(
            ContextSource(
                source=s.ref,
                question=s.request.question,
                run_id=s.acceptance.run_id,
                origins=s.origins,
                relevant=s.ref in relevant,
                selected_group=s.ref in selected,
                recent_candidate=s.ref in h.a_inputs,
            )
            for s in available.values()
        ),
        relevant_sources=wire.relevant_sources,
        recent_sources=h.a_inputs,
        working_state=tuple(
            ContextStateEntry.model_validate(e.model_dump(mode="json")) for e in h.state_projection
        ),
        used_state_item_ids=trace.input_state_item_ids,
        references=tuple(
            ReferenceObservation(
                mention=trace.original_question[r.mention.start : r.mention.end],
                start=r.mention.start,
                end=r.mention.end,
                values=tuple(f.value for f in r.candidates),
                sources=tuple(dict.fromkeys(f.source for f in r.candidates if f.source)),
            )
            for r in draft.references
        ),
        inherited_facts=tuple(f for f in decision.facts if f.source is not None),
        topic_relation=wire.topic_relation,
        dependency=wire.dependency,
        candidate_input_identity=receipt["candidate_input_identity"],
        interpretation_identity=trace.interpretation_identity,
    )


def verify_provider_binding(receipt: dict, phase):
    if (
        phase is None
        or phase.state != "COMPLETED"
        or phase.result_hash != receipt["provider_response_sha256"]
        or phase.request_hash
        != request_hash(completion_payload(receipt["candidate_input"], phase.model, phase.output_tokens))
    ):
        raise ValueError("context_durable_provider_binding")


def observe_context(workspace, conversation_id: UUID, run_id: UUID) -> ContextObservation:
    # Authorize immutable versions before touching the optional local receipt.
    value = inspection_view(core.read_run_id(workspace, conversation_id, run_id))
    path = ROOT / ".runtime/interpretation-context" / str(run_id) / "receipt.json"
    if not path.exists():
        return ContextObservation(run_id=run_id, availability="NOT_RECORDED")
    try:
        if path.stat().st_size > MAX_RECEIPT_BYTES:
            raise ValueError("context_receipt_size")
        receipt = json.loads(path.read_text("utf8"))
        with transaction() as db:
            phase = db.execute(
                select(
                    ProviderPhaseRow.state,
                    ProviderPhaseRow.model,
                    ProviderPhaseRow.output_tokens,
                    ProviderPhaseRow.request_hash,
                    ProviderPhaseRow.result_hash,
                ).where(
                    ProviderPhaseRow.conversation_run_id == run_id,
                    ProviderPhaseRow.phase == "interpretation",
                )
            ).one_or_none()
        verify_provider_binding(receipt, phase)
        return verified_projection(value, receipt, _source_reader(workspace, conversation_id))
    except (OSError, ValueError, KeyError, IndexError, TypeError, HTTPException):
        # Explicit unavailable observation, no raw body or inferred replacement.
        return ContextObservation(run_id=run_id, availability="UNVERIFIABLE")


def mount(app, principal):
    @app.get(
        "/v1/conversations/{conversation_id}/runs/{run_id}/context",
        response_model=ContextObservation,
    )
    def context(conversation_id: UUID, run_id: UUID, workspace=Depends(principal)):
        return observe_context(workspace, conversation_id, run_id)
