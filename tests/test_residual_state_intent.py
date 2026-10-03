"""Synthetic singleton-State bindings; no provider, Gold or semantic-label lookup."""

from uuid import uuid4

import pytest
from test_conversation_history import source, state_step
from test_conversation_interpretation import context as context
from test_conversation_interpretation import with_sources

from citeweave.conversation_contract import CoreConflict, HistoryRelation, StateValue
from citeweave.conversation_evidence import intent_context
from citeweave.conversation_history import HistorySelection, project_state
from citeweave.conversation_interpretation import (
    CriticalTerm,
    IntentFact,
    InterpretationDraft,
    ReferenceDraft,
    RetrievalRewrite,
    StateCorrection,
    TextSpan,
)
from citeweave.evaluation.dev_state import state_intent


def state_context(context, *, kind="entity"):
    first = state_step(
        context.request.scope,
        put=(
            StateValue(id=uuid4(), kind=kind, key="subject", value="Orchid"),
            StateValue(id=uuid4(), kind="entity", key="alternative", value="Linden"),
        ),
    )
    latest = state_step(context.request.scope, first)
    question = "Inspect it, NOT before 4 days."
    context = context.model_copy(
        update={
            "request": context.request.model_copy(update={"question": question, "expected_head": latest.id}),
            "previous": latest,
            "history": HistorySelection(
                head=latest.id, state_projection=project_state(latest.state, context.request.scope)
            ),
        }
    )
    entries = context.history.state_projection
    facts = tuple(
        IntentFact(kind=e.item.kind, value=e.item.value, source=e.introduced_by, state_item_id=e.item.id)
        for e in entries
    )
    return context, facts


def mention(context, value="it"):
    start = context.request.question.index(value)
    return TextSpan(start=start, end=start + len(value))


def proposal(context, *, facts=(), candidates=(), relation="return", dependency="required"):
    inherited = tuple(dict.fromkeys(f.value for f in (*facts, *candidates) if f.source))
    return InterpretationDraft(
        topic_relation=relation,
        dependency=dependency,
        facts=facts,
        references=(ReferenceDraft(mention=mention(context), candidates=candidates),),
        rewrite=RetrievalRewrite(
            text=context.request.question + "\n" + "\n".join(inherited),
            scope=context.request.scope,
            retained=context.required,
        ),
    )


@pytest.mark.parametrize("kind", ["entity", "topic", "constraint"])
@pytest.mark.parametrize("relation", ["continue", "return"])
def test_declared_singleton_state_reference_preserves_binding_without_raw_history(context, kind, relation):
    context, (chosen, _) = state_context(context, kind=kind)
    draft = proposal(context, candidates=(chosen,), relation=relation)
    decision = state_intent(context, draft)
    assert decision.topic_relation == relation
    assert decision.selected_query == context.request.question + "\nOrchid"
    assert decision.bindings == draft.references and decision.facts == (chosen,)
    assert decision.sources == () and decision.ambiguities == ()
    assert decision.delta.put == () and decision.delta.deactivate == () and decision.delta.relations == ()
    history, state = intent_context(context, decision)
    assert history == () and tuple(e.item.id for e in state) == (chosen.state_item_id,)


def test_duplicate_facts_and_same_mention_same_origin_produce_one_explicit_binding(context):
    context, (chosen, _) = state_context(context)
    draft = proposal(context, facts=(chosen, chosen), candidates=(chosen, chosen))
    draft = draft.model_copy(update={"references": (*draft.references, *draft.references)})
    decision = state_intent(context, draft)
    assert decision.facts == (chosen,)
    assert decision.bindings == (draft.references[0].model_copy(update={"candidates": (chosen,)}),)
    assert decision.selected_query == context.request.question + "\nOrchid"


def test_current_negation_time_and_required_terms_are_retained_with_state_reference(context):
    context, (chosen, _) = state_context(context)
    required = (
        CriticalTerm(dimension="negation", value="NOT"),
        CriticalTerm(dimension="time", value="4 days"),
    )
    context = context.model_copy(update={"required": required})
    current = tuple(
        IntentFact(kind=t.dimension, value=t.value, span=mention(context, t.value)) for t in required
    )
    draft = proposal(context, facts=current, candidates=(chosen,))
    decision = state_intent(context, draft)
    assert decision.selected_query == context.request.question + "\nOrchid"
    assert decision.facts == (*current, chosen)
    assert "NOT before 4 days" in decision.selected_query
    bad = draft.model_copy(update={"rewrite": draft.rewrite.model_copy(update={"retained": ()})})
    with pytest.raises(CoreConflict, match="rewrite_fidelity_conflict"):
        state_intent(context, bad)


@pytest.mark.parametrize("size", [0, 2])
def test_empty_or_competing_state_candidates_are_not_guessed(context, size):
    context, available = state_context(context)
    with pytest.raises(CoreConflict, match="evaluation_state_intent_reference_unresolved"):
        state_intent(context, proposal(context, candidates=available[:size]))


def test_two_singleton_claims_for_one_mention_cannot_hide_competing_candidates(context):
    context, (one, two) = state_context(context)
    draft = proposal(context, candidates=(one,))
    other = draft.references[0].model_copy(update={"candidates": (two,)})
    draft = draft.model_copy(update={"references": (*draft.references, other)})
    with pytest.raises(CoreConflict, match="evaluation_state_intent_reference_unresolved"):
        state_intent(context, draft)


@pytest.mark.parametrize("fault", ["kind", "value", "state_id", "source", "raw_history", "current"])
def test_singleton_reference_still_requires_exact_active_state_origin(context, fault):
    context, (chosen, _) = state_context(context)
    if fault == "kind":
        chosen = chosen.model_copy(update={"kind": "task"})
    elif fault == "value":
        chosen = chosen.model_copy(update={"value": "Unsupported"})
    elif fault == "state_id":
        chosen = chosen.model_copy(update={"state_item_id": uuid4()})
    elif fault == "source":
        chosen = chosen.model_copy(update={"source": chosen.source.model_copy(update={"turn_id": uuid4()})})
    elif fault == "raw_history":
        chosen = chosen.model_copy(update={"state_item_id": None})
    else:
        chosen = IntentFact(kind="entity", value="it", span=mention(context))
    with pytest.raises(CoreConflict, match="evaluation_state_intent_origin_invalid"):
        state_intent(context, proposal(context, candidates=(chosen,)))


@pytest.mark.parametrize("fault", ["empty", "reversed", "overflow"])
def test_reference_mention_span_is_validated_before_binding(context, fault):
    context, (chosen, _) = state_context(context)
    draft = proposal(context, candidates=(chosen,))
    if fault == "empty":
        bad = TextSpan(start=1, end=1)
    elif fault == "reversed":
        bad = TextSpan(start=2, end=1)
    else:
        bad = TextSpan(start=0, end=len(context.request.question) + 1)
    draft = draft.model_copy(
        update={"references": (draft.references[0].model_copy(update={"mention": bad}),)}
    )
    with pytest.raises(CoreConflict, match="interpretation_span_invalid"):
        state_intent(context, draft)


@pytest.mark.parametrize("dependency", ["none", "unresolved"])
def test_singleton_reference_cannot_change_dependency_decision(context, dependency):
    context, (chosen, _) = state_context(context)
    with pytest.raises(CoreConflict, match="evaluation_state_intent_contract"):
        state_intent(context, proposal(context, candidates=(chosen,), dependency=dependency))


def test_new_topic_shift_is_not_converted_to_older_return(context):
    context, (chosen, _) = state_context(context)
    with pytest.raises(CoreConflict, match="evaluation_state_intent_contract"):
        state_intent(context, proposal(context, candidates=(chosen,), relation="shift"))


@pytest.mark.parametrize("mutation", ["put", "corrections"])
def test_state_reference_does_not_permit_proposed_state_mutations(context, mutation):
    context, (chosen, _) = state_context(context)
    draft = proposal(context, candidates=(chosen,))
    value = (
        StateValue(id=uuid4(), kind="entity", key="new", value="Orchid")
        if mutation == "put"
        else StateCorrection(item_id=chosen.state_item_id, mention=mention(context))
    )
    with pytest.raises(CoreConflict, match="evaluation_state_intent_contract"):
        state_intent(context, draft.model_copy(update={mutation: (value,)}))


def test_inactive_state_and_correction_group_are_not_recovered_by_a_reference(context):
    context, (chosen, _) = state_context(context)
    previous = context.previous
    retired = state_step(
        context.request.scope,
        previous,
        deactivate=(chosen.state_item_id,),
        relations=(
            HistoryRelation(target=chosen.source, kind="correction", state_item_ids=(chosen.state_item_id,)),
        ),
    )
    context = context.model_copy(
        update={
            "request": context.request.model_copy(update={"expected_head": retired.id}),
            "previous": retired,
            "history": HistorySelection(
                head=retired.id, state_projection=project_state(retired.state, context.request.scope)
            ),
        }
    )
    with pytest.raises(CoreConflict, match="evaluation_state_intent_origin_invalid"):
        state_intent(context, proposal(context, candidates=(chosen,)))
    current = source(context.request.scope).model_copy(update={"acceptance": retired})
    old = source(context.request.scope).model_copy(update={"acceptance": previous})
    context = with_sources(context, (old, current), retired)
    with pytest.raises(CoreConflict):
        state_intent(context, proposal(context, candidates=(chosen,)))


def test_singleton_candidate_does_not_synthesize_or_silently_change_rewrite(context):
    context, (chosen, _) = state_context(context)
    draft = proposal(context, candidates=(chosen,))
    for rewrite in (None, draft.rewrite.model_copy(update={"text": "Invented query"})):
        with pytest.raises(CoreConflict):
            state_intent(context, draft.model_copy(update={"rewrite": rewrite}))


@pytest.mark.parametrize("at_head", [False, True])
@pytest.mark.parametrize("with_reference", [False, True])
def test_active_pending_ambiguity_precedes_an_omitted_draft_ambiguity(context, at_head, with_reference):
    context, (chosen, _) = state_context(context)
    pending = state_step(
        context.request.scope,
        context.previous,
        put=(StateValue(id=uuid4(), kind="ambiguity", key="pending", value="unresolved subject"),),
    )
    latest = pending if at_head else state_step(context.request.scope, pending)
    context = context.model_copy(
        update={
            "request": context.request.model_copy(update={"expected_head": latest.id}),
            "previous": latest,
            "history": HistorySelection(
                head=latest.id, state_projection=project_state(latest.state, context.request.scope)
            ),
        }
    )
    if with_reference:
        draft = proposal(context, candidates=(chosen,))
    else:
        draft = proposal(context, facts=(chosen,)).model_copy(update={"references": ()})
    assert draft.ambiguities == ()
    assert any(e.item.kind == "ambiguity" and e.active for e in context.history.state_projection)
    before = latest.model_dump(mode="json")
    with pytest.raises(CoreConflict, match="evaluation_state_intent_contract"):
        state_intent(context, draft)
    assert latest.model_dump(mode="json") == before


def replacement_context(context):
    context, (chosen, unaffected) = state_context(context)
    replacement = StateValue(
        id=uuid4(), kind="entity", key="subject", value="Orchid revised", replaces=(chosen.state_item_id,)
    )
    latest = state_step(
        context.request.scope,
        context.previous,
        put=(replacement,),
        relations=(
            HistoryRelation(target=chosen.source, kind="correction", state_item_ids=(chosen.state_item_id,)),
        ),
    )
    context = context.model_copy(
        update={
            "request": context.request.model_copy(update={"expected_head": latest.id}),
            "previous": latest,
            "history": HistorySelection(
                head=latest.id, state_projection=project_state(latest.state, context.request.scope)
            ),
        }
    )
    entry = next(e for e in context.history.state_projection if e.item.id == replacement.id)
    fact = IntentFact(
        kind=entry.item.kind, value=entry.item.value, source=entry.introduced_by, state_item_id=entry.item.id
    )
    return context, fact, unaffected


@pytest.mark.parametrize("with_reference", [False, True])
def test_used_replacement_state_cannot_substitute_for_a_missing_raw_correction_group(context, with_reference):
    context, replacement, _ = replacement_context(context)
    assert context.history.selected == () and context.history.failure is None
    if with_reference:
        draft = proposal(context, candidates=(replacement,))
    else:
        draft = proposal(context, facts=(replacement,)).model_copy(update={"references": ()})
    with pytest.raises(CoreConflict, match="evaluation_state_intent_correction_group_required"):
        state_intent(context, draft)


def test_unused_replacement_state_does_not_block_an_unaffected_ordinary_state_origin(context):
    context, replacement, unaffected = replacement_context(context)
    assert any(
        e.item.id == replacement.state_item_id and e.item.replaces for e in context.history.state_projection
    )
    before = context.previous.model_dump(mode="json")
    draft = proposal(context, candidates=(unaffected,))
    decision = state_intent(context, draft)
    assert decision.mode == "USE_REWRITE" and decision.selected_query == context.request.question + "\nLinden"
    assert decision.facts == (unaffected,) and decision.bindings == draft.references
    assert decision.sources == () and intent_context(context, decision)[0] == ()
    assert tuple(e.item.id for e in intent_context(context, decision)[1]) == (unaffected.state_item_id,)
    assert context.previous.model_dump(mode="json") == before
