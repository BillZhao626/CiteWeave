"""Preserved outputs and generic opposite decisions; never a model quality judge."""

import json
from pathlib import Path

import pytest

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationInput, interpret
from citeweave.interpretation_format import decode_format
from citeweave.runtime_stabilization import decision_context, decode_stabilized, localized_span

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def receipts():
    p = ROOT / ".runtime/evaluation/p0-rerun/execution-reconciliation.json"
    if not p.exists():
        pytest.skip("preserved local real campaign receipts absent")
    return {c["case_id"]: c for c in json.loads(p.read_bytes())["cases"]}


def ctx(c):
    return InterpretationInput.model_validate(c["result"]["target_context"]["input"])


@pytest.mark.parametrize(
    "key,error",
    [
        ("D4.V2:cp-ab0-v1", "interpretation_format_schema"),
        ("D5.V1:cp-a-v1", "topic_relation_conflict"),
        ("D5.V2:cp-a-v1", "interpretation_format_quote_occurrence"),
    ],
)
def test_three_original_failures_reproduced(receipts, key, error):
    c = receipts[key]
    with pytest.raises(CoreConflict, match=error):
        interpret(ctx(c), draft=decode_format(c["result"]["provider_outputs"]["interpretation"], ctx(c)))


def test_preserved_unique_quote_failure_has_one_correct_derivation(receipts):
    c = receipts["D5.V2:cp-a-v1"]
    context = ctx(c)
    draft = decode_stabilized(
        c["result"]["provider_outputs"]["interpretation"], context, fact_bytes_cap=400000
    )
    result = interpret(context, draft=draft)
    assert result.mode == "USE_REWRITE"
    assert result.selected_query.startswith(context.request.question + "\n")
    for fact in draft.facts:
        if fact.span:
            assert context.request.question[fact.span.start : fact.span.end] == fact.value


def test_unique_quote_does_not_guess_repeated_or_absent_origins():
    assert localized_span("😀 AA and BB", "BB", 1).start == 9
    with pytest.raises(CoreConflict, match="localization_ambiguous"):
        localized_span("AA AA", "AA", None)
    assert localized_span("AA AA", "AA", 1).start == 3
    with pytest.raises(CoreConflict, match="localization"):
        localized_span("AA AA", "AA", 2)
    with pytest.raises(CoreConflict, match="localization"):
        localized_span("AA", "BB", None)


def state(context, value):
    return dict(kind="entity", value=value, origin=dict(type="state"))


def wire(facts, topic="continue", dependency="required", **fields):
    return dict(
        topic_relation=topic,
        dependency=dependency,
        facts=facts,
        references=[],
        ambiguities=[],
        put=[],
        corrections=[],
        **fields,
    )


def test_state_machine_fields_are_derived_only_for_unique_active_value(receipts):
    context = ctx(receipts["D1.V1:cp-ab0-v1"])
    draft = decode_stabilized(json.dumps(wire([state(context, "Ferrule-Q")])), context, fact_bytes_cap=400000)
    entry = context.history.state_projection[0]
    assert draft.facts[0].source == entry.introduced_by and draft.facts[0].state_item_id == entry.item.id
    bad = wire([state(context, "unsupported unit")])
    with pytest.raises(CoreConflict, match="origin_unavailable"):
        decode_stabilized(json.dumps(bad), context, fact_bytes_cap=400000)
    bad = wire([state(context, "Ferrule-Q")])
    bad["facts"][0]["origin"]["source"] = {
        "acceptance_id": "00000000-0000-0000-0000-000000000000",
        "turn_id": "00000000-0000-0000-0000-000000000000",
    }
    with pytest.raises(CoreConflict, match="origin_unavailable"):
        decode_stabilized(json.dumps(bad), context, fact_bytes_cap=400000)


def test_topic_return_exposes_head_signals_and_rejects_wrong_continue(receipts):
    context = ctx(receipts["D1.V2:cp-ab0-v1"])
    assert decision_context(context)["head_signals"]["task"] == "tray-display"
    facts = [dict(kind="task", value="D1-task", origin=dict(type="current")), state(context, "Ferrule-Q")]
    with pytest.raises(CoreConflict, match="topic_return_required"):
        decode_stabilized(json.dumps(wire(facts)), context, fact_bytes_cap=400000)
    draft = decode_stabilized(json.dumps(wire(facts, topic="return")), context, fact_bytes_cap=400000)
    assert interpret(context, draft=draft).topic_relation == "return"
    current = ctx(receipts["D5.V1:cp-ab0-v1"])
    same = [dict(kind="task", value="D5-task", origin=dict(type="current")), state(current, "Quill m4")]
    assert (
        interpret(
            current, draft=decode_stabilized(json.dumps(wire(same)), current, fact_bytes_cap=400000)
        ).topic_relation
        == "continue"
    )


def test_ambiguity_and_explicit_selection_are_opposite_decisions(receipts):
    context = ctx(receipts["D4.V1:cp-a-v1"])
    candidates = [state(context, v) for v in ("Beacon-North", "Beacon-South")]
    value = wire([])
    value["references"] = [dict(mention=dict(quote="it"), candidates=candidates)]
    assert (
        interpret(context, draft=decode_stabilized(json.dumps(value), context, fact_bytes_cap=400000)).mode
        == "CLARIFY"
    )
    context = ctx(receipts["D4.V2:cp-a-v1"])
    selection = state(context, "Beacon-South")
    value = wire([selection], resolutions=[dict(ambiguity_key="pending", selection=selection)])
    draft = decode_stabilized(json.dumps(value), context, fact_bytes_cap=400000)
    result = interpret(context, draft=draft)
    assert result.mode == "USE_REWRITE"
    assert len(draft.corrections) == 1
    assert result.selected_query == context.request.question + "\nBeacon-South"
    # Explicit intent proof cannot be replaced by selecting an absent literal.
    value = wire(
        [state(context, "Beacon-North")],
        resolutions=[dict(ambiguity_key="pending", selection=state(context, "Beacon-North"))],
    )
    with pytest.raises(CoreConflict, match="localization"):
        decode_stabilized(json.dumps(value), context, fact_bytes_cap=400000)


def test_correction_uses_active_state_and_keeps_incomplete_guard(receipts):
    context = ctx(receipts["D3.V2:cp-ab0-v1"])
    active = wire([state(context, "Cobalt-Latch release violet")], topic="return")
    assert (
        interpret(context, draft=decode_stabilized(json.dumps(active), context, fact_bytes_cap=400000)).mode
        == "USE_REWRITE"
    )
    stale = wire([state(context, "Cobalt-Latch release amber")], topic="return")
    with pytest.raises(CoreConflict, match="origin_unavailable"):
        decode_stabilized(json.dumps(stale), context, fact_bytes_cap=400000)
    from citeweave.evaluation.dev_dispatch import slots_for_view

    assert ctx(receipts["D3.V2:cp-a-v1"]).history.failure == "incomplete_group"
    assert slots_for_view(type("View", (), {"id": "D3.V2"})(), "cp-a-v1") == ()


def test_malformed_duplicate_json_and_byte_envelope_reject_without_repair(receipts):
    context = ctx(receipts["D5.V1:cp-ab0-v1"])
    for raw in ("{", '{"topic_relation":"continue","topic_relation":"return","dependency":"none"}'):
        with pytest.raises(CoreConflict, match="stabilization_json"):
            decode_stabilized(raw, context, fact_bytes_cap=400000)
    with pytest.raises(CoreConflict, match="normalized_fact_envelope"):
        decode_stabilized(json.dumps(wire([state(context, "Quill m4")])), context, fact_bytes_cap=1)


def test_ambiguous_state_identity_requires_explicit_binding(receipts):
    from uuid import uuid4

    context = ctx(receipts["D1.V1:cp-ab0-v1"])
    entry = context.history.state_projection[0]
    duplicate = entry.model_copy(update={"item": entry.item.model_copy(update={"id": uuid4()})})
    context = context.model_copy(
        update={"history": context.history.model_copy(update={"state_projection": (entry, duplicate)})}
    )
    value = wire([state(context, entry.item.value)])
    with pytest.raises(CoreConflict, match="origin_unavailable_or_ambiguous"):
        decode_stabilized(json.dumps(value), context, fact_bytes_cap=400000)
    value["facts"][0]["origin"]["state_item_id"] = str(entry.item.id)
    assert (
        decode_stabilized(json.dumps(value), context, fact_bytes_cap=400000).facts[0].state_item_id
        == entry.item.id
    )


def test_literal_does_not_silently_resolve_pending_ambiguity(receipts):
    context = ctx(receipts["D4.V2:cp-a-v1"])
    draft = decode_stabilized(
        json.dumps(wire([state(context, "Beacon-South")])), context, fact_bytes_cap=400000
    )
    assert interpret(context, draft=draft).mode == "CLARIFY"
    value = wire([], resolutions=[dict(ambiguity_key="absent", selection=state(context, "Beacon-South"))])
    with pytest.raises(CoreConflict, match="resolution_unavailable"):
        decode_stabilized(json.dumps(value), context, fact_bytes_cap=400000)


def test_preserved_valid_return_and_negation_remain_valid(receipts):
    for key in ("D3.V1:cp-ab0-v1", "D3.V2:cp-ab0-v1", "D5.V1:cp-ab0-v1", "D5.V2:cp-ab0-v1"):
        case = receipts[key]
        context = ctx(case)
        raw = case["result"]["provider_outputs"]["interpretation"]
        old = interpret(context, draft=decode_format(raw, context))
        new = interpret(context, draft=decode_stabilized(raw, context, fact_bytes_cap=400000))
        assert new == old
        assert new.selected_query.startswith(context.request.question + "\n")


def test_full_refreeze_preserves_generation_and_nine_pass_mechanisms(receipts):
    from decimal import Decimal

    from citeweave.evaluation.dev_stabilization import refreeze_stabilization
    from citeweave.provider_accounting import DeepSeekAccounting

    original = json.loads((ROOT / ".runtime/evaluation/0012-accepted-runtime/contracts.json").read_bytes())
    prior = json.loads((ROOT / ".runtime/evaluation/p0-rerun/contracts.json").read_bytes())
    accounting = DeepSeekAccounting(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    )
    new = refreeze_stabilization(original, accounting, ROOT)
    assert len(new["slots"]) == 38
    assert new["output_tokens"] == 777079
    assert Decimal(new["derived_worst_case_yuan"]) <= Decimal("18.70")
    assert new["normalized_fact_bytes_cap"] == 399616
    independent = 0
    for p, q in zip(new["probes"], prior["probes"], strict=True):
        assert (p["view"], p["arm"]) == (q["view"], q["arm"])
        assert p["dispatch_slots"] == q["dispatch_slots"]
        if "generation_shell" in q:
            assert p["generation_shell"] == q["generation_shell"]
            assert p["generation_bound"] == q["generation_bound"]
        if "generation_request" in q:
            independent += 1
            assert p["generation_request"] == q["generation_request"]
        if not p["dispatch_slots"]:
            assert p["guard"] == "incomplete_group"
    assert independent == 8
