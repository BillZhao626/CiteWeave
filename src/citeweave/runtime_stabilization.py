"""Bounded interpretation wire normalization; semantic choices remain explicit.

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
)
from citeweave.settings import ROOT

REVISION = "interpretation-stabilized-v3"


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


def localized_span(question, quote, occurrence):
    starts = []
    start = question.find(quote)
    while start >= 0:
        starts.append(start)
        start = question.find(quote, start + 1)
    if not starts:
        raise CoreConflict("stabilization_localization_unavailable")
    if len(starts) == 1:
        index = 0
    elif occurrence is None:
        raise CoreConflict("stabilization_localization_ambiguous")
    elif not 0 <= occurrence < len(starts):
        raise CoreConflict("stabilization_localization_unavailable")
    else:
        index = occurrence
    return TextSpan(start=starts[index], end=starts[index] + len(quote))


def decision_context(context):
    previous = context.previous
    signals = previous.state.delta.signals if previous else None
    return dict(
        head_signals=signals.model_dump(mode="json") if signals else None,
        active_items=[
            dict(
                kind=e.item.kind,
                key=e.item.key,
                value=e.item.value,
                introduced_at_head=bool(previous and e.introduced_by.acceptance_id == previous.id),
            )
            for e in context.history.state_projection
            if e.active
        ],
    )


def decode_stabilized(raw, context, *, fact_bytes_cap):
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
        raise CoreConflict("stabilization_json") from exc
    try:
        value = FormatDraft.model_validate(parsed)
    except ValidationError as exc:
        raise CoreConflict("stabilization_schema") from exc
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
                raise CoreConflict("stabilization_origin_unavailable_or_ambiguous")
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
                    else s.signals.constraints
                    if f.kind == "constraint"
                    else (getattr(s.signals, f.kind, None),)
                )
            )
        ]
        if len(set(candidates)) != 1:
            raise CoreConflict("stabilization_origin_unavailable_or_ambiguous")
        return IntentFact(kind=f.kind, value=f.value, source=candidates[0])

    def mention(m):
        return localized_span(context.request.question, m.quote, m.occurrence)

    facts = list(fact(f) for f in value.facts)
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
    for resolution in value.resolutions:
        chosen = fact(resolution.selection)
        pending = [e for e in active if e.item.kind == "ambiguity" and e.item.key == resolution.ambiguity_key]
        if chosen.kind != "entity" or chosen.state_item_id is None or len(pending) != 1:
            raise CoreConflict("stabilization_resolution_unavailable_or_ambiguous")
        span = localized_span(context.request.question, chosen.value, resolution.occurrence)
        corrections.append(StateCorrection(item_id=pending[0].item.id, mention=span))
        if chosen not in facts:
            facts.append(chosen)
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
        raise CoreConflict("stabilization_normalized_fact_envelope")
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
        raise CoreConflict("stabilization_topic_return_required")
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
        ROOT / "prompts/conversation-interpretation-stabilized-v3.txt"
    ).read_text(encoding="utf-8")
    payload = json.loads(messages[1]["content"])
    payload["output_schema"] = FormatDraft.model_json_schema()
    payload["decision_context"] = decision_context(context)
    messages[1]["content"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return messages
