"""General adversarial contracts plus immutable real-output regression locks."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from test_conversation_history import source, state_step
from test_conversation_interpretation import context as context
from test_conversation_interpretation import with_sources

from citeweave.conversation_contract import CoreConflict, StateValue
from citeweave.conversation_history import HistorySource
from citeweave.conversation_interpretation import CriticalTerm, InterpretationInput, interpret
from citeweave.evaluation.dev_state import state_intent
from citeweave.runtime_reconciliation import decision_context, decode_reconciled, localized_span

ROOT = Path(__file__).resolve().parents[1]


def draft(context, facts, **fields):
    value = dict(topic_relation="continue", dependency="required", facts=facts)
    value.update(fields)
    return decode_reconciled(json.dumps(value), context, fact_bytes_cap=399616)


def sf(value):
    return dict(kind="entity", value=value, origin=dict(type="state"))


@pytest.fixture
def real():
    folders = ("dynamic-provenance", "p0-rerun", "stabilization")
    paths = [ROOT / ".runtime/evaluation" / f / "execution-reconciliation.json" for f in folders]
    if not all(p.exists() for p in paths):
        pytest.skip("immutable local campaign receipts absent")
    return {
        f: {c["case_id"]: c for c in json.loads(p.read_bytes())["cases"]}
        for f, p in zip(folders, paths, strict=True)
    }


def decode_case(case):
    context = InterpretationInput.model_validate(case["result"]["target_context"]["input"])
    decoded = decode_reconciled(
        case["result"]["provider_outputs"]["interpretation"], context, fact_bytes_cap=399616
    )
    return (
        state_intent(context, decoded)
        if case["case_id"] in {"D1.V2:cp-a-v1", "D3.V1:cp-a-v1"}
        else interpret(context, draft=decoded)
    )


@pytest.mark.parametrize(
    "key",
    [
        "D1.V1:cp-a-v1",
        "D1.V1:cp-ab0-v1",
        "D3.V1:cp-a-v1",
        "D3.V1:cp-ab0-v1",
        "D3.V2:cp-ab0-v1",
        "D4.V1:cp-ab0-v1",
        "D5.V2:cp-ab0-v1",
    ],
)
def test_all_interpretation_paths_in_sixteen_p0_human_pass_locks(real, key):
    case = real["p0-rerun"][key]
    new = decode_case(case)
    old = case["result"]["result"]["interpretation"]
    assert new.mode == old["mode"]
    assert new.topic_relation == old["topic_relation"]
    assert new.selected_query == old["selected_query"]


@pytest.mark.parametrize(
    "key,mode",
    [
        ("D1.V1:cp-ab0-v1", "USE_REWRITE"),
        ("D4.V1:cp-ab0-v1", "CLARIFY"),
        ("D4.V2:cp-a-v1", "USE_REWRITE"),
        ("D4.V2:cp-ab0-v1", "USE_REWRITE"),
        ("D5.V2:cp-a-v1", "USE_REWRITE"),
    ],
)
def test_reworked_regressions_and_kept_unique_gain_replay(real, key, mode):
    result = decode_case(real["stabilization"][key])
    assert result.mode == mode
    if key.startswith("D4.V2"):
        assert result.delta.signals.entities == ("Beacon-South",)
        assert not result.ambiguities


def test_optional_current_description_cannot_kill_supported_intent(context):
    from citeweave.conversation_contract import ResolvedSignals

    old = source(context.request.scope, signals=ResolvedSignals(entities=("Orchid",)))
    context = with_sources(context, (old,))
    entity = dict(kind="entity", value="Orchid", origin=dict(type="history"))
    description = dict(kind="constraint", value="abstract question category", origin=dict(type="current"))
    good = interpret(context, draft=draft(context, [entity, description]))
    assert good.selected_query == context.request.question + "\nOrchid"
    assert good.delta.signals.constraints == ()
    for kind in ("entity", "time", "negation", "task", "document", "version"):
        bad = dict(description, kind=kind)
        with pytest.raises(CoreConflict):
            draft(context, [entity, bad])
    critical = context.model_copy(update={"required": (CriticalTerm(dimension="negation", value="not"),)})
    with pytest.raises(CoreConflict):
        draft(critical, [entity, description])
    with pytest.raises(CoreConflict):
        draft(context, [entity, dict(description, origin=dict(type="history"))])


@pytest.mark.parametrize(
    "entity_mode,mode", [("single", "CLARIFY"), ("alternatives", "CLARIFY"), ("joint", "USE_REWRITE")]
)
def test_alternatives_are_not_documentary_insufficiency_and_joint_is_explicit(context, entity_mode, mode):
    from citeweave.conversation_contract import ResolvedSignals

    old = source(context.request.scope, signals=ResolvedSignals(entities=("Orchid", "Linden")))
    context = with_sources(context, (old,))
    facts = [dict(kind="entity", value=v, origin=dict(type="history")) for v in ("Orchid", "Linden")]
    result = interpret(context, draft=draft(context, facts, entity_mode=entity_mode))
    assert result.mode == mode
    if mode == "CLARIFY":
        assert result.control_result.kind == "clarification" and result.selected_query is None
    else:
        assert result.delta.signals.entities == ("Orchid", "Linden")
    with pytest.raises(CoreConflict):
        if mode != "CLARIFY":
            interpret(context, draft=draft(context, facts, entity_mode=entity_mode, dependency="none"))
        else:
            draft(context, [*facts, dict(kind="entity", value="Invented", origin=dict(type="state"))])


def pending_context(context):
    scope = context.request.scope
    accepted = state_step(
        scope,
        put=tuple(
            StateValue(id=uuid4(), kind=kind, key=key, value=value)
            for kind, key, value in [
                ("entity", "one", "Orchid"),
                ("entity", "two", "Linden"),
                ("ambiguity", "choice", "unresolved selection"),
            ]
        ),
    )
    history = HistorySource(
        acceptance=accepted,
        request=context.request.model_copy(update={"expected_head": None}),
        origins=("explicit",),
    )
    context = with_sources(context, (history,), accepted)
    return context.model_copy(
        update={"request": context.request.model_copy(update={"question": "Use Linden, NOT Orchid."})}
    )


def test_explicit_resolution_keeps_other_ambiguity_and_negative_current_constraints(context):
    context = pending_context(context)
    facts = [sf("Orchid"), sf("Linden"), dict(kind="negation", value="NOT", origin=dict(type="current"))]
    resolution = dict(ambiguity_key="choice", selection=sf("Linden"))
    result = interpret(context, draft=draft(context, facts, resolutions=[resolution]))
    assert result.mode == "USE_REWRITE" and result.delta.signals.entities == ("Linden",)
    assert "NOT Orchid" in result.selected_query
    assert result.delta.signals.constraints == ("NOT",)
    unresolved = dict(reason="unresolved_intent")
    result = interpret(
        context, draft=draft(context, facts, resolutions=[resolution], ambiguities=[unresolved])
    )
    assert result.mode == "CLARIFY"
    for invalid in (
        dict(ambiguity_key="missing", selection=sf("Linden")),
        dict(ambiguity_key="choice", selection=sf("Invented")),
    ):
        with pytest.raises(CoreConflict):
            draft(context, facts, resolutions=[invalid])
    with pytest.raises(CoreConflict):
        draft(context, facts, resolutions=[resolution], entity_mode="joint")
    bad = sf("Linden")
    bad["origin"]["source"] = dict(acceptance_id=str(UUID(int=0)), turn_id=str(UUID(int=0)))
    with pytest.raises(CoreConflict):
        draft(context, facts, resolutions=[dict(ambiguity_key="choice", selection=bad)])


def test_repeated_literal_and_malformed_structure_do_not_gain_guessing(context):
    assert localized_span("é unique", "unique", 9).start == 2
    with pytest.raises(CoreConflict):
        localized_span("A A", "A", None)
    assert localized_span("A A", "A", 1).start == 2
    for raw in ("{", '{"dependency":"none","dependency":"required"}'):
        with pytest.raises(CoreConflict, match="reconciliation_json"):
            decode_reconciled(raw, context, fact_bytes_cap=399616)


def test_synthetic_task_return_continue_action_and_independence_are_distinct(context):
    from citeweave.conversation_contract import ResolvedSignals

    def signals(accepted, task):
        return accepted.model_copy(
            update={
                "state": accepted.state.model_copy(
                    update={
                        "delta": accepted.state.delta.model_copy(
                            update={"signals": ResolvedSignals(task=task)}
                        )
                    }
                )
            }
        )

    first = signals(
        state_step(
            context.request.scope, put=(StateValue(id=uuid4(), kind="entity", key="machine", value="Orchid"),)
        ),
        "packing",
    )
    second = signals(state_step(context.request.scope, first), "painting")
    sources = tuple(
        HistorySource(
            acceptance=a,
            request=context.request.model_copy(update={"expected_head": None if a is first else first.id}),
            origins=("explicit",),
        )
        for a in (first, second)
    )
    question = "Resume packing operation for it, NOT before 4 days."
    context = context.model_copy(
        update={"request": context.request.model_copy(update={"question": question})}
    )
    current = dict(kind="task", value="packing", origin=dict(type="current"))
    facts = [
        current,
        sf("Orchid"),
        dict(kind="negation", value="NOT", origin=dict(type="current")),
        dict(kind="time", value="4 days", origin=dict(type="current")),
    ]
    continued = with_sources(context, sources[:1], first)
    assert interpret(continued, draft=draft(continued, facts)).topic_relation == "continue"
    returned = with_sources(context, sources, second)
    assert (
        interpret(returned, draft=draft(returned, facts, topic_relation="return")).topic_relation == "return"
    )
    with pytest.raises(CoreConflict, match="topic_return_required"):
        draft(returned, facts)
    action = [dict(current, value="packing operation"), *facts[1:]]
    with pytest.raises(CoreConflict, match="topic_relation_conflict"):
        interpret(continued, draft=draft(continued, action))
    independent = interpret(returned, draft=draft(returned, [], topic_relation="shift", dependency="none"))
    assert independent.selected_query == question and not independent.facts
    assert (
        "NOT before 4 days"
        in interpret(returned, draft=draft(returned, facts, topic_relation="return")).selected_query
    )


def test_head_context_supports_true_return_continue_and_independent_neighbors(real):
    for key, topic in [("D1.V2:cp-ab0-v1", "return"), ("D3.V1:cp-ab0-v1", "return")]:
        case = real["p0-rerun"][key]
        context = InterpretationInput.model_validate(case["result"]["target_context"]["input"])
        value = json.loads(case["result"]["provider_outputs"]["interpretation"])
        value["topic_relation"] = topic
        assert (
            interpret(context, draft=draft(context, value["facts"], topic_relation=topic)).topic_relation
            == topic
        )
        assert decision_context(context)["head_signals"]
    case = real["p0-rerun"]["D5.V2:cp-ab0-v1"]
    context = InterpretationInput.model_validate(case["result"]["target_context"]["input"])
    assert "D5-task" in {t["value"] for t in decision_context(context)["stable_tasks"]}
    result = interpret(context, draft=draft(context, [], topic_relation="shift", dependency="none"))
    assert result.mode == "USE_ORIGINAL" and result.selected_query == context.request.question
