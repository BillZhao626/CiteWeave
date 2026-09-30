"""Original synthetic drafts test structural safety, never model quality."""

from uuid import UUID, uuid4

import pytest
from test_conversation_history import source, state_step

from citeweave.conversation_contract import (
    Admission,
    CoreConflict,
    HistoryRelation,
    ResolvedSignals,
    Scope,
    StateValue,
)
from citeweave.conversation_history import HistoryQuery, HistorySelection, project_state, select_history
from citeweave.conversation_interpretation import (
    CriticalTerm,
    FakeInterpreter,
    IntentFact,
    InterpretationDraft,
    InterpretationInput,
    ReferenceDraft,
    RetrievalRewrite,
    StateCorrection,
    TextSpan,
    interpret,
)


@pytest.fixture
def context():
    scope = Scope(kb_id=uuid4(), version_ids=(uuid4(),))
    return InterpretationInput(
        conversation_id=UUID(int=999),
        turn_id=uuid4(),
        request=Admission(question="Explain it; not X, in 2024, only C.", scope=scope, expected_head=None),
        history=HistorySelection(head=None),
    )


def span(context, text):
    start = context.request.question.index(text)
    return TextSpan(start=start, end=start + len(text))


def with_sources(context, sources, previous=None):
    head = previous.id if previous else None
    projection = project_state(previous.state, context.request.scope) if previous else ()
    history = select_history(
        sources,
        HistoryQuery(scope=context.request.scope, expected_head=head, explicit=tuple(s.ref for s in sources)),
        projection,
    )
    return context.model_copy(
        update={
            "request": context.request.model_copy(update={"expected_head": head}),
            "history": history,
            "previous": previous,
        }
    )


def completion(context, *, topic="continue"):
    old = source(
        context.request.scope, signals=ResolvedSignals(entities=("Device A",)), origins=("explicit",)
    )
    context = with_sources(context, (old,))
    fact = IntentFact(kind="entity", value="Device A", source=old.ref)
    draft = InterpretationDraft(
        topic_relation=topic,
        dependency="required",
        references=(ReferenceDraft(mention=span(context, "it"), candidates=(fact,)),),
        rewrite=RetrievalRewrite(text=context.request.question + "\nDevice A", scope=context.request.scope),
    )
    return context, draft, fact


def test_raw_text_never_claims_semantic_skip(context):
    with pytest.raises(CoreConflict, match="interpretation_required"):
        interpret(context)


def test_original_without_dependency_does_not_inherit_recent_history(context):
    old = source(context.request.scope, signals=ResolvedSignals(constraints=("unrelated",)))
    context = with_sources(context, (old,))
    draft = InterpretationDraft(topic_relation="shift", dependency="none")
    fake = FakeInterpreter(draft=draft)
    result = interpret(context, interpreter=fake)
    assert result.mode == "USE_ORIGINAL" and result.selected_query == context.request.question
    assert result.sources == () and result.delta.signals == ResolvedSignals()
    assert result.guard_outcome == "STRUCTURAL_ONLY" and fake.calls == 1
    assert result.authority == "contextual_intent_not_evidence"


@pytest.mark.parametrize("topic", ["continue", "return"])
def test_unique_binding_rewrite_retains_original_and_B_source(context, topic):
    context, draft, fact = completion(context, topic=topic)
    result = interpret(context, draft=draft)
    assert result.mode == "USE_REWRITE"
    assert result.original_question == context.request.question
    assert result.proposed_rewrite == result.selected_query == draft.rewrite.text
    assert result.bindings[0].candidates == (fact,) and result.topic_relation == topic
    assert result.sources == (fact.source,) and result.delta.signals.entities == (fact.value,)
    assert result.delta.relations == (HistoryRelation(target=fact.source, kind="dependency"),)
    assert result.delta_identity and result.control_result is None


def test_multiple_valid_candidates_clarify_without_guessed_state(context):
    first = source(context.request.scope, signals=ResolvedSignals(entities=("A", "B")))
    context = with_sources(context, (first,))
    facts = tuple(IntentFact(kind="entity", value=v, source=first.ref) for v in ("A", "B"))
    result = interpret(
        context,
        draft=InterpretationDraft(
            topic_relation="continue",
            dependency="required",
            references=(ReferenceDraft(mention=span(context, "it"), candidates=facts),),
            put=(StateValue(id=uuid4(), kind="entity", key="guess", value="A"),),
        ),
    )
    assert result.mode == "CLARIFY" and result.selected_query is None
    assert result.bindings == () and result.ambiguities[0].candidates == facts
    assert result.control_result.kind == "clarification"
    assert all(v.kind == "ambiguity" for v in result.delta.put)
    assert result.delta.signals == ResolvedSignals()


def test_unresolved_reference_is_typed_clarification(context):
    result = interpret(
        context,
        draft=InterpretationDraft(
            topic_relation="continue",
            dependency="unresolved",
            references=(ReferenceDraft(mention=span(context, "it")),),
        ),
    )
    assert result.mode == "CLARIFY" and result.ambiguities[0].reason == "unresolved_reference"


@pytest.mark.parametrize(
    "dimension,value",
    [
        ("entity", "X"),
        ("document", "C"),
        ("version", "2024"),
        ("time", "2024"),
        ("negation", "not"),
        ("constraint", "only C"),
    ],
)
def test_critical_markers_cannot_be_dropped_or_changed(context, dimension, value):
    context, draft, _ = completion(context)
    required = CriticalTerm(dimension=dimension, value=value)
    context = context.model_copy(update={"required": (required,)})
    good = draft.rewrite.model_copy(update={"retained": (required,)})
    assert interpret(context, draft=draft.model_copy(update={"rewrite": good})).mode == "USE_REWRITE"
    for bad in (draft.rewrite, good.model_copy(update={"text": good.text.replace(value, "drift")})):
        with pytest.raises(CoreConflict, match="rewrite_fidelity"):
            interpret(context, draft=draft.model_copy(update={"rewrite": bad}))


def test_scope_widening_and_unattributed_prose_fail_closed(context):
    context, draft, _ = completion(context)
    wide = Scope(
        kb_id=context.request.scope.kb_id, version_ids=context.request.scope.version_ids + (uuid4(),)
    )
    for rewrite, reason in (
        (draft.rewrite.model_copy(update={"scope": wide}), "rewrite_scope"),
        (
            draft.rewrite.model_copy(update={"text": draft.rewrite.text + " is factually true"}),
            "rewrite_fidelity",
        ),
    ):
        with pytest.raises(CoreConflict, match=reason):
            interpret(context, draft=draft.model_copy(update={"rewrite": rewrite}))


@pytest.mark.parametrize("fault", ["source", "turn", "value", "conversation", "scope"])
def test_invalid_binding_is_failure_not_a_guessed_fallback(context, fault):
    context, draft, fact = completion(context)
    if fault in {"source", "turn"}:
        field = "acceptance_id" if fault == "source" else "turn_id"
        fact = fact.model_copy(update={"source": fact.source.model_copy(update={field: uuid4()})})
    elif fault == "value":
        fact = fact.model_copy(update={"value": "fabricated"})
    else:
        src = context.history.selected[0].sources[0]
        if fault == "conversation":
            src = src.model_copy(
                update={"acceptance": src.acceptance.model_copy(update={"conversation_id": uuid4()})}
            )
        else:
            src = src.model_copy(
                update={
                    "request": src.request.model_copy(
                        update={"scope": Scope(kb_id=uuid4(), version_ids=(uuid4(),))}
                    )
                }
            )
        group = context.history.selected[0].model_copy(update={"sources": (src,)})
        context = context.model_copy(
            update={"history": context.history.model_copy(update={"selected": (group,)})}
        )
    draft = draft.model_copy(
        update={"references": (ReferenceDraft(mention=span(context, "it"), candidates=(fact,)),)}
    )
    with pytest.raises(CoreConflict):
        interpret(context, draft=draft)


def test_superseded_history_cannot_bind_even_with_forged_group_flags(context):
    old = source(context.request.scope, signals=ResolvedSignals(entities=("A",)))
    new = source(context.request.scope, 2, relations=(HistoryRelation(target=old.ref, kind="correction"),))
    context = with_sources(context, (old, new))
    group = context.history.selected[0].model_copy(update={"superseded": ()})
    context = context.model_copy(
        update={"history": context.history.model_copy(update={"selected": (group,)})}
    )
    with pytest.raises(CoreConflict, match="superseded"):
        interpret(
            context,
            draft=InterpretationDraft(
                topic_relation="continue",
                dependency="required",
                facts=(IntentFact(kind="entity", value="A", source=old.ref),),
            ),
        )


def test_incomplete_history_is_failure_not_clarification(context):
    context = context.model_copy(update={"history": HistorySelection(head=None, search_incomplete=True)})
    with pytest.raises(CoreConflict, match="history_unavailable"):
        interpret(context, draft=InterpretationDraft(topic_relation="shift", dependency="none"))


def test_shift_deactivates_old_state_without_deleting_history(context):
    item = StateValue(id=uuid4(), kind="constraint", key="old", value="unrelated")
    previous = state_step(context.request.scope, put=(item,))
    src = source(context.request.scope).model_copy(update={"acceptance": previous})
    context = with_sources(context, (src,), previous)
    result = interpret(context, draft=InterpretationDraft(topic_relation="shift", dependency="none"))
    assert result.mode == "USE_ORIGINAL" and result.delta.deactivate == (item.id,)
    assert previous.state.entries[0].active and result.delta.signals.constraints == ()


def test_explicit_correction_reuses_reducer_and_never_reactivates_old(context):
    old = StateValue(id=uuid4(), kind="entity", key="device", value="A")
    previous = state_step(context.request.scope, put=(old,))
    src = source(context.request.scope).model_copy(update={"acceptance": previous})
    context = with_sources(context, (src,), previous)
    fact = IntentFact(kind="entity", value="X", span=span(context, "X"))
    new = StateValue(id=uuid4(), kind="entity", key="device", value="X", replaces=(old.id,))
    result = interpret(
        context,
        draft=InterpretationDraft(
            topic_relation="continue",
            dependency="none",
            facts=(fact,),
            put=(new,),
            corrections=(StateCorrection(item_id=old.id, mention=span(context, "X")),),
        ),
    )
    from citeweave.conversation_contract import SourceRef
    from citeweave.conversation_history import reduce_state

    state = reduce_state(
        previous,
        SourceRef(acceptance_id=uuid4(), turn_id=context.turn_id),
        context.request.scope,
        result.delta,
    )
    assert not state.entries[0].active and state.entries[1].active
    assert state.entries[1].item.value == "X"


def test_unsafe_unnecessary_rewrite_prefers_original(context):
    result = interpret(
        context,
        draft=InterpretationDraft(
            topic_relation="shift",
            dependency="none",
            rewrite=RetrievalRewrite(text="unnecessary drift", scope=context.request.scope),
        ),
    )
    assert result.mode == "USE_ORIGINAL" and result.selected_query == context.request.question
    assert result.proposed_rewrite == "unnecessary drift"


def test_missing_required_completion_never_silently_uses_original(context):
    context, draft, _ = completion(context)
    with pytest.raises(CoreConflict, match="rewrite_required"):
        interpret(context, draft=draft.model_copy(update={"rewrite": None}))


def state_context(context, previous, *earlier):
    sources = tuple(
        source(context.request.scope).model_copy(update={"acceptance": a}) for a in (*earlier, previous)
    )
    return with_sources(context, sources, previous)


def publish_local(context, result):
    from datetime import datetime, timezone

    from citeweave.conversation_contract import Acceptance, ProducedResult, SourceRef
    from citeweave.conversation_history import reduce_state

    ref = SourceRef(acceptance_id=uuid4(), turn_id=context.turn_id)
    return Acceptance(
        id=ref.acceptance_id,
        turn_id=ref.turn_id,
        conversation_id=context.conversation_id,
        run_id=uuid4(),
        result=result.control_result or ProducedResult(kind="evidence_insufficient", text="Fixture"),
        state=reduce_state(context.previous, ref, context.request.scope, result.delta),
        created_at=datetime.now(timezone.utc),
    )


def test_ambiguity_is_durable_and_later_resolution_clears_it(context):
    unresolved = interpret(
        context, draft=InterpretationDraft(topic_relation="continue", dependency="unresolved")
    )
    previous = publish_local(context, unresolved)
    context = state_context(context.model_copy(update={"turn_id": uuid4()}), previous)
    no_resolution = InterpretationDraft(topic_relation="continue", dependency="none")
    assert interpret(context, draft=no_resolution).mode == "CLARIFY"
    fact = IntentFact(kind="entity", value="X", span=span(context, "X"))
    resolved = interpret(
        context,
        draft=no_resolution.model_copy(
            update={
                "facts": (fact,),
                "corrections": (
                    StateCorrection(item_id=previous.state.entries[0].item.id, mention=span(context, "X")),
                ),
                "put": (StateValue(id=uuid4(), kind="entity", key="device", value="X"),),
            }
        ),
    )
    after = publish_local(context, resolved)
    assert [e.item.kind for e in project_state(after.state, context.request.scope)] == ["entity"]


def test_return_can_revalidate_shift_retired_topic_but_not_user_correction(context):
    fact = IntentFact(kind="topic", value="X", span=span(context, "X"))
    initial = interpret(
        context,
        draft=InterpretationDraft(
            topic_relation="shift",
            dependency="none",
            facts=(fact,),
            put=(StateValue(id=uuid4(), kind="topic", key="topic", value="X"),),
        ),
    )
    first = publish_local(context, initial)
    context = state_context(context.model_copy(update={"turn_id": uuid4()}), first)
    shifted = interpret(context, draft=InterpretationDraft(topic_relation="shift", dependency="none"))
    second = publish_local(context, shifted)
    assert not second.state.entries[0].active
    context = state_context(context.model_copy(update={"turn_id": uuid4()}), second, first)
    old = IntentFact(kind="topic", value="X", source=first.state.source)
    draft = InterpretationDraft(
        topic_relation="return",
        dependency="required",
        facts=(old,),
        rewrite=RetrievalRewrite(text=context.request.question + "\nX", scope=context.request.scope),
    )
    assert interpret(context, draft=draft).mode == "USE_REWRITE"
    with pytest.raises(CoreConflict, match="inactive_topic_requires_return"):
        interpret(context, draft=draft.model_copy(update={"topic_relation": "continue"}))


def test_active_state_binding_and_item_specific_correction(context):
    old = StateValue(id=uuid4(), kind="entity", key="device", value="A")
    keep = StateValue(id=uuid4(), kind="constraint", key="limit", value="only C")
    first = state_step(context.request.scope, put=(old, keep))
    second = state_step(
        context.request.scope,
        first,
        deactivate=(old.id,),
        relations=(HistoryRelation(target=first.state.source, kind="correction", state_item_ids=(old.id,)),),
    )
    context = state_context(context, second, first)
    fact = IntentFact(kind="constraint", value="only C", source=first.state.source, state_item_id=keep.id)
    draft = InterpretationDraft(
        topic_relation="continue",
        dependency="required",
        facts=(fact,),
        rewrite=RetrievalRewrite(text=context.request.question + "\nonly C", scope=context.request.scope),
    )
    assert interpret(context, draft=draft).mode == "USE_REWRITE"
    for invalid in (
        fact.model_copy(update={"state_item_id": None}),
        IntentFact(kind="entity", value="A", source=first.state.source, state_item_id=old.id),
    ):
        with pytest.raises(CoreConflict, match="superseded"):
            interpret(context, draft=draft.model_copy(update={"facts": (invalid,)}))


def test_same_draft_cannot_correct_and_reactivate_old_binding(context):
    old = StateValue(id=uuid4(), kind="entity", key="device", value="A")
    previous = state_step(context.request.scope, put=(old,))
    context = state_context(context, previous)
    inherited = IntentFact(kind="entity", value="A", source=previous.state.source, state_item_id=old.id)
    with pytest.raises(CoreConflict, match="corrected_binding_cannot_reactivate"):
        interpret(
            context,
            draft=InterpretationDraft(
                topic_relation="continue",
                dependency="required",
                facts=(inherited,),
                corrections=(StateCorrection(item_id=old.id, mention=span(context, "X")),),
                rewrite=RetrievalRewrite(text=context.request.question + "\nA", scope=context.request.scope),
            ),
        )


@pytest.mark.parametrize("fault", ["head", "projection", "span", "state", "shift", "none"])
def test_conflicting_contracts_fail_closed(context, fault):
    context, draft, fact = completion(context)
    if fault == "head":
        context = context.model_copy(update={"history": context.history.model_copy(update={"head": uuid4()})})
    elif fault == "projection":
        previous = state_step(
            context.request.scope, put=(StateValue(id=uuid4(), kind="entity", key="x", value="X"),)
        )
        context = state_context(context, previous)
        context = context.model_copy(
            update={"history": context.history.model_copy(update={"state_projection": ()})}
        )
    elif fault == "span":
        draft = draft.model_copy(
            update={"facts": (IntentFact(kind="entity", value="fabricated", span=span(context, "X")),)}
        )
    elif fault == "state":
        draft = draft.model_copy(
            update={"put": (StateValue(id=uuid4(), kind="entity", key="x", value="fabricated"),)}
        )
    else:
        draft = draft.model_copy(update={"topic_relation" if fault == "shift" else "dependency": fault})
    with pytest.raises(CoreConflict):
        interpret(context, draft=draft)


def test_same_mention_two_separate_bindings_cannot_bypass_ambiguity(context):
    old = source(context.request.scope, signals=ResolvedSignals(entities=("A", "B")))
    context = with_sources(context, (old,))
    draft = InterpretationDraft(
        topic_relation="continue",
        dependency="required",
        references=tuple(
            ReferenceDraft(
                mention=span(context, "it"), candidates=(IntentFact(kind="entity", value=v, source=old.ref),)
            )
            for v in ("A", "B")
        ),
    )
    result = interpret(context, draft=draft)
    assert result.mode == "CLARIFY" and len(result.ambiguities[0].candidates) == 2


def test_shift_cannot_disguise_explicit_correction_as_recoverable_retirement(context):
    previous = state_step(
        context.request.scope, put=(StateValue(id=uuid4(), kind="entity", key="e", value="A"),)
    )
    context = state_context(context, previous)
    with pytest.raises(CoreConflict, match="shift_correction_requires_separate_resolution"):
        interpret(
            context,
            draft=InterpretationDraft(
                topic_relation="shift",
                dependency="none",
                corrections=(
                    StateCorrection(item_id=previous.state.entries[0].item.id, mention=span(context, "X")),
                ),
            ),
        )


def test_return_retires_unrelated_active_context(context):
    previous = state_step(
        context.request.scope, put=(StateValue(id=uuid4(), kind="constraint", key="new", value="unrelated"),)
    )
    old = source(context.request.scope, signals=ResolvedSignals(entities=("A",)), origins=("explicit",))
    current = source(context.request.scope).model_copy(update={"acceptance": previous})
    context = with_sources(context, (old, current), previous)
    draft = InterpretationDraft(
        topic_relation="return",
        dependency="required",
        facts=(IntentFact(kind="entity", value="A", source=old.ref),),
        rewrite=RetrievalRewrite(text=context.request.question + "\nA", scope=context.request.scope),
    )
    result = interpret(context, draft=draft)
    assert result.delta.deactivate == (previous.state.entries[0].item.id,)
