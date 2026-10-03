"""Explicit model wire origins, deterministic representation conversion only.

The existing InterpretationDraft/interpret validator retains semantic authority.
No origin, value, dependency, correction or ambiguity is guessed from prose.
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

REVISION = "interpretation-format-v2"


class CurrentOrigin(DurableDTO):
    type: Literal["current"]
    occurrence: int = Field(
        ge=0, strict=True, description="Zero-based occurrence of exact fact value in current question"
    )


class HistoryOrigin(DurableDTO):
    type: Literal["history"]
    source: SourceRef


class StateOrigin(DurableDTO):
    type: Literal["state"]
    source: SourceRef
    state_item_id: UUID


class FormatFact(DurableDTO):
    kind: FactKind
    value: str = Field(min_length=1)
    origin: Annotated[CurrentOrigin | HistoryOrigin | StateOrigin, Field(discriminator="type")]


class Mention(DurableDTO):
    quote: str = Field(min_length=1)
    occurrence: int = Field(ge=0, strict=True)


class FormatReference(DurableDTO):
    mention: Mention
    candidates: tuple[FormatFact, ...] = ()


class FormatAmbiguity(DurableDTO):
    reason: Literal["unresolved_reference", "multiple_candidates", "unresolved_intent", "pending_ambiguity"]
    mention: Mention | None = None
    candidates: tuple[FormatFact, ...] = ()


class FormatCorrection(DurableDTO):
    item_id: UUID
    mention: Mention


class FormatDraft(DurableDTO):
    topic_relation: Literal["continue", "shift", "return"]
    dependency: Literal["none", "required", "unresolved"]
    facts: tuple[FormatFact, ...] = ()
    references: tuple[FormatReference, ...] = ()
    ambiguities: tuple[FormatAmbiguity, ...] = ()
    put: tuple[StateValue, ...] = ()
    corrections: tuple[FormatCorrection, ...] = ()


def quote_span(question, quote, occurrence):
    # Exact Unicode codepoint positions; overlapping occurrences count too.
    start = -1
    for _ in range(occurrence + 1):
        start = question.find(quote, start + 1)
        if start < 0:
            raise CoreConflict("interpretation_format_quote_occurrence")
    return TextSpan(start=start, end=start + len(quote))


def decode_format(raw, context):
    try:
        value = FormatDraft.model_validate_json(raw)
    except ValidationError as exc:
        raise CoreConflict("interpretation_format_schema") from exc
    entries = {e.item.id: e for e in context.history.state_projection if e.active}

    def fact(f):
        origin = f.origin
        if isinstance(origin, CurrentOrigin):
            return IntentFact(
                kind=f.kind,
                value=f.value,
                span=quote_span(context.request.question, f.value, origin.occurrence),
            )
        if isinstance(origin, StateOrigin):
            e = entries.get(origin.state_item_id)
            if not e or e.introduced_by != origin.source:
                raise CoreConflict("interpretation_format_state_source_identity")
            if e.item.value != f.value:
                raise CoreConflict("interpretation_format_state_value_identity")
        return IntentFact(
            kind=f.kind,
            value=f.value,
            source=origin.source,
            state_item_id=origin.state_item_id if isinstance(origin, StateOrigin) else None,
        )

    def mention(m):
        return quote_span(context.request.question, m.quote, m.occurrence)

    facts = tuple(fact(f) for f in value.facts)
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
    # The core's exact completion-only serializer is deterministic. Reference
    # candidates become facts only for an unambiguous singleton, as in interpret.
    inherited = tuple(
        dict.fromkeys(
            f.value
            for f in (*facts, *(f for r in references if len(set(r.candidates)) == 1 for f in r.candidates))
            if f.source is not None
        )
    )
    rewrite = (
        RetrievalRewrite(
            text=context.request.question + "\n" + "\n".join(inherited),
            scope=context.request.scope,
            retained=context.required,
        )
        if value.dependency == "required" and inherited
        else None
    )
    return InterpretationDraft(
        topic_relation=value.topic_relation,
        dependency=value.dependency,
        facts=facts,
        references=references,
        ambiguities=ambiguities,
        rewrite=rewrite,
        put=value.put,
        corrections=tuple(
            StateCorrection(item_id=c.item_id, mention=mention(c.mention)) for c in value.corrections
        ),
    )


def format_messages(context):
    from citeweave.evaluation.dev_state import evaluation_messages

    messages = evaluation_messages(context)
    messages[0]["content"] += "\n" + (ROOT / "prompts/conversation-interpretation-format-v2.txt").read_text(
        encoding="utf-8"
    )
    payload = json.loads(messages[1]["content"])
    payload["output_schema"] = FormatDraft.model_json_schema()
    messages[1]["content"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return messages
