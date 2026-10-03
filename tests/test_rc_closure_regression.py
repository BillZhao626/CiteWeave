"""All19 approved behaviors replay locally; new model semantics need Human review."""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationInput, interpret
from citeweave.evaluation.dev_dataset import digest
from citeweave.evaluation.dev_dispatch import decode_output, slots_for_view
from citeweave.evaluation.dev_rc_closure import refreeze_closure
from citeweave.evaluation.dev_state import state_intent
from citeweave.provider_accounting import DeepSeekAccounting
from citeweave.runtime_rc_closure import decode_closure

ROOT = Path(__file__).resolve().parents[1]


def test_unknown_wire_revision_rejects_without_legacy_fallback():
    from types import SimpleNamespace

    accounting = SimpleNamespace(
        reserved=(), tokenizer=SimpleNamespace(encode=lambda *a, **k: SimpleNamespace(ids=[]))
    )
    with pytest.raises(CoreConflict, match="dev_interpretation_revision_unsupported"):
        decode_output(
            "interpretation",
            "{}",
            finish_reason="stop",
            reserve=1561,
            accounting=accounting,
            format_context=object(),
            format_revision="unapproved-future",
        )
    with pytest.raises(CoreConflict, match="dev_format_context_missing"):
        decode_output(
            "interpretation",
            "{}",
            finish_reason="stop",
            reserve=1561,
            accounting=accounting,
            format_revision="interpretation-rc-closure-v5",
        )


def test_normalized_fact_envelope_includes_array_separators():
    from types import SimpleNamespace

    from citeweave.runtime_reconciliation import decode_reconciled

    context = SimpleNamespace(
        previous=None,
        required=(),
        request=SimpleNamespace(question="Orchid Linden"),
        history=SimpleNamespace(selected=(), state_projection=()),
    )
    raw = json.dumps(
        dict(
            topic_relation="continue",
            dependency="none",
            facts=[dict(kind="entity", value=v, origin=dict(type="current")) for v in ("Orchid", "Linden")],
        )
    )
    draft = decode_reconciled(raw, context, fact_bytes_cap=399616)
    fact_bytes = sum(len(f.model_dump_json().encode()) for f in draft.facts)
    assert decode_reconciled(raw, context, fact_bytes_cap=fact_bytes) == draft
    with pytest.raises(CoreConflict, match="closure_normalized_fact_envelope"):
        decode_closure(raw, context, fact_bytes_cap=fact_bytes)
    assert decode_closure(raw, context, fact_bytes_cap=fact_bytes + 1) == draft


@pytest.mark.parametrize(
    "revision",
    [None, "interpretation-format-v2", "interpretation-reconciled-v4", "interpretation-rc-closure-v5"],
)
def test_generation_identity_allows_only_revision_bound_path_before_file_read(revision):
    from citeweave.evaluation.dev_launcher import generation_identity

    packet = dict(interpretation_format_intervention=dict(revision=revision)) if revision else {}
    if revision == "interpretation-rc-closure-v5":
        packet["generation_prompt"] = dict(
            path="prompts/answer-telecom-rc-v2.txt", revision="answer-telecom-rc-v2"
        )
    approved = generation_identity(packet)
    packet["generation_prompt"] = dict(approved, path="../../unapproved")
    with pytest.raises(CoreConflict, match="dev_candidate_generation_prompt_drift"):
        generation_identity(packet)


LOCKS = (
    "D1.V1:cp-a-v1",
    "D1.V1:cp-ab0-v1",
    "D2.V1:cp-a-v1",
    "D2.V1:cp-ab0-v1",
    "D2.V2:cp-a-v1",
    "D2.V2:cp-ab0-v1",
    "D3.V1:cp-a-v1",
    "D3.V1:cp-ab0-v1",
    "D3.V2:cp-a-v1",
    "D3.V2:cp-ab0-v1",
    "D4.V1:cp-a-v1",
    "D4.V2:cp-ab0-v1",
    "D5.V1:cp-a-v1",
    "D5.V2:cp-a-v1",
    "D5.V2:cp-ab0-v1",
    "D6.V1:cp-a-v1",
    "D6.V1:cp-ab0-v1",
    "D6.V2:cp-a-v1",
    "D6.V2:cp-ab0-v1",
)


@pytest.fixture(scope="module")
def frozen():
    folder = ROOT / ".runtime/evaluation"
    path = folder / "reconciliation/execution-reconciliation.json"
    if not path.exists():
        pytest.skip("immutable local paid receipts absent in public checkout")
    cases = {c["case_id"]: c for c in json.loads(path.read_bytes())["cases"]}
    original = json.loads((folder / "0012-accepted-runtime/contracts.json").read_bytes())
    prior = json.loads((folder / "reconciliation/contracts.json").read_bytes())
    accounting = DeepSeekAccounting(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    )
    before = digest(original)
    new = refreeze_closure(original, accounting, ROOT)
    assert digest(original) == before
    return cases, prior, new


@pytest.mark.parametrize("key", LOCKS)
def test_all19_exact_preserved_human_pass_interpretation_and_authority(frozen, key):
    cases, prior, new = frozen
    case = cases[key]
    context = InterpretationInput.model_validate(case["result"]["target_context"]["input"])
    raw = case["result"].get("provider_outputs", {}).get("interpretation")
    if raw:
        draft = decode_closure(raw, context, fact_bytes_cap=new["normalized_fact_bytes_cap"])
        decision = (
            state_intent(context, draft)
            if case["result"]["target_context"]["state_only"]
            else interpret(context, draft=draft)
        )
        assert decision.model_dump(mode="json") == case["result"]["result"]["interpretation"]
    else:
        probe = next(p for p in new["probes"] if p["view"] + ":" + p["arm"] == key)
        old = next(p for p in prior["probes"] if p["view"] + ":" + p["arm"] == key)
        if not probe["dispatch_slots"]:
            assert context.history.failure == probe["guard"] == "incomplete_group"
            assert slots_for_view(type("View", (), {"id": key.split(":")[0]})(), key.split(":")[1]) == ()
        else:
            assert probe["reviewed_independent_draft"] == old["reviewed_independent_draft"]
            body = copy.deepcopy(probe["generation_request"])
            body["messages"][0] = old["generation_request"]["messages"][0]
            assert body == old["generation_request"]


def test_five_dimensions_and_every_generation_binding_recomputed_without_reserve_growth(frozen):
    _, prior, new = frozen
    assert len(new["slots"]) == 38 and new["max_calls"] == 38
    assert new["reserves"] == prior["reserves"]
    assert new["output_tokens"] == 777079
    assert new["total_tokens"] == new["input_tokens"] + new["output_tokens"]
    assert Decimal(new["derived_worst_case_yuan"]) <= Decimal("18.70")
    assert new["normalized_fact_bytes_cap"] == prior["normalized_fact_bytes_cap"] == 399616
    counts = {"exact": 0, "symbolic": 0}
    for p, q in zip(new["probes"], prior["probes"], strict=True):
        assert p["dispatch_slots"] == q["dispatch_slots"]
        if "generation_request" in p:
            counts["exact"] += 1
            assert p["generation_measurement"]["request_hash"] != q["generation_measurement"]["request_hash"]
            assert p["generation_request"]["messages"][1:] == q["generation_request"]["messages"][1:]
        if "generation_shell" in p:
            counts["symbolic"] += 1
            assert p["generation_shell"]["messages"][1:] == q["generation_shell"]["messages"][1:]
            for field in (
                "interpretation_insertion_bytes",
                "escaped_query_bytes",
                "current_evidence_pack_bytes",
            ):
                assert p["generation_bound"][field] == q["generation_bound"][field]
    assert counts == {"exact": 8, "symbolic": 15}
