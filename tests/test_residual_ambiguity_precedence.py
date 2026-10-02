"""A valid old-task declaration cannot bypass unresolved intent clarification."""

from uuid import uuid4

import pytest
from test_residual_topic_micro import CAP, facts, inherited_task, raw, scenario, state_entity

from citeweave.conversation_contract import CoreConflict, StateValue
from citeweave.conversation_interpretation import interpret
from citeweave.runtime_rc_closure import decode_closure
from citeweave.runtime_residual_closure import decode_residual


@pytest.mark.parametrize("candidates", [0, 2])
def test_exact_old_task_with_unresolved_reference_clarifies_without_topic_conversion(candidates):
    context, older, _, unit = scenario(extra_entity=candidates == 2)
    proposals = []
    if candidates:
        entries = [e.item for e in context.history.state_projection if e.active and e.item.kind == "entity"]
        proposals = [state_entity(item, older) for item in entries]
    value = raw([inherited_task(older)], references=[dict(mention=dict(quote="it"), candidates=proposals)])
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decode_closure(value, context, fact_bytes_cap=CAP)
    draft = decode_residual(value, context, fact_bytes_cap=CAP)
    result = interpret(context, draft=draft)
    assert draft.topic_relation == result.topic_relation == "continue"
    assert result.mode == "CLARIFY" and result.selected_query is None
    assert result.delta.signals.task is None and result.control_result.kind == "clarification"
    assert result.delta.topic_relation is None and not result.facts and not result.bindings
    assert len(result.delta.put) == 1 and result.delta.put[0].kind == "ambiguity"
    assert all(r.kind == "dependency" for r in result.delta.relations)


def test_explicit_unresolved_intent_takes_precedence_without_inventing_return():
    context, older, _, unit = scenario()
    value = raw(facts(older, unit), ambiguities=[dict(reason="unresolved_intent")])
    draft = decode_residual(value, context, fact_bytes_cap=CAP)
    result = interpret(context, draft=draft)
    assert draft.topic_relation == "continue" and result.mode == "CLARIFY"
    assert result.selected_query is None and result.delta.topic_relation is None
    assert len(result.delta.put) == 1 and result.delta.put[0].kind == "ambiguity"


def test_persisted_pending_ambiguity_cannot_be_resolved_by_a_singleton_model_guess():
    pending = StateValue(id=uuid4(), kind="ambiguity", key="unresolved-unit", value="Choose the unit")
    context, older, _, unit = scenario(head_put=(pending,))
    value = raw(facts(older, unit))  # No explicit resolution of the durable pending item.
    draft = decode_residual(value, context, fact_bytes_cap=CAP)
    result = interpret(context, draft=draft)
    assert draft.topic_relation == "continue" and result.mode == "CLARIFY"
    assert result.selected_query is None and result.delta.topic_relation is None
    # The authoritative reducer replaces the pending item with the new typed
    # ambiguity bundle, retaining its raw correction provenance.
    assert result.delta.deactivate == (pending.id,)
    assert len(result.delta.put) == 1 and result.delta.put[0].kind == "ambiguity"
    assert any(r.kind == "correction" and r.state_item_ids == (pending.id,) for r in result.delta.relations)


def test_clarification_precedence_still_rejects_invalid_claimed_origin():
    context, older, _, unit = scenario()
    claimed = facts(older, unit)
    claimed[1]["origin"]["state_item_id"] = str(uuid4())
    with pytest.raises(CoreConflict, match="reconciliation_origin_unavailable_or_ambiguous"):
        decode_residual(
            raw(claimed, ambiguities=[dict(reason="unresolved_intent")]), context, fact_bytes_cap=CAP
        )
