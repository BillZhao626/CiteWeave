"""Provider-free intent-path safety; these tests do not assign Human quality labels."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from test_conversation_history import source, state_step
from test_conversation_interpretation import context as context
from test_conversation_interpretation import with_sources

from citeweave.conversation_contract import CoreConflict, HistoryRelation, ResolvedSignals, StateValue
from citeweave.conversation_evidence import intent_context
from citeweave.conversation_history import HistorySelection, HistorySource, project_state
from citeweave.conversation_interpretation import InterpretationInput, interpret
from citeweave.evaluation.dev_state import state_intent
from citeweave.runtime_rc_closure import decision_context, decode_closure

ROOT = Path(__file__).resolve().parents[1]
FACT_BYTES_CAP = 399616


def wire(context, facts, *, relation="continue", dependency="required"):
    return decode_closure(
        json.dumps(dict(topic_relation=relation, dependency=dependency, facts=facts)),
        context,
        fact_bytes_cap=FACT_BYTES_CAP,
    )


def state_entity(value, **identities):
    return dict(kind="entity", value=value, origin=dict(type="state", **identities))


def task_signals(accepted, task, entity=None):
    signals = ResolvedSignals(task=task, topic=task, entities=(entity,) if entity else ())
    return accepted.model_copy(
        update={
            "state": accepted.state.model_copy(
                update={"delta": accepted.state.delta.model_copy(update={"signals": signals})}
            )
        }
    )


def intent_fixture(context, *, selected=True, same_focus=False):
    entity = StateValue(id=uuid4(), kind="entity", key="unit", value="Orchid cartridge")
    first = task_signals(state_step(context.request.scope, put=(entity,)), "packing", entity.value)
    latest = first if same_focus else task_signals(state_step(context.request.scope, first), "painting")
    question = "For packing inspection, how long must it cool, NOT before 4 days?"
    context = context.model_copy(
        update={"request": context.request.model_copy(update={"question": question})}
    )
    prior = HistorySource(
        acceptance=first,
        request=context.request.model_copy(
            update={"question": "Inspect Orchid cartridge", "expected_head": None}
        ),
        origins=("explicit",),
    )
    if selected:
        context = with_sources(context, (prior,), latest)
    else:
        # The explicitly supplied bounded State-only evaluation surface does not
        # claim a selected raw source or a recovered provenance group.
        context = context.model_copy(
            update={
                "request": context.request.model_copy(update={"expected_head": latest.id}),
                "previous": latest,
                "history": HistorySelection(
                    head=latest.id, state_projection=project_state(latest.state, context.request.scope)
                ),
            }
        )
    return context, entity, first


def supported_facts(entity):
    return [
        dict(kind="task", value="packing", origin=dict(type="current")),
        state_entity(entity.value),
        dict(kind="time", value="4 days", origin=dict(type="current")),
        dict(kind="negation", value="NOT", origin=dict(type="current")),
    ]


def test_state_only_return_uses_active_intent_without_reconstructing_raw_history(context):
    context, entity, first = intent_fixture(context, selected=False)
    assert context.history.selected == ()
    draft = wire(context, supported_facts(entity), relation="return")
    decision = state_intent(context, draft)
    history, state = intent_context(context, decision)
    assert decision.mode == "USE_REWRITE" and decision.topic_relation == "return"
    assert decision.selected_query == context.request.question + "\n" + entity.value
    assert history == () and tuple(e.item.id for e in state) == (entity.id,)
    assert state[0].introduced_by == first.state.source
    assert decision.sources == () and decision.delta.put == () and decision.delta.deactivate == ()
    assert decision.delta.relations == ()
    assert decision.authority == "contextual_intent_not_evidence"


def test_state_only_shift_with_required_inherited_entity_remains_fail_closed(context):
    context, entity, _ = intent_fixture(context, selected=False)
    draft = wire(context, [state_entity(entity.value)], relation="shift")
    with pytest.raises(CoreConflict, match="evaluation_state_intent_contract"):
        state_intent(context, draft)


@pytest.mark.parametrize("selected", [False, True])
def test_same_focus_continue_and_older_focus_return_remain_distinct(context, selected):
    continued, entity, _ = intent_fixture(context, selected=selected, same_focus=True)
    draft = wire(continued, supported_facts(entity))
    decision = interpret(continued, draft=draft) if selected else state_intent(continued, draft)
    assert decision.topic_relation == "continue"
    returned, entity, _ = intent_fixture(context, selected=selected)
    draft = wire(returned, supported_facts(entity), relation="return")
    decision = interpret(returned, draft=draft) if selected else state_intent(returned, draft)
    assert decision.topic_relation == "return" and "NOT before 4 days" in decision.selected_query
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        wire(returned, supported_facts(entity))


def test_independent_shift_does_not_silently_import_available_prior_state(context):
    context, entity, _ = intent_fixture(context)
    task = dict(kind="task", value="packing", origin=dict(type="current"))
    independent = interpret(context, draft=wire(context, [task], relation="shift", dependency="none"))
    assert independent.mode == "USE_ORIGINAL" and independent.selected_query == context.request.question
    assert independent.delta.deactivate == (entity.id,)
    assert intent_context(context, independent) == ((), ())
    returned = interpret(context, draft=wire(context, [task, state_entity(entity.value)], relation="return"))
    history, state = intent_context(context, returned)
    assert returned.selected_query == context.request.question + "\n" + entity.value
    assert returned.delta.deactivate == () and len(history) == 1
    assert tuple(e.item.id for e in state) == (entity.id,)
    with pytest.raises(CoreConflict, match="independent_query_inheritance"):
        interpret(
            context,
            draft=wire(context, [task, state_entity(entity.value)], relation="return", dependency="none"),
        )


def test_origin_catalog_exposes_available_pairs_without_inventing_state_task(context):
    context, entity, _ = intent_fixture(context)
    metadata = decision_context(context)
    catalog = metadata["origin_catalog"]
    assert dict(kind="entity", value=entity.value, type="state", available_origins=1) in catalog
    assert dict(kind="task", value="packing", type="history", available_origins=1) in catalog
    assert not any(o["kind"] == "task" and o["type"] == "state" for o in catalog)
    assert metadata["head_signals"]["task"] == "painting"
    missing_raw, _, _ = intent_fixture(context, selected=False)
    assert decision_context(missing_raw)["state_only_dependency_available"]
    assert not any(o["type"] == "history" for o in decision_context(missing_raw)["origin_catalog"])


@pytest.mark.parametrize("fault", ["kind", "value", "item_id", "source"])
def test_state_origin_catalog_never_licenses_unsupported_origin(context, fault):
    context, entity, _ = intent_fixture(context)
    fact = state_entity(entity.value)
    if fault == "kind":
        fact["kind"] = "task"
    elif fault == "value":
        fact["value"] = "Invented cartridge"
    elif fault == "item_id":
        fact["origin"]["state_item_id"] = str(uuid4())
    else:
        fact["origin"]["source"] = dict(acceptance_id=str(uuid4()), turn_id=str(uuid4()))
    with pytest.raises(CoreConflict, match="reconciliation_origin_unavailable_or_ambiguous"):
        wire(context, [fact], relation="return")


def test_correction_group_return_uses_active_replacement_and_cannot_reactivate_old(context):
    old = StateValue(id=uuid4(), kind="entity", key="release", value="Orchid amber")
    first = task_signals(state_step(context.request.scope, put=(old,)), "packing", old.value)
    replacement = StateValue(
        id=uuid4(), kind="entity", key=old.key, value="Orchid violet", replaces=(old.id,)
    )
    latest = task_signals(
        state_step(
            context.request.scope,
            first,
            put=(replacement,),
            relations=(
                HistoryRelation(target=first.state.source, kind="correction", state_item_ids=(old.id,)),
            ),
        ),
        "packing",
        replacement.value,
    )
    sources = tuple(
        source(context.request.scope).model_copy(update={"acceptance": a}) for a in (first, latest)
    )
    context = with_sources(context, sources, latest)
    decision = interpret(context, draft=wire(context, [state_entity(replacement.value)], relation="return"))
    assert decision.selected_query == context.request.question + "\n" + replacement.value
    assert decision.delta.signals.entities == (replacement.value,)
    history, state = intent_context(context, decision)
    assert len(history) == 2 and tuple(e.item.id for e in state) == (replacement.id,)
    with pytest.raises(CoreConflict, match="reconciliation_origin_unavailable_or_ambiguous"):
        wire(context, [state_entity(old.value)], relation="return")
    historical = dict(kind="entity", value=old.value, origin=dict(type="history"))
    with pytest.raises(CoreConflict, match="superseded"):
        interpret(context, draft=wire(context, [historical], relation="return"))
    with pytest.raises(CoreConflict, match="evaluation_state_intent_contract"):
        state_intent(context, wire(context, [state_entity(replacement.value)], relation="return"))


@pytest.fixture
def preserved():
    path = ROOT / ".runtime/evaluation/reconciliation/execution-reconciliation.json"
    if not path.exists():
        pytest.skip("immutable local reconciled receipts absent")
    return {c["case_id"]: c for c in json.loads(path.read_bytes())["cases"]}


def test_preserved_state_only_failure_is_not_repaired_after_decode(preserved):
    case = preserved["D1.V2:cp-a-v1"]
    context = InterpretationInput.model_validate(case["result"]["target_context"]["input"])
    raw = case["result"]["provider_outputs"]["interpretation"]
    draft = decode_closure(raw, context, fact_bytes_cap=FACT_BYTES_CAP)
    assert draft.topic_relation == "shift" and draft.dependency == "required"
    with pytest.raises(CoreConflict, match="evaluation_state_intent_contract"):
        state_intent(context, draft)
    chosen = context.history.state_projection[0]
    represented = wire(context, [state_entity(chosen.item.value)], relation="return")
    assert (
        state_intent(context, represented).selected_query
        == context.request.question + "\n" + chosen.item.value
    )


def test_preserved_ab0_omission_loses_intent_context_despite_present_documentary_evidence(preserved):
    case = preserved["D1.V2:cp-ab0-v1"]
    receipt = case["result"]
    context = InterpretationInput.model_validate(receipt["target_context"]["input"])
    draft = decode_closure(
        receipt["provider_outputs"]["interpretation"], context, fact_bytes_cap=FACT_BYTES_CAP
    )
    decision = interpret(context, draft=draft)
    assert decision.selected_query == receipt["result"]["interpretation"]["selected_query"]
    assert intent_context(context, decision) == ((), ())
    chosen = context.history.state_projection[0]
    documentary = json.loads(receipt["result"]["result"]["evidence_pack"]["prompt_json"])
    assert any(chosen.item.value in item["text"] for item in documentary["evidence"])
    represented = wire(context, [state_entity(chosen.item.value)], relation="return")
    represented_decision = interpret(context, draft=represented)
    history, state = intent_context(context, represented_decision)
    assert represented_decision.selected_query == context.request.question + "\n" + chosen.item.value
    assert len(history) == 1 and tuple(e.item.id for e in state) == (chosen.item.id,)


@pytest.mark.parametrize("key", ["D3.V1:cp-a-v1", "D3.V1:cp-ab0-v1", "D3.V2:cp-ab0-v1"])
def test_preserved_return_and_correction_interpretations_replay_exactly(preserved, key):
    case = preserved[key]
    context = InterpretationInput.model_validate(case["result"]["target_context"]["input"])
    draft = decode_closure(
        case["result"]["provider_outputs"]["interpretation"], context, fact_bytes_cap=FACT_BYTES_CAP
    )
    decision = (
        state_intent(context, draft)
        if case["result"]["target_context"]["state_only"]
        else interpret(context, draft=draft)
    )
    assert decision.model_dump(mode="json") == case["result"]["result"]["interpretation"]


def test_preserved_incomplete_correction_group_remains_zero_call_guard(preserved):
    case = preserved["D3.V2:cp-a-v1"]
    context = InterpretationInput.model_validate(case["result"]["target_context"]["input"])
    assert context.history.failure == "incomplete_group"
    assert not case["result"].get("provider_outputs") and not case["result"].get("request_evidence")
    assert case["result"]["result"]["guard"] == "incomplete_group"
