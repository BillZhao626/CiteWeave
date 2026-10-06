"""Product-only candidate inspection followed by explicit, validated relevance.

Legacy experiments and selected-history guards remain unchanged. Candidates
are contextual intent only; no answer, EvidencePack or PDF geometry is exposed.
"""

import json
import logging
import os
from hashlib import sha256
from typing import Literal
from uuid import UUID

from pydantic import Field, ValidationError

from citeweave.catalog import fingerprint
from citeweave.conversation_contract import (
    CoreConflict,
    DurableDTO,
    HistoryRelation,
    ResolvedSignals,
    Scope,
    SourceRef,
    StateEntry,
)
from citeweave.conversation_history import (
    MAX_BYTES,
    MAX_MEMBERS,
    MAX_ROWS,
    MAX_TRIPS,
    C,
    HistoryQuery,
    HistorySelection,
    K,
    Rejection,
    select_history,
)
from citeweave.conversation_interpretation import InterpretationInput, selected_sources
from citeweave.interpretation_format import FormatDraft, decode_format
from citeweave.interpretation_response import record_interpretation_failure
from citeweave.settings import ROOT


class CandidateSource(DurableDTO):
    source: SourceRef
    original_question: str
    scope: Scope
    signals: ResolvedSignals
    relations: tuple[HistoryRelation, ...]


class CandidateGroup(DurableDTO):
    identity: tuple[UUID, ...]
    sources: tuple[CandidateSource, ...]
    superseded: tuple[SourceRef, ...]
    partially_superseded: tuple[SourceRef, ...]


class CandidateInput(DurableDTO):
    authority: Literal["contextual_intent_candidates_not_selected_not_evidence"] = (
        "contextual_intent_candidates_not_selected_not_evidence"
    )
    groups: tuple[CandidateGroup, ...] = Field(max_length=C)
    working_state: tuple[StateEntry, ...]


class RelevanceDraft(FormatDraft):
    # Required even for []: omission cannot masquerade as an explicit decision.
    relevant_sources: tuple[SourceRef, ...]


class CandidateHistory(DurableDTO):
    query: HistoryQuery
    history: HistorySelection

    def validate_for(self, context: InterpretationInput) -> CandidateInput:
        h = self.history
        if (
            context.history != h
            or self.query.scope != context.request.scope
            or self.query.expected_head != h.head
        ):
            raise CoreConflict("interpretation_candidate_input_conflict")
        if h.selected or len(h.candidates) > C:
            raise CoreConflict("interpretation_candidate_bound")
        if h.payload_bytes > MAX_BYTES or h.materialized_rows > MAX_ROWS or h.round_trips > MAX_TRIPS:
            raise CoreConflict("interpretation_candidate_bound")
        if any(len(g.sources) > MAX_MEMBERS for g in h.candidates):
            raise CoreConflict("interpretation_candidate_bound")
        # The existing guard checks failure/incompleteness, head, conversation,
        # scope, full correction closure and active-state projection before send.
        visible = context.model_copy(update={"history": h.model_copy(update={"selected": h.candidates})})
        sources = selected_sources(visible)
        if len({g.identity for g in h.candidates}) != len(h.candidates):
            raise CoreConflict("interpretation_candidate_identity_conflict")
        refs = {s.ref for s in sources}
        required = set(self.query.explicit + self.query.mandatory) | {
            e.introduced_by for e in h.state_projection
        }
        if not required <= refs:
            raise CoreConflict("interpretation_candidate_source_unavailable")
        for g in h.candidates:
            if g.identity != tuple(sorted(s.acceptance.id for s in g.sources)):
                raise CoreConflict("interpretation_candidate_identity_conflict")
        # Group boundaries and correction/mandatory metadata are derived from
        # source relations and active state, never trusted as caller assertions.
        # Recompute locally over the bounded visible set without another search.
        canonical = select_history(
            tuple(s for g in h.candidates for s in g.sources),
            self.query,
            h.state_projection,
            candidate_mode=True,
        )
        if canonical.failure or canonical.candidates != h.candidates:
            raise CoreConflict("interpretation_candidate_group_conflict")
        payload = CandidateInput(
            groups=tuple(
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
            ),
            working_state=h.state_projection,
        )
        if len(payload.model_dump_json().encode("utf-8")) > MAX_BYTES:
            raise CoreConflict("interpretation_candidate_payload_cap")
        return payload


def candidate_messages(context: InterpretationInput, candidates: CandidateHistory):
    payload = candidates.validate_for(context)
    value = dict(
        authority=payload.authority,
        question=context.request.question,
        scope=context.request.scope.model_dump(mode="json"),
        required=[r.model_dump(mode="json") for r in context.required],
        candidate_history=payload.model_dump(mode="json"),
        output_schema=RelevanceDraft.model_json_schema(),
    )
    return [
        {
            "role": "system",
            "content": (ROOT / "prompts/conversation-interpretation-relevance-v1.txt").read_text("utf8"),
        },
        {"role": "user", "content": json.dumps(value, ensure_ascii=False, separators=(",", ":"))},
    ]


def resolve_response(raw: str, *, context: InterpretationInput, candidates: CandidateHistory, run_id: UUID):
    try:
        candidates.validate_for(context)
        try:
            wire = RelevanceDraft.model_validate_json(raw)
        except ValidationError as exc:
            raise CoreConflict("interpretation_format_schema") from exc
        chosen = set(wire.relevant_sources)
        if len(chosen) != len(wire.relevant_sources):
            raise CoreConflict("interpretation_relevance_duplicate_source")
        available = {s.ref for g in candidates.history.candidates for s in g.sources}
        if not chosen <= available:
            raise CoreConflict("interpretation_relevance_source_unavailable")
        # Selecting a source expands its whole provenance group. Mandatory state
        # groups remain available for existing ambiguity/correction guards, but
        # they confer no permission to inherit an unchosen source fact.
        groups = tuple(
            g for g in candidates.history.candidates if g.mandatory or any(s.ref in chosen for s in g.sources)
        )
        if len(groups) > K:
            raise CoreConflict("interpretation_relevance_exceeds_K")
        facts = (
            *wire.facts,
            *(f for r in wire.references for f in r.candidates),
            *(f for a in wire.ambiguities for f in a.candidates),
        )
        origins = {f.origin.source for f in facts if f.origin.type != "current"}
        items = {e.item.id: e for e in candidates.history.state_projection}
        correction_sources = {items[c.item_id].introduced_by for c in wire.corrections if c.item_id in items}
        if not origins <= chosen or not chosen <= origins | correction_sources:
            raise CoreConflict("interpretation_relevance_origin_conflict")
        h = candidates.history
        resolved = h.model_copy(
            update={
                "selected": groups,
                "rejected": h.rejected
                + tuple(
                    Rejection(identity=g.identity, reason="model_no_relevance")
                    for g in h.candidates
                    if g not in groups
                ),
            }
        )
        final_context = context.model_copy(update={"history": resolved})
        # Strip only the declared relevance field; the existing converter and
        # semantic validator still reject unsupported facts/rewrites/corrections.
        draft = decode_format(wire.model_dump_json(exclude={"relevant_sources"}), final_context)
        selected_sources(final_context)
        return final_context, draft, wire
    except ValueError as exc:
        record_interpretation_failure(raw, run_id=run_id, exc=exc)
        raise


def record_context_receipt(run_id, *, messages, candidates, context, wire, raw):
    if os.environ.get("CW_INTERPRETATION_CONTEXT_RECEIPTS") == "1":
        try:
            folder = ROOT / ".runtime/interpretation-context" / str(UUID(str(run_id)))
            folder.mkdir(parents=True, exist_ok=True)
            value = dict(
                kind="interpretation_context_not_evidence",
                candidate_input=messages,
                candidate_input_identity=fingerprint(messages),
                candidate_history_identity=fingerprint(candidates.model_dump(mode="json")),
                resolved_history=context.history.model_dump(mode="json"),
                resolved_history_identity=fingerprint(context.history.model_dump(mode="json")),
                relevance_decision=wire.model_dump(mode="json"),
                raw_interpretation_response=raw,
                provider_response_sha256=sha256(raw.encode("utf-8")).hexdigest(),
            )
            with (folder / "receipt.json").open("x", encoding="utf8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
        except Exception:
            logging.warning("interpretation_context_receipt_write_failed run=%s", run_id)
