"""Format intervention: old receipts reproduce failure, invalid neighbors still fail."""

import json
from pathlib import Path

import pytest

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationInput, interpret
from citeweave.interpretation_format import FormatDraft, decode_format, format_messages

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".runtime/evaluation/dynamic-provenance/execution-reconciliation.json"
P0 = (
    "D1.V1:cp-a-v1",
    "D1.V1:cp-ab0-v1",
    "D3.V1:cp-ab0-v1",
    "D4.V2:cp-ab0-v1",
    "D5.V1:cp-a-v1",
    "D5.V1:cp-ab0-v1",
    "D5.V2:cp-a-v1",
    "D5.V2:cp-ab0-v1",
)


@pytest.fixture
def baseline():
    if not BASELINE.is_file():
        pytest.skip("private preserved DEV receipts absent")
    return {c["case_id"]: c for c in json.loads(BASELINE.read_bytes())["cases"]}


def context(case):
    return InterpretationInput.model_validate(case["result"]["target_context"]["input"])


@pytest.mark.parametrize("key", P0)
def test_baseline_old_boundary_reproduces_exact_failure(baseline, key):
    from citeweave.evaluation.dev_dispatch import decode_output
    from citeweave.provider_accounting import DeepSeekAccounting

    case = baseline[key]
    accounting = DeepSeekAccounting(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    )
    with pytest.raises(CoreConflict, match=case["result"]["result"]["error_code"]):
        draft = decode_output(
            "interpretation",
            case["result"]["provider_outputs"]["interpretation"],
            finish_reason="stop",
            reserve=1561,
            accounting=accounting,
        )
        interpret(context(case), draft=draft)


def state_fact(ctx):
    e = ctx.history.state_projection[0]
    return dict(
        kind=e.item.kind,
        value=e.item.value,
        origin=dict(
            type="state", source=e.introduced_by.model_dump(mode="json"), state_item_id=str(e.item.id)
        ),
    )


def wire(ctx, facts, topic="continue", dependency="required"):
    return dict(
        topic_relation=topic,
        dependency=dependency,
        facts=facts,
        references=[],
        ambiguities=[],
        put=[],
        corrections=[],
    )


@pytest.mark.parametrize(
    "key,quote,kind,topic",
    [
        ("D3.V1:cp-ab0-v1", "D3-task latch test", "topic", "return"),
        ("D5.V1:cp-a-v1", "before 24 hours", "constraint", "continue"),
    ],
)
def test_reexpressed_baseline_claims_need_only_format_conversion(baseline, key, quote, kind, topic):
    ctx = context(baseline[key])
    facts = [state_fact(ctx), dict(kind=kind, value=quote, origin=dict(type="current", occurrence=0))]
    draft = decode_format(json.dumps(wire(ctx, facts, topic)), ctx)
    result = interpret(ctx, draft=draft)
    assert result.mode == "USE_REWRITE"
    assert result.selected_query == ctx.request.question + "\n" + facts[0]["value"]
    assert draft.rewrite.retained == ctx.required
    assert draft.facts[1].value == ctx.request.question[draft.facts[1].span.start : draft.facts[1].span.end]


@pytest.mark.parametrize(
    "mutation,error",
    [
        ("foreign_source", "state_source_identity"),
        ("wrong_state_value", "state_value_identity"),
        ("missing_quote", "quote_occurrence"),
        ("negative_occurrence", "format_schema"),
        ("missing_origin", "format_schema"),
        ("both_origins", "format_schema"),
        ("independent_inheritance", "independent_query_inheritance"),
        ("task_conflict", "topic_relation_conflict"),
    ],
)
def test_invalid_neighbors_still_rejected(baseline, mutation, error):
    ctx = context(baseline["D5.V1:cp-a-v1"])
    facts = [state_fact(ctx), dict(kind="time", value="24 hours", origin=dict(type="current", occurrence=0))]
    value = wire(ctx, facts)
    if mutation == "foreign_source":
        facts[0]["origin"]["source"]["turn_id"] = "00000000-0000-0000-0000-000000000000"
    if mutation == "wrong_state_value":
        facts[0]["value"] = "wrong unit"
    if mutation == "missing_quote":
        facts[1]["value"] = "48 hours"
    if mutation == "negative_occurrence":
        facts[1]["origin"]["occurrence"] = -1
    if mutation == "missing_origin":
        del facts[1]["origin"]
    if mutation == "both_origins":
        facts[1]["origin"]["source"] = facts[0]["origin"]["source"]
    if mutation == "independent_inheritance":
        value["dependency"] = "none"
    if mutation == "task_conflict":
        facts.append(dict(kind="task", value="relay check", origin=dict(type="current", occurrence=0)))
    with pytest.raises(CoreConflict, match=error):
        interpret(ctx, draft=decode_format(json.dumps(value), ctx))


def test_no_rewrite_guessing_scope_or_retention_override(baseline):
    ctx = context(baseline["D5.V1:cp-a-v1"])
    value = wire(ctx, [state_fact(ctx)])
    value["rewrite"] = dict(
        text="changed question", scope=ctx.request.scope.model_dump(mode="json"), retained=[]
    )
    with pytest.raises(CoreConflict, match="format_schema"):
        decode_format(json.dumps(value), ctx)


def test_wire_schema_has_discriminated_origin_and_format_only_prompt(baseline):
    ctx = context(baseline["D5.V1:cp-a-v1"])
    messages = format_messages(ctx)
    payload = json.loads(messages[1]["content"])
    assert payload["output_schema"] == FormatDraft.model_json_schema()
    assert "zero-based occurrence" in messages[0]["content"]
    assert payload["question"] == ctx.request.question
    assert payload["required"] == [t.model_dump(mode="json") for t in ctx.required]
    assert "rewrite" not in FormatDraft.model_fields


def test_unicode_repeated_and_overlapping_quote_offsets_are_exact():
    from citeweave.interpretation_format import quote_span

    assert quote_span("😀 aaa 中文", "aa", 1).model_dump() == {"start": 3, "end": 5}
    assert quote_span("😀 aaa 中文", "中文", 0).model_dump() == {"start": 6, "end": 8}
    with pytest.raises(CoreConflict, match="quote_occurrence"):
        quote_span("same same", "same", 2)


def test_baseline_pass_locks_provider_free(baseline):
    from citeweave.answering import REFUSAL
    from citeweave.evaluation.dev_approval import load_human_gold
    from citeweave.evaluation.dev_dispatch import slots_for_view

    data, _, _ = load_human_gold(ROOT)
    for view in data.views:
        if view.id.startswith(("D2.", "D6.")):
            for aid in ("cp-a-v1", "cp-ab0-v1"):
                assert slots_for_view(view, aid) == ("generation",)
                c = baseline[view.id + ":" + aid]
                ctx = context(c)
                old_decision = c["result"]["result"]["interpretation"]
                draft = decode_format(json.dumps(wire(ctx, [], dependency="none")), ctx)
                decision = interpret(ctx, draft=draft)
                assert decision.mode == old_decision["mode"] == "USE_ORIGINAL"
                assert decision.selected_query == view.question
                text = c["result"]["result"]["result"]["text"]
                if view.id == "D6.V2":
                    assert text == REFUSAL
                elif view.id == "D6.V1":
                    assert c["result"]["result"]["result"]["answer"]["citations"]
    v = next(v for v in data.views if v.id == "D3.V2")
    assert slots_for_view(v, "cp-a-v1") == ()
    assert baseline["D3.V2:cp-a-v1"]["result"]["result"] == {"guard": "incomplete_group", "calls": 0}


def test_format_refreeze_keeps_generation_envelopes_and_all_conditional_slots(baseline):
    from decimal import Decimal

    from citeweave.evaluation.dev_p0 import refreeze_p0
    from citeweave.provider_accounting import DeepSeekAccounting

    accounting = DeepSeekAccounting(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    )
    original = json.loads((ROOT / ".runtime/evaluation/0012-accepted-runtime/contracts.json").read_bytes())
    packet = refreeze_p0(original, accounting, ROOT)
    prior = json.loads((ROOT / ".runtime/evaluation/dynamic-provenance/contracts.json").read_bytes())
    assert packet["max_calls"] == 38
    assert packet["output_tokens"] == 777079
    assert Decimal(packet["derived_worst_case_yuan"]) <= Decimal("18.70")
    assert packet["environment"] == prior["environment"]
    for a, b in zip(packet["slots"], prior["slots"]):
        assert (a["case"], a["purpose"], a["output_tokens"]) == (b["case"], b["purpose"], b["output_tokens"])
        if a["purpose"] == "generation":
            assert a == b


def test_format_fact_expansion_fits_existing_symbolic_generation_proof(baseline):
    ctx = context(baseline["D5.V1:cp-a-v1"])
    candidates = [
        state_fact(ctx),
        dict(kind="time", value="24 hours", origin=dict(type="current", occurrence=0)),
        dict(
            kind="entity",
            value=ctx.history.state_projection[0].item.value,
            origin=dict(
                type="history", source=ctx.history.state_projection[0].introduced_by.model_dump(mode="json")
            ),
        ),
    ]
    for f in candidates:
        raw = json.dumps(wire(ctx, [f]), separators=(",", ":"))
        draft = decode_format(raw, ctx)
        for normalized in draft.facts:
            assert len(normalized.model_dump_json().encode()) <= 2 * len(
                json.dumps(f, separators=(",", ":"), ensure_ascii=False).encode()
            )


def test_d1_current_quote_and_same_state_claims_do_not_change_semantic_decision(baseline):
    ctx = context(baseline["D1.V1:cp-a-v1"])
    facts = [
        dict(kind="topic", value="D1-task inspection", origin=dict(type="current", occurrence=0)),
        dict(kind="task", value="inspection", origin=dict(type="current", occurrence=0)),
        state_fact(ctx),
    ]
    result = interpret(ctx, draft=decode_format(json.dumps(wire(ctx, facts)), ctx))
    assert result.mode == "USE_REWRITE"
    assert result.selected_query == ctx.request.question + "\nFerrule-Q"
