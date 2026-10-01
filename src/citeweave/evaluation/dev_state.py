"""Evaluation-only current State intent. Never a product acceptance adapter.

No source lookup, historical text synthesis, state update or provider dispatch.
Ordinary state-only intent is distinct from atomic raw correction provenance.
"""

from citeweave.catalog import fingerprint
from citeweave.conversation_contract import CoreConflict, ResolvedConversationDelta, ResolvedSignals
from citeweave.conversation_interpretation import InterpretationDraft, InterpretationResult, selected_sources

STATE_INTENT_POLICY = (
    "Evaluation origin clarification v2 (common to R/A/AB0): supplied active bounded Working State "
    "is an exact selected semantic-intent origin, identified by state_item_id and introduced_by. "
    "Ordinary intent may use that origin even when its raw Turn is absent. Never reconstruct its raw "
    "text or treat State as documentary Evidence or raw-source recovery. State cannot replace any "
    "required complete correction/provenance group."
)


def evaluation_messages(context):
    from citeweave.conversation_runtime import interpretation_messages

    messages = interpretation_messages(context)
    messages[0]["content"] += "\n" + STATE_INTENT_POLICY
    return messages


def state_intent(context, draft):
    raw = {s.ref for s in selected_sources(context)}
    draft = InterpretationDraft.model_validate(draft.model_dump(mode="json"))
    if (
        draft.dependency != "required"
        or draft.topic_relation not in {"continue", "return"}
        or draft.ambiguities
        or draft.references
        or draft.corrections
        or draft.put
        or any(s.relations for g in context.history.selected for s in g.sources)
    ):
        raise CoreConflict("evaluation_state_intent_contract")
    entries = {e.item.id: e for e in context.history.state_projection if e.active}
    inherited = []
    state_used = False
    for fact in draft.facts:
        if fact.source is None:
            span = fact.span
            if (
                span.end > len(context.request.question)
                or context.request.question[span.start : span.end] != fact.value
            ):
                raise CoreConflict("interpretation_span_invalid")
        else:
            entry = entries.get(fact.state_item_id)
            if (
                not entry
                or entry.introduced_by != fact.source
                or entry.item.value != fact.value
                or entry.item.kind != fact.kind
            ):
                raise CoreConflict("evaluation_state_intent_origin_invalid")
            inherited.append(fact.value)
            state_used |= fact.source not in raw
    rewrite = draft.rewrite
    expected = context.request.question + "\n" + "\n".join(dict.fromkeys(inherited))
    if not state_used or not rewrite or rewrite.scope != context.request.scope:
        raise CoreConflict("evaluation_state_intent_contract")
    if (
        rewrite.text != expected
        or rewrite.retained != context.required
        or any(t.value not in context.request.question for t in context.required)
    ):
        raise CoreConflict("rewrite_fidelity_conflict")
    # A provisional, non-published delta: do not invent a raw dependency or change
    # accepted state to make this diagnostic fit the production commit contract.
    delta = ResolvedConversationDelta(
        source_turn_id=context.turn_id,
        previous_snapshot_id=context.request.expected_head,
        signals=ResolvedSignals(),
    )
    return InterpretationResult(
        mode="USE_REWRITE",
        input_mode="supplied_structured_draft",
        original_question=context.request.question,
        proposed_rewrite=rewrite.text,
        selected_query=rewrite.text,
        scope=context.request.scope,
        topic_relation=draft.topic_relation,
        sources=(),
        bindings=(),
        facts=draft.facts,
        ambiguities=(),
        delta=delta,
        delta_identity=fingerprint(delta.model_dump(mode="json")),
        control_result=None,
    )
