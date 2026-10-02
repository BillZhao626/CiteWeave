"""Reconciled P0 wire behavior with explicit candidate/resolution semantics.

Only uniquely identified bookkeeping is derived. Invalid/ambiguous origins and
malformed JSON fail closed. The existing core validates the resulting draft.
"""

import json
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, ValidationError

from citeweave.conversation_contract import CoreConflict, DurableDTO, SourceRef, StateValue
from citeweave.conversation_interpretation import (
    Ambiguity,
    FactKind,
    IntentFact,
    InterpretationDraft,
    ReferenceDraft,
    RetrievalRewrite,
    StateCorrection,
    TextSpan,
    interpret,
)
from citeweave.settings import ROOT

REVISION = "interpretation-reconciled-v4"


class CurrentOrigin(DurableDTO):
    type: Literal["current"]
    occurrence: int | None = Field(default=None, ge=0, strict=True)


class HistoryOrigin(DurableDTO):
    type: Literal["history"]
    source: SourceRef | None = None


class StateOrigin(DurableDTO):
    type: Literal["state"]
    source: SourceRef | None = None
    state_item_id: UUID | None = None


class FormatFact(DurableDTO):
    kind: FactKind
    value: str = Field(min_length=1)
    origin: Annotated[CurrentOrigin | HistoryOrigin | StateOrigin, Field(discriminator="type")]


class Mention(DurableDTO):
    quote: str = Field(min_length=1)
    occurrence: int | None = Field(default=None, ge=0, strict=True)


class Reference(DurableDTO):
    mention: Mention
    candidates: tuple[FormatFact, ...] = ()


class FormatAmbiguity(DurableDTO):
    reason: Literal["unresolved_reference", "multiple_candidates", "unresolved_intent", "pending_ambiguity"]
    mention: Mention | None = None
    candidates: tuple[FormatFact, ...] = ()


class Correction(DurableDTO):
    item_id: UUID
    mention: Mention


class Resolution(DurableDTO):
    ambiguity_key: str = Field(min_length=1)
    selection: FormatFact
    occurrence: int | None = Field(default=None, ge=0, strict=True)


class FormatDraft(DurableDTO):
    topic_relation: Literal["continue", "shift", "return"]
    dependency: Literal["none", "required", "unresolved"]
    facts: tuple[FormatFact, ...] = ()
    references: tuple[Reference, ...] = ()
    ambiguities: tuple[FormatAmbiguity, ...] = ()
    put: tuple[StateValue, ...] = ()
    corrections: tuple[Correction, ...] = ()
    resolutions: tuple[Resolution, ...] = ()
    entity_mode: Literal["single", "alternatives", "joint"] = "single"


def localized_span(question, quote, occurrence):
    starts = []
    start = question.find(quote)
    while start >= 0:
        starts.append(start)
        start = question.find(quote, start + 1)
    if not starts:
        raise CoreConflict("reconciliation_localization_unavailable")
    if len(starts) == 1:
        index = 0
    elif occurrence is None:
        raise CoreConflict("reconciliation_localization_ambiguous")
    elif not 0 <= occurrence < len(starts):
        raise CoreConflict("reconciliation_localization_unavailable")
    else:
        index = occurrence
    return TextSpan(start=starts[index], end=starts[index] + len(quote))


def decision_context(context):
    previous = context.previous
    signals = previous.state.delta.signals if previous else None
    raw_sources = {s.ref for g in context.history.selected for s in g.sources}
    tasks = tuple(
        dict.fromkeys(s.signals.task for g in context.history.selected for s in g.sources if s.signals.task)
    )
    return dict(
        head_signals=signals.model_dump(mode="json") if signals else None,
        stable_tasks=[
            dict(value=v, exact_current_literal=context.request.question.count(v) == 1)
            for v in dict.fromkeys((*(tasks), *((signals.task,) if signals and signals.task else ())))
        ],
        state_only_dependency_available=any(
            e.active and e.item.kind == "entity" and e.introduced_by not in raw_sources
            for e in context.history.state_projection
        ),
        pending_ambiguity_keys=[
            e.item.key for e in context.history.state_projection if e.active and e.item.kind == "ambiguity"
        ],
        active_items=[
            dict(
                kind=e.item.kind,
                key=e.item.key,
                value=e.item.value,
                introduced_at_head=bool(previous and e.introduced_by.acceptance_id == previous.id),
                current_literal_occurrences=context.request.question.count(e.item.value),
            )
            for e in context.history.state_projection
            if e.active
        ],
    )


def decode_reconciled(raw, context, *, fact_bytes_cap):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non_json_constant")),
        )
    except (ValueError, TypeError) as exc:
        raise CoreConflict("reconciliation_json") from exc
    try:
        value = FormatDraft.model_validate(parsed)
    except ValidationError as exc:
        raise CoreConflict("reconciliation_schema") from exc
    active = tuple(e for e in context.history.state_projection if e.active)
    sources = tuple(s for g in context.history.selected for s in g.sources)

    def fact(f):
        origin = f.origin
        if isinstance(origin, CurrentOrigin):
            return IntentFact(
                kind=f.kind,
                value=f.value,
                span=localized_span(context.request.question, f.value, origin.occurrence),
            )
        if isinstance(origin, StateOrigin):
            kind = f.kind if f.kind in {"topic", "entity"} else "constraint"
            candidates = [
                e
                for e in active
                if (e.item.kind, e.item.value) == (kind, f.value)
                and (origin.state_item_id is None or e.item.id == origin.state_item_id)
                and (origin.source is None or e.introduced_by == origin.source)
            ]
            if len(candidates) != 1:
                raise CoreConflict("reconciliation_origin_unavailable_or_ambiguous")
            entry = candidates[0]
            return IntentFact(
                kind=f.kind, value=f.value, source=entry.introduced_by, state_item_id=entry.item.id
            )
        candidates = [
            s.ref
            for s in sources
            if (origin.source is None or origin.source == s.ref)
            and (
                f.value
                in (
                    s.signals.entities
                    if f.kind == "entity"
                    else (getattr(s.signals, f.kind, None),)
                    if f.kind in {"topic", "task"}
                    else s.signals.constraints
                )
            )
        ]
        if len(set(candidates)) != 1:
            raise CoreConflict("reconciliation_origin_unavailable_or_ambiguous")
        return IntentFact(kind=f.kind, value=f.value, source=candidates[0])

    def mention(m):
        return localized_span(context.request.question, m.quote, m.occurrence)

    facts = []
    for f in value.facts:
        # Current descriptive constraints do not add retrieval completion bytes.
        # Preserve the whole original question; never omit typed critical facts,
        # inherited origins, references, mutations or any explicitly required term.
        descriptive = (
            f.kind == "constraint"
            and isinstance(f.origin, CurrentOrigin)
            and f.value not in context.request.question
            and not context.required
            and not value.put
            and not value.corrections
            and not any(f == c for r in value.references for c in r.candidates)
            and not any(f == c for a in value.ambiguities for c in a.candidates)
        )
        if descriptive:
            continue
        facts.append(fact(f))
    references = tuple(
        ReferenceDraft(mention=mention(r.mention), candidates=tuple(fact(f) for f in r.candidates))
        for r in value.references
    )
    ambiguities = tuple(
        Ambiguity(
            reason=a.reason,
            mention=mention(a.mention) if a.mention else None,
            candidates=tuple(fact(f) for f in a.candidates),
        )
        for a in value.ambiguities
    )
    corrections = [StateCorrection(item_id=c.item_id, mention=mention(c.mention)) for c in value.corrections]
    choices = []
    corrected_origins = set()
    for resolution in value.resolutions:
        chosen = fact(resolution.selection)
        pending = [e for e in active if e.item.kind == "ambiguity" and e.item.key == resolution.ambiguity_key]
        if chosen.kind != "entity" or chosen.state_item_id is None or len(pending) != 1:
            raise CoreConflict("reconciliation_resolution_unavailable_or_ambiguous")
        span = localized_span(context.request.question, chosen.value, resolution.occurrence)
        if value.entity_mode != "single":
            raise CoreConflict("reconciliation_resolution_entity_mode_conflict")
        corrections.append(StateCorrection(item_id=pending[0].item.id, mention=span))
        corrected_origins.add(pending[0].introduced_by)
        choices.append(chosen)
        if chosen not in facts:
            facts.append(chosen)
    if len({f.value for f in choices}) > 1:
        raise CoreConflict("reconciliation_competing_explicit_selections")
    if choices:
        chosen = choices[0]
        for f in facts:
            if f.kind == "entity" and f.value != chosen.value:
                # Projection must not hide invalid provenance in another model
                # claim. Validate discarded alternatives with the existing core.
                interpret(
                    context,
                    draft=InterpretationDraft(topic_relation="continue", dependency="unresolved", facts=(f,)),
                )
        # The model explicitly selected ONE supported current literal. Other
        # validated entity candidates remain context, not resolved query facts.
        facts = [f for f in facts if f.kind != "entity" or f.value == chosen.value]
        # Whole-source history signals from a corrected ambiguity source cannot
        # be reused by the frozen reducer. An identical unique current literal is
        # an independently valid origin; derive it without altering kind/value.
        facts = [
            IntentFact(
                kind=f.kind, value=f.value, span=localized_span(context.request.question, f.value, None)
            )
            if f.source in corrected_origins
            and f.state_item_id is None
            and context.request.question.count(f.value) == 1
            else f
            for f in facts
        ]
        references = tuple(
            r.model_copy(update={"candidates": (chosen,)})
            if chosen in r.candidates and all(f.kind == "entity" for f in r.candidates)
            else r
            for r in references
        )
        pending_ids = {e.item.id for e in active if e.item.kind == "ambiguity"}
        resolved_ids = {c.item_id for c in corrections}
        ambiguities = tuple(
            a
            for a in ambiguities
            if not (
                (a.reason == "pending_ambiguity" and pending_ids <= resolved_ids)
                or (
                    a.reason in {"multiple_candidates", "unresolved_reference"}
                    and chosen in a.candidates
                    and all(f.kind == "entity" for f in a.candidates)
                )
            )
        )
    inherited_entities = tuple(dict.fromkeys(f for f in facts if f.kind == "entity" and f.source))
    if (
        value.entity_mode != "joint"
        and len({f.value for f in inherited_entities}) > 1
        and not ambiguities
        and not any(len(set(r.candidates)) != 1 for r in references)
    ):
        ambiguities += (Ambiguity(reason="multiple_candidates", candidates=inherited_entities),)
    all_facts = tuple(
        dict.fromkeys(
            (
                *facts,
                *(f for r in references for f in r.candidates),
                *(f for a in ambiguities for f in a.candidates),
            )
        )
    )
    if sum(len(f.model_dump_json().encode()) for f in all_facts) > fact_bytes_cap:
        raise CoreConflict("reconciliation_normalized_fact_envelope")
    # A declared switch back to an earlier selected intent must be explicit.
    # No question keyword classifier or case identity participates in this guard.
    head = decision_context(context)["head_signals"]
    earlier = any(
        f.source and context.previous and f.source.acceptance_id != context.previous.id for f in all_facts
    )
    if (
        value.topic_relation == "continue"
        and head
        and earlier
        and any(f.kind in {"topic", "task"} and head.get(f.kind) and f.value != head[f.kind] for f in facts)
    ):
        raise CoreConflict("reconciliation_topic_return_required")
    inherited = tuple(
        dict.fromkeys(
            f.value
            for f in (*facts, *(f for r in references if len(set(r.candidates)) == 1 for f in r.candidates))
            if f.source
        )
    )
    rewrite = (
        RetrievalRewrite(
            text=context.request.question + "\n" + "\n".join(inherited),
            scope=context.request.scope,
            retained=context.required,
        )
        if (value.dependency == "required" and inherited)
        else None
    )
    return InterpretationDraft(
        topic_relation=value.topic_relation,
        dependency=value.dependency,
        facts=tuple(facts),
        references=references,
        ambiguities=ambiguities,
        rewrite=rewrite,
        put=value.put,
        corrections=tuple(corrections),
    )


def format_messages(context):
    from citeweave.evaluation.dev_state import evaluation_messages

    messages = evaluation_messages(context)
    messages[0]["content"] += "\n" + (
        ROOT / "prompts/conversation-interpretation-reconciled-v4.txt"
    ).read_text(encoding="utf-8")
    payload = json.loads(messages[1]["content"])
    payload["output_schema"] = FormatDraft.model_json_schema()
    payload["decision_context"] = decision_context(context)
    messages[1]["content"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return messages
