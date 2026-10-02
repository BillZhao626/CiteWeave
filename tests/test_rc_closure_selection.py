"""Selection/provenance neighbors and immutable successful interpretation replay.

These prove representation safety only; they do not assign Human quality labels.
"""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_conversation_history import source, state_step
from test_conversation_interpretation import context as context
from test_conversation_interpretation import with_sources

from citeweave.conversation_contract import CoreConflict, HistoryRelation, ResolvedSignals, StateValue
from citeweave.conversation_history import HistorySource
from citeweave.conversation_interpretation import InterpretationInput, interpret
from citeweave.evaluation.dev_state import state_intent
from citeweave.runtime_rc_closure import decision_context, decode_closure

ROOT = Path(__file__).resolve().parents[1]
FACT_CAP = 399616


def wire(facts=(), **fields):
    value = dict(topic_relation="continue", dependency="required", facts=list(facts))
    value.update(fields)
    return value


def decode(context, value):
    return decode_closure(json.dumps(value), context, fact_bytes_cap=FACT_CAP)


def state_fact(value, item_id=None):
    origin = dict(type="state")
    if item_id is not None:
        origin["state_item_id"] = str(item_id)
    return dict(kind="entity", value=value, origin=origin)


def task_fact(origin=None):
    return dict(kind="task", value="orchard-test", origin=origin or dict(type="current"))


def set_signals(accepted, signals):
    return accepted.model_copy(
        update={
            "state": accepted.state.model_copy(
                update={"delta": accepted.state.delta.model_copy(update={"signals": signals})}
            )
        }
    )


def choice_context(context, *, pending):
    scope = context.request.scope
    items = tuple(
        StateValue(id=uuid4(), kind="entity", key=key, value=value)
        for key, value in (("one", "Orchid"), ("two", "Linden"))
    )
    signals = ResolvedSignals(task="orchard-test", entities=("Orchid", "Linden"))
    first = set_signals(state_step(scope, put=items), signals)
    accepted = [first]
    if pending:
        second = set_signals(
            state_step(
                scope,
                first,
                put=(StateValue(id=uuid4(), kind="ambiguity", key="choice", value="unresolved unit"),),
            ),
            ResolvedSignals(task="orchard-test"),
        )
        accepted.append(second)
    sources = tuple(
        HistorySource(
            acceptance=a,
            request=context.request.model_copy(update={"expected_head": None if a is first else first.id}),
            origins=("explicit",),
        )
        for a in accepted
    )
    context = with_sources(context, sources, accepted[-1])
    question = (
        "For orchard-test, I mean Linden: which indicator should it show?"
        if pending
        else "For orchard-test, which indicator should it show?"
    )
    return context.model_copy(
        update={"request": context.request.model_copy(update={"question": question})}
    ), items


def test_available_origins_distinguish_task_signals_from_entity_state(context):
    context, _ = choice_context(context, pending=False)
    catalog = decision_context(context)["origin_catalog"]
    task_origins = [e for e in catalog if e["kind"] == "task" and e["value"] == "orchard-test"]
    assert any(e["type"] == "history" and e["available_origins"] for e in task_origins)
    assert not any(e["type"] == "state" for e in task_origins)
    for value in ("Orchid", "Linden"):
        assert any(e["kind"] == "entity" and e["value"] == value and e["type"] == "state" for e in catalog)
    assert not decision_context(context)["same_task_pending_selection"]


def test_wrong_task_state_id_is_rejected_even_when_clarification_is_intended(context):
    context, items = choice_context(context, pending=False)
    references = [
        dict(
            mention=dict(quote="it"),
            candidates=[state_fact(item.value, item.id) for item in items],
        )
    ]
    good = wire([task_fact()], references=references, entity_mode="alternatives")
    result = interpret(context, draft=decode(context, good))
    assert result.mode == "CLARIFY" and result.selected_query is None
    assert result.control_result.kind == "clarification"
    assert {f.value for a in result.ambiguities for f in a.candidates} == {"Orchid", "Linden"}
    bad = wire(
        [task_fact(dict(type="state", state_item_id=str(items[0].id)))],
        references=references,
        entity_mode="alternatives",
    )
    with pytest.raises(CoreConflict, match="origin_unavailable_or_ambiguous"):
        decode(context, bad)
    with pytest.raises(CoreConflict, match="rewrite_required"):
        interpret(context, draft=decode(context, wire([task_fact()])))


def test_wrong_candidate_origin_cannot_hide_behind_an_unresolved_reference(context):
    context, items = choice_context(context, pending=False)
    candidates = [state_fact(items[0].value, items[0].id), state_fact(items[1].value, items[0].id)]
    bad = wire(references=[dict(mention=dict(quote="it"), candidates=candidates)])
    with pytest.raises(CoreConflict, match="origin_unavailable_or_ambiguous"):
        decode(context, bad)


def test_explicit_same_task_selection_uses_continue_and_clears_only_stale_ambiguity(context):
    context, _ = choice_context(context, pending=True)
    assert decision_context(context)["same_task_pending_selection"]
    resolution = dict(ambiguity_key="choice", selection=state_fact("Linden"))
    value = wire([task_fact()], resolutions=[resolution], entity_mode="single")
    result = interpret(context, draft=decode(context, value))
    pending = next(e for e in context.history.state_projection if e.item.kind == "ambiguity")
    assert result.mode == "USE_REWRITE" and result.topic_relation == "continue"
    assert result.delta.signals.entities == ("Linden",)
    assert result.delta.deactivate == (pending.item.id,)
    assert result.selected_query == context.request.question + "\nLinden"
    assert not result.ambiguities
    assert any(r.kind == "correction" and pending.item.id in r.state_item_ids for r in result.delta.relations)
    value["ambiguities"] = [dict(reason="unresolved_intent")]
    unresolved = interpret(context, draft=decode(context, value))
    assert unresolved.mode == "CLARIFY" and unresolved.selected_query is None


@pytest.mark.parametrize("topic", ["return", "shift"])
def test_combined_transition_and_selection_remains_rejected_without_semantic_rewriting(context, topic):
    context, _ = choice_context(context, pending=True)
    value = wire(
        [task_fact()],
        topic_relation=topic,
        resolutions=[dict(ambiguity_key="choice", selection=state_fact("Linden"))],
    )
    draft = decode(context, value)
    assert draft.topic_relation == topic
    with pytest.raises(CoreConflict, match="shift_correction_requires_separate_resolution"):
        interpret(context, draft=draft)


@pytest.mark.parametrize(
    "fault", ["missing_key", "missing_current_selection", "wrong_id", "wrong_source", "joint"]
)
def test_explicit_selection_does_not_invent_an_origin_or_current_choice(context, fault):
    context, items = choice_context(context, pending=True)
    selection = state_fact("Linden")
    value = wire([task_fact()], resolutions=[dict(ambiguity_key="choice", selection=selection)])
    if fault == "missing_key":
        value["resolutions"][0]["ambiguity_key"] = "nonexistent"
    elif fault == "missing_current_selection":
        selection["value"] = "Orchid"
    elif fault == "wrong_id":
        selection["origin"]["state_item_id"] = str(items[0].id)
    elif fault == "wrong_source":
        selection["origin"]["source"] = dict(acceptance_id=str(UUID(int=0)), turn_id=str(UUID(int=0)))
    else:
        value["entity_mode"] = "joint"
    with pytest.raises(CoreConflict):
        decode(context, value)


def test_ambiguous_state_mapping_requires_a_real_unique_item_identity(context):
    items = tuple(StateValue(id=uuid4(), kind="entity", key=k, value="Orchid") for k in ("one", "two"))
    accepted = state_step(context.request.scope, put=items)
    src = HistorySource(acceptance=accepted, request=context.request, origins=("explicit",))
    context = with_sources(context, (src,), accepted)
    assert any(
        e["kind"] == "entity"
        and e["value"] == "Orchid"
        and e["type"] == "state"
        and e["available_origins"] == 2
        for e in decision_context(context)["origin_catalog"]
    )
    with pytest.raises(CoreConflict, match="origin_unavailable_or_ambiguous"):
        decode(context, wire([state_fact("Orchid")]))
    result = interpret(context, draft=decode(context, wire([state_fact("Orchid", items[0].id)])))
    assert result.mode == "USE_REWRITE"
    assert result.facts[0].state_item_id == items[0].id


def test_repeated_explicit_selection_requires_a_real_current_occurrence(context):
    context, _ = choice_context(context, pending=True)
    context = context.model_copy(
        update={"request": context.request.model_copy(update={"question": "Use Linden, repeat Linden."})}
    )
    value = wire(resolutions=[dict(ambiguity_key="choice", selection=state_fact("Linden"))])
    with pytest.raises(CoreConflict, match="localization_ambiguous"):
        decode(context, value)
    value["resolutions"][0]["occurrence"] = 1
    assert interpret(context, draft=decode(context, value)).mode == "USE_REWRITE"


def test_duplicate_json_fields_cannot_choose_a_different_semantic_decision(context):
    raw = '{"topic_relation":"continue","topic_relation":"shift","dependency":"none"}'
    with pytest.raises(CoreConflict, match="reconciliation_json"):
        decode_closure(raw, context, fact_bytes_cap=FACT_CAP)


def test_duplicate_history_signal_does_not_gain_a_guessed_source(context):
    sources = tuple(
        source(context.request.scope, i, signals=ResolvedSignals(entities=("Orchid",))) for i in (1, 2)
    )
    context = with_sources(context, sources)
    fact = dict(kind="entity", value="Orchid", origin=dict(type="history"))
    with pytest.raises(CoreConflict, match="origin_unavailable_or_ambiguous"):
        decode(context, wire([fact]))
    fact["origin"]["source"] = sources[0].ref.model_dump(mode="json")
    assert interpret(context, draft=decode(context, wire([fact]))).mode == "USE_REWRITE"


def test_superseded_state_item_cannot_be_selected_from_its_old_snapshot(context):
    old = StateValue(id=uuid4(), kind="entity", key="unit", value="Orchid")
    first = state_step(context.request.scope, put=(old,))
    new = StateValue(id=uuid4(), kind="entity", key="unit", value="Linden", replaces=(old.id,))
    second = state_step(
        context.request.scope,
        first,
        put=(new,),
        relations=(HistoryRelation(target=first.state.source, kind="correction"),),
    )
    sources = tuple(
        HistorySource(
            acceptance=a,
            request=context.request.model_copy(update={"expected_head": None if a is first else first.id}),
            origins=("explicit",),
        )
        for a in (first, second)
    )
    context = with_sources(context, sources, second)
    with pytest.raises(CoreConflict, match="origin_unavailable_or_ambiguous"):
        decode(context, wire([state_fact("Orchid", old.id)]))
    assert (
        interpret(context, draft=decode(context, wire([state_fact("Linden", new.id)]))).mode == "USE_REWRITE"
    )


@pytest.mark.parametrize(
    "key",
    [
        "D3.V1:cp-a-v1",
        "D3.V1:cp-ab0-v1",
        "D3.V2:cp-ab0-v1",
        "D4.V1:cp-a-v1",
        "D4.V2:cp-ab0-v1",
    ],
)
def test_preserved_return_correction_and_selection_interpretations_remain_exact(key):
    path = ROOT / ".runtime/evaluation/reconciliation/execution-reconciliation.json"
    if not path.exists():
        pytest.skip("immutable local reconciled receipt absent")
    case = next(c for c in json.loads(path.read_bytes())["cases"] if c["case_id"] == key)
    result = case["result"]
    context = InterpretationInput.model_validate(result["target_context"]["input"])
    draft = decode_closure(result["provider_outputs"]["interpretation"], context, fact_bytes_cap=FACT_CAP)
    output = (
        state_intent(context, draft)
        if result["target_context"]["state_only"]
        else interpret(context, draft=draft)
    )
    assert output.model_dump(mode="json") == result["result"]["interpretation"]
