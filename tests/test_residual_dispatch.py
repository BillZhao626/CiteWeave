"""V6 route, immutable generation, and complete measured request envelope."""

import copy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from test_residual_locks import frozen as frozen
from test_residual_topic_micro import CAP, facts, raw, scenario

from citeweave.conversation_contract import CoreConflict
from citeweave.costs import maximum_cost
from citeweave.evaluation.dev_dispatch import decode_output
from citeweave.evaluation.dev_launcher import generation_identity
from citeweave.llm import completion_payload
from citeweave.provider_accounting import DeepSeekAccounting, request_hash, serialize_request
from citeweave.runtime_residual_closure import REVISION, decode_residual
from citeweave.settings import ROOT


def accounting_stub():
    return SimpleNamespace(
        reserved=("<reserved>",),
        tokenizer=SimpleNamespace(encode=lambda text, **kwargs: SimpleNamespace(ids=[0] * len(text))),
    )


def test_v6_dispatch_routes_to_validated_normal_form_with_exact_cap():
    context, older, _, unit = scenario()
    value = raw(facts(older, unit))
    result = decode_output(
        "interpretation",
        value,
        finish_reason="stop",
        reserve=10000,
        accounting=accounting_stub(),
        format_context=context,
        format_revision=REVISION,
        fact_bytes_cap=CAP,
    )
    assert result == decode_residual(value, context, fact_bytes_cap=CAP)
    assert result.topic_relation == "return"


@pytest.mark.parametrize("cap", [None, 0, -1])
def test_v6_route_rejects_missing_or_invalid_fact_cap(cap):
    context, _, _, _ = scenario()
    with pytest.raises(CoreConflict, match="dev_normalized_fact_cap_missing"):
        decode_output(
            "interpretation",
            "{}",
            finish_reason="stop",
            reserve=10000,
            accounting=accounting_stub(),
            format_context=context,
            format_revision=REVISION,
            fact_bytes_cap=cap,
        )


@pytest.mark.parametrize(
    "fault,code",
    [
        ("context", "dev_format_context_missing"),
        ("revision", "dev_interpretation_revision_unsupported"),
        ("finish", "dev_output_truncated_or_incomplete"),
        ("output", "dev_output_reserve_exceeded"),
        ("special", "dev_output_special_token"),
    ],
)
def test_v6_transport_failures_reject_before_decoding(fault, code):
    context, _, _, _ = scenario()
    args = dict(
        finish_reason="stop",
        reserve=10000,
        accounting=accounting_stub(),
        format_context=context,
        format_revision=REVISION,
        fact_bytes_cap=CAP,
    )
    value = "{}"
    if fault == "context":
        args["format_context"] = None
    elif fault == "revision":
        args["format_revision"] = "unapproved-future"
    elif fault == "finish":
        args["finish_reason"] = "length"
    elif fault == "output":
        args["reserve"] = 1
    else:
        value = "<reserved>"
    with pytest.raises(CoreConflict, match=code):
        decode_output("interpretation", value, **args)


def test_v6_generation_path_requires_exact_unchanged_rc_revision():
    packet = dict(
        interpretation_format_intervention=dict(revision=REVISION),
        generation_prompt=dict(path="prompts/answer-telecom-rc-v2.txt", revision="answer-telecom-rc-v2"),
    )
    assert generation_identity(packet) == packet["generation_prompt"]
    for field, value in (("path", "../../unapproved"), ("revision", "invented-revision")):
        drift = copy.deepcopy(packet)
        drift["generation_prompt"][field] = value
        with pytest.raises(CoreConflict, match="dev_candidate_generation_prompt_drift"):
            generation_identity(drift)


def test_refreeze_preserves_all23_generation_slots_and_production_order_measurements(frozen):
    packet = frozen["new"]
    accounting = DeepSeekAccounting(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    )
    oldslots = {(s["case"], s["purpose"]): s for s in frozen["prior"]["slots"]}
    counts = dict(interpretation=0, generation=0)
    for probe in packet["probes"]:
        prior = next(
            p for p in frozen["prior"]["probes"] if (p["view"], p["arm"]) == (probe["view"], probe["arm"])
        )
        for purpose in probe["dispatch_slots"]:
            counts[purpose] += 1
            slot = next(
                s
                for s in packet["slots"]
                if s["case"] == probe["view"] + ":" + probe["arm"] and s["purpose"] == purpose
            )
            if purpose == "generation":
                assert slot == oldslots[(slot["case"], purpose)]
                for key in (
                    "generation_request",
                    "generation_shell",
                    "generation_bound",
                    "generation_measurement",
                    "generation_provenance_bound",
                ):
                    assert probe.get(key) == prior.get(key)
            if purpose == "interpretation" or "generation_request" in probe:
                body = probe[purpose + "_request"]
                # Reconstruct the actual production outer dictionary order. A
                # canonical sorted JSON storage representation is not the wire.
                assert body == completion_payload(body["messages"], body["model"], body["max_tokens"])
                assert accounting.measure(body) == probe[purpose + "_measurement"]
                assert request_hash(body) == probe[purpose + "_measurement"]["request_hash"]
                assert serialize_request(body).startswith(b'{"model":')
                assert accounting.measure(body)["input_tokens"] <= slot["input_tokens"]
    assert counts == dict(interpretation=15, generation=23)
    assert len(packet["slots"]) == packet["max_calls"] == 38
    assert sum(s["input_tokens"] for s in packet["slots"]) == packet["input_tokens"]
    assert sum(s["output_tokens"] for s in packet["slots"]) == packet["output_tokens"] == 777079
    assert packet["total_tokens"] == packet["input_tokens"] + packet["output_tokens"]
    assert Decimal(packet["maximum_yuan"]) == maximum_cost(packet["input_tokens"], packet["output_tokens"])
    assert packet["authority"] == "PROVIDER_FREE_RESIDUAL_CANDIDATE_NOT_PAID_AUTHORITY"
