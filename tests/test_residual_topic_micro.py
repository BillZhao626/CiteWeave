"""Independent synthetic topic-boundary diagnostics plus immutable residual replay.

These fixtures prove a narrow structured normal form, not provider obedience,
documentary support, Human quality scores or measured History parameter optima.
"""

import copy
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_conversation_history import state_step
from test_conversation_interpretation import with_sources

from citeweave.conversation_contract import (
    Admission,
    CoreConflict,
    HistoryRelation,
    ResolvedSignals,
    Scope,
    StateValue,
)
from citeweave.conversation_evidence import intent_context
from citeweave.conversation_history import HistorySelection, HistorySource
from citeweave.conversation_interpretation import CriticalTerm, InterpretationInput, interpret
from citeweave.evaluation.dev_state import state_intent
from citeweave.runtime_rc_closure import decode_closure
from citeweave.runtime_reconciliation import decode_reconciled
from citeweave.runtime_residual_closure import decode_residual

ROOT = Path(__file__).resolve().parents[1]
CAP = 399616


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("residual_topic_micro_attempted_network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def task_step(scope, task, previous=None, *, put=(), deactivate=(), relations=(), entities=()):
    accepted = state_step(scope, previous, put=put, deactivate=deactivate, relations=relations)
    signals = ResolvedSignals(
        task=task,
        topic=task,
        entities=entities,
        constraints=tuple(item.value for item in put if item.kind == "constraint"),
    )
    return accepted.model_copy(
        update={
            "state": accepted.state.model_copy(
                update={"delta": accepted.state.delta.model_copy(update={"signals": signals})}
            )
        }
    )


def historical(accepted, scope, question):
    return HistorySource(
        acceptance=accepted,
        request=Admission(
            question=question,
            scope=scope,
            expected_head=accepted.state.delta.previous_snapshot_id,
        ),
        origins=("explicit",),
    )


def scenario(*, task="calibration", entity="Aurora spindle", extra_entity=False, head_put=()):
    scope = Scope(kb_id=uuid4(), version_ids=(uuid4(),))
    unit = StateValue(id=uuid4(), kind="entity", key="unit", value=entity)
    second = StateValue(id=uuid4(), kind="entity", key="alternative", value="Boreal sensor")
    initial = task_step(
        scope,
        task,
        put=(unit, second) if extra_entity else (unit,),
        entities=(unit.value, second.value) if extra_entity else (unit.value,),
    )
    latest = task_step(scope, "inventory", initial, put=head_put)
    context = InterpretationInput(
        conversation_id=UUID(int=999),
        turn_id=uuid4(),
        request=Admission(
            question=f"For {task}, what setting should it use, NOT before 6 hours?",
            scope=scope,
            expected_head=latest.id,
        ),
        history=HistorySelection(head=latest.id),
        previous=latest,
        required=(
            CriticalTerm(dimension="negation", value="NOT"),
            CriticalTerm(dimension="time", value="6 hours"),
        ),
    )
    older = historical(initial, scope, f"Inspect {entity} for {task}.")
    head = historical(latest, scope, "Check inventory counts.")
    context = with_sources(context, (older, head), latest)
    assert context.history.failure is None and len(context.history.selected) == 2
    return context, older, head, unit


def inherited_task(older):
    return dict(
        kind="task",
        value=older.signals.task,
        origin=dict(type="history", source=older.ref.model_dump(mode="json")),
    )


def state_entity(unit, older=None):
    origin = dict(type="state", state_item_id=str(unit.id))
    if older is not None:
        origin["source"] = older.ref.model_dump(mode="json")
    return dict(kind="entity", value=unit.value, origin=origin)


def facts(older, unit):
    return [
        inherited_task(older),
        state_entity(unit, older),
        dict(kind="negation", value="NOT", origin=dict(type="current")),
        dict(kind="time", value="6 hours", origin=dict(type="current")),
    ]


def raw(facts=(), *, relation="continue", dependency="required", **fields):
    return json.dumps(dict(topic_relation=relation, dependency=dependency, facts=facts, **fields))


def decoded(value, context):
    return decode_residual(value, context, fact_bytes_cap=CAP)


@pytest.mark.parametrize("task,entity", [("calibration", "Aurora spindle"), ("packaging", "Marble sensor")])
@pytest.mark.parametrize("explicit_return_language", [False, True])
def test_unique_valid_older_task_normal_form_matches_existing_explicit_return_exactly(
    task, entity, explicit_return_language
):
    context, older, _, unit = scenario(task=task, entity=entity)
    if explicit_return_language:
        context = context.model_copy(
            update={
                "request": context.request.model_copy(
                    update={"question": "Return to " + context.request.question}
                )
            }
        )
    value = raw(facts(older, unit))
    normalized = decoded(value, context)
    expected = decode_closure(raw(facts(older, unit), relation="return"), context, fact_bytes_cap=CAP)
    assert normalized == expected
    result = interpret(context, draft=normalized)
    assert result.model_dump(mode="json") == interpret(context, draft=expected).model_dump(mode="json")
    assert result.topic_relation == "return" and result.mode == "USE_REWRITE"
    assert result.selected_query == context.request.question + "\n" + task + "\n" + entity
    assert result.delta.signals.task == task and result.delta.signals.entities == (entity,)
    assert result.delta.put == () and result.delta.deactivate == ()
    assert result.delta.relations == (HistoryRelation(target=older.ref, kind="dependency"),)
    assert "NOT before 6 hours" in result.selected_query
    assert result.scope == context.request.scope and result.authority == "contextual_intent_not_evidence"
    for historical_decoder in (decode_reconciled, decode_closure):
        with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
            historical_decoder(value, context, fact_bytes_cap=CAP)


def test_genuine_head_continue_does_not_infer_return_from_old_state_age():
    context, older, head, unit = scenario()
    context = context.model_copy(
        update={
            "request": context.request.model_copy(update={"question": "For inventory, inspect it."}),
            "required": (),
        }
    )
    value = raw(
        [dict(kind="task", value=head.signals.task, origin=dict(type="current")), state_entity(unit, older)]
    )
    normal = decoded(value, context)
    assert normal == decode_closure(value, context, fact_bytes_cap=CAP)
    result = interpret(context, draft=normal)
    assert result.topic_relation == "continue"
    assert result.selected_query == context.request.question + "\n" + unit.value


def test_same_entity_current_literal_under_genuine_new_task_stays_independent_shift():
    context, _, _, unit = scenario()
    question = f"New lubrication task for {unit.value}: which grease applies?"
    context = context.model_copy(
        update={"request": context.request.model_copy(update={"question": question}), "required": ()}
    )
    value = raw(
        [
            dict(kind="task", value="lubrication", origin=dict(type="current")),
            dict(kind="entity", value=unit.value, origin=dict(type="current")),
        ],
        relation="shift",
        dependency="none",
    )
    normal = decoded(value, context)
    assert normal == decode_closure(value, context, fact_bytes_cap=CAP)
    result = interpret(context, draft=normal)
    assert result.topic_relation == "shift" and result.mode == "USE_ORIGINAL"
    assert result.selected_query == question and all(fact.source is None for fact in result.facts)
    assert intent_context(context, result) == ((), ())
    assert result.delta.deactivate == (unit.id,)


def test_explicit_existing_return_is_already_normal_and_does_not_need_projection():
    context, older, _, unit = scenario()
    value = raw(facts(older, unit), relation="return")
    assert decoded(value, context) == decode_closure(value, context, fact_bytes_cap=CAP)


def test_shift_required_with_valid_old_origins_is_never_converted():
    context, older, _, unit = scenario()
    value = raw(facts(older, unit), relation="shift")
    draft = decoded(value, context)
    assert draft == decode_closure(value, context, fact_bytes_cap=CAP)
    assert draft.topic_relation == "shift" and draft.dependency == "required"
    with pytest.raises(CoreConflict, match="topic_shift_inheritance"):
        interpret(context, draft=draft)


@pytest.mark.parametrize("fault", ["state_id", "source", "kind", "value"])
def test_normal_form_never_rescues_wrong_state_provenance(fault):
    context, older, _, unit = scenario()
    claimed = facts(older, unit)
    if fault == "state_id":
        claimed[1]["origin"]["state_item_id"] = str(uuid4())
    elif fault == "source":
        claimed[1]["origin"]["source"]["turn_id"] = str(uuid4())
    elif fault == "kind":
        claimed[1]["kind"] = "task"
    else:
        claimed[1]["value"] = "Unsupported unit"
    with pytest.raises(CoreConflict, match="reconciliation_origin_unavailable_or_ambiguous"):
        decoded(raw(claimed), context)


def test_inactive_state_remains_unavailable_despite_selected_old_history():
    context, older, _, unit = scenario()
    retired = task_step(
        context.request.scope,
        "inventory",
        context.previous,
        deactivate=(unit.id,),
        relations=(HistoryRelation(target=older.ref, kind="correction", state_item_ids=(unit.id,)),),
    )
    retirement = historical(retired, context.request.scope, "Retire the previous subject during inventory.")
    context = with_sources(context, (older, retirement), retired)
    with pytest.raises(CoreConflict, match="reconciliation_origin_unavailable_or_ambiguous"):
        decoded(raw(facts(older, unit)), context)


@pytest.mark.parametrize("literal", ["absent", "repeated"])
def test_old_task_requires_one_exact_current_literal(literal):
    context, older, _, unit = scenario()
    question = (
        "For lubrication, inspect it, NOT before 6 hours?"
        if literal == "absent"
        else "calibration versus calibration: inspect it, NOT before 6 hours?"
    )
    context = context.model_copy(
        update={"request": context.request.model_copy(update={"question": question})}
    )
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw(facts(older, unit)), context)


def test_current_task_literal_is_not_a_unique_history_task_proof():
    context, older, _, unit = scenario()
    claimed = facts(older, unit)
    claimed[0]["origin"] = dict(type="current")
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw(claimed), context)


def test_available_old_state_without_claimed_old_task_does_not_derive_return():
    context, older, _, unit = scenario()
    value = raw([state_entity(unit, older)])
    normal = decoded(value, context)
    assert normal == decode_closure(value, context, fact_bytes_cap=CAP)
    assert normal.topic_relation == "continue"
    assert interpret(context, draft=normal).selected_query == context.request.question + "\n" + unit.value


def test_conflicting_old_topic_without_a_history_task_proof_does_not_derive_return():
    context, older, _, unit = scenario()
    claimed = [
        dict(
            kind="topic",
            value=older.signals.topic,
            origin=dict(type="history", source=older.ref.model_dump(mode="json")),
        ),
        state_entity(unit, older),
    ]
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw(claimed), context)


def test_old_history_task_without_its_supported_entity_is_not_a_return_normal_form():
    context, older, _, _ = scenario()
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw([inherited_task(older)]), context)


def test_same_older_entity_with_different_current_task_cannot_reuse_old_task_normal_form():
    context, older, _, unit = scenario()
    question = "For lubrication, inspect it, NOT before 6 hours?"
    context = context.model_copy(
        update={"request": context.request.model_copy(update={"question": question})}
    )
    claimed = facts(older, unit)
    claimed[0] = dict(kind="task", value="lubrication", origin=dict(type="current"))
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw(claimed), context)


def test_second_available_history_task_match_prevents_a_unique_projection():
    context, older, head, unit = scenario()
    another = task_step(context.request.scope, older.signals.task, entities=("Copper sensor",))
    duplicate = historical(another, context.request.scope, "Inspect Copper sensor for calibration.")
    context = with_sources(context, (older, duplicate), head.acceptance)
    assert len(context.history.selected) == 2 and context.history.failure is None
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw(facts(older, unit)), context)


def test_one_old_task_cannot_project_mixed_inherited_sources():
    precision = StateValue(id=uuid4(), kind="constraint", key="quality", value="precision mode")
    context, older, head, unit = scenario(head_put=(precision,))
    claimed = [
        *facts(older, unit),
        dict(
            kind="constraint",
            value=precision.value,
            origin=dict(
                type="state", state_item_id=str(precision.id), source=head.ref.model_dump(mode="json")
            ),
        ),
    ]
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw(claimed), context)
    # The same claims are supported, but the user/model must explicitly decide
    # the mixed-source transition. Unique older-task projection cannot do so.
    explicit = decode_closure(raw(claimed, relation="return"), context, fact_bytes_cap=CAP)
    assert interpret(context, draft=explicit).topic_relation == "return"


@pytest.mark.parametrize("mutation", ["put", "corrections"])
def test_semantic_mutations_and_ambiguity_do_not_enter_the_normal_form(mutation):
    context, older, _, unit = scenario()
    if mutation == "put":
        extra = [
            StateValue(id=uuid4(), kind="entity", key="additional", value=unit.value).model_dump(mode="json")
        ]
    elif mutation == "corrections":
        extra = [dict(item_id=str(unit.id), mention=dict(quote="it"))]
    else:
        extra = [dict(reason="unresolved_intent")]
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw(facts(older, unit), **{mutation: extra}), context)


def test_correction_group_requires_the_existing_explicit_model_core_path():
    context, older, _, unit = scenario()
    replacement = StateValue(
        id=uuid4(), kind="entity", key=unit.key, value="Aurora revised spindle", replaces=(unit.id,)
    )
    corrected = task_step(
        context.request.scope,
        older.signals.task,
        older.acceptance,
        put=(replacement,),
        entities=(replacement.value,),
        relations=(HistoryRelation(target=older.ref, kind="correction", state_item_ids=(unit.id,)),),
    )
    later = task_step(context.request.scope, "inventory", corrected)
    correction_source = historical(
        corrected, context.request.scope, "Use Aurora revised spindle for calibration."
    )
    context = with_sources(context, (older, correction_source), later)
    assert context.history.failure is None and context.history.selected[0].edges
    claimed = facts(correction_source, replacement)
    with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
        decoded(raw(claimed), context)
    explicit = decode_closure(raw(claimed, relation="return"), context, fact_bytes_cap=CAP)
    assert interpret(context, draft=explicit).delta.signals.entities == (replacement.value,)


@pytest.mark.parametrize("candidate_count", [0, 2])
def test_unresolved_or_competing_references_clarify_without_guessing_a_return(candidate_count):
    context, older, head, unit = scenario(extra_entity=True)
    context = context.model_copy(
        update={
            "request": context.request.model_copy(update={"question": "For inventory, inspect it."}),
            "required": (),
        }
    )
    entries = [entry for entry in context.history.state_projection if entry.item.kind == "entity"]
    candidates = [state_entity(entry.item, older) for entry in entries[:candidate_count]]
    value = raw(
        [dict(kind="task", value=head.signals.task, origin=dict(type="current"))],
        dependency="unresolved" if candidate_count == 0 else "required",
        references=[dict(mention=dict(quote="it"), candidates=candidates)],
    )
    draft = decoded(value, context)
    assert draft == decode_closure(value, context, fact_bytes_cap=CAP)
    decision = interpret(context, draft=draft)
    assert decision.mode == "CLARIFY" and decision.selected_query is None
    assert decision.bindings == () and decision.control_result.kind == "clarification"
    assert decision.delta.signals == ResolvedSignals()
    assert unit.id not in decision.delta.deactivate


@pytest.fixture(scope="module")
def rc_residuals():
    path = ROOT / ".runtime/evaluation/rc-closure/execution-reconciliation.json"
    if not path.is_file():
        pytest.skip("immutable local RC receipts absent in public checkout")
    return {case["case_id"]: case for case in json.loads(path.read_bytes())["cases"]}


def test_preserved_ab0_continue_has_one_valid_return_normal_form_but_old_parsers_reject(rc_residuals):
    case = rc_residuals["D1.V2:cp-ab0-v1"]
    receipt = case["result"]
    context = InterpretationInput.model_validate(receipt["target_context"]["input"])
    original = receipt["provider_outputs"]["interpretation"]
    for old_parser in (decode_reconciled, decode_closure):
        with pytest.raises(CoreConflict, match="reconciliation_topic_return_required"):
            old_parser(original, context, fact_bytes_cap=CAP)
    normalized = decoded(original, context)
    manual = copy.deepcopy(json.loads(original))
    manual["topic_relation"] = "return"
    explicit = decode_closure(json.dumps(manual), context, fact_bytes_cap=CAP)
    assert normalized == explicit and normalized.topic_relation == "return"
    assert interpret(context, draft=normalized).model_dump(mode="json") == interpret(
        context, draft=explicit
    ).model_dump(mode="json")
    assert case["status"] == "FAILED"  # Historical evidence stays unchanged.


def test_preserved_a_shift_remains_unchanged_and_fails_state_only_contract(rc_residuals):
    receipt = rc_residuals["D1.V2:cp-a-v1"]["result"]
    context = InterpretationInput.model_validate(receipt["target_context"]["input"])
    original = receipt["provider_outputs"]["interpretation"]
    draft = decoded(original, context)
    assert draft == decode_closure(original, context, fact_bytes_cap=CAP)
    assert draft.topic_relation == "shift" and draft.dependency == "required"
    with pytest.raises(CoreConflict, match="evaluation_state_intent_contract"):
        state_intent(context, draft)
