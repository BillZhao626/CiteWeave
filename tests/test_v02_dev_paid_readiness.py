"""Provider-free readiness cannot turn references or missing bounds into grants."""

from decimal import Decimal
from pathlib import Path

import pytest

from citeweave.evaluation.dev_paid_readiness import bounded_totals, build_readiness
from citeweave.provider_accounting import DeepSeekAccounting, request_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def packet():
    path = ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    if not path.is_file():
        pytest.skip("pinned local tokenizer absent; no fabricated accounting")
    return build_readiness(ROOT, DeepSeekAccounting(path))


def test_closed_decimal_aggregation_and_exact_boundary():
    calls = [dict(input_tokens=73, output_tokens=300), dict(input_tokens=27, output_tokens=100)]
    limits = dict(calls=2, input_tokens=100, output_tokens=400, yuan=Decimal("0.0034"))
    assert bounded_totals(calls, limits=limits) == dict(
        calls=2, input_tokens=100, output_tokens=400, total_tokens=500, yuan=Decimal("0.0034")
    )


@pytest.mark.parametrize("field", ["calls", "input_tokens", "output_tokens", "yuan"])
def test_each_budget_dimension_fails_closed(field):
    limits = dict(calls=1, input_tokens=73, output_tokens=300, yuan=Decimal("0.002546"))
    limits[field] -= Decimal("0.000001") if field == "yuan" else 1
    with pytest.raises(ValueError, match="readiness_budget_exceeded"):
        bounded_totals([dict(input_tokens=73, output_tokens=300)], limits=limits)


@pytest.mark.parametrize("value", [None, True, -1, 1.5])
def test_missing_or_invalid_token_bound_never_becomes_zero(value):
    with pytest.raises(ValueError, match="readiness_unbounded_tokens"):
        bounded_totals([dict(input_tokens=value, output_tokens=300)])


def test_paid_membership_and_skip_slots_are_not_reallocated(packet):
    assert packet["logical_attempts"] == 24
    assert packet["calls"] == dict(protocol=48, conditional=38, expected=36, judge=0, retry=0, refetch=0)
    assert packet["paid_views"]["V0"] == packet["paid_views"]["R"] == []
    assert packet["per_arm"]["cp-a-v1"]["expected"] == 17
    assert packet["per_arm"]["cp-ab0-v1"]["expected"] == 19
    guard = next(r for r in packet["attempts"] if r["view"] == "D3.V2" and r["arm"] == "cp-a-v1")
    assert guard["expected_purposes"] == [] and guard["conditional_calls"] == 0


def test_reference_bodies_are_exact_specimens_and_not_dispatch_policies(packet):
    for sample in packet["specimens"]:
        assert request_hash(sample["body"]) == sample["measurement"]["request_hash"]
        assert sample["output_reserve"] is None
        assert sample["live_input_upper_bound"] is None
    assert packet["input_token_ceiling"] is None
    assert packet["output_token_ceiling"] is None
    assert packet["expected_path_yuan_ceiling"] is None
    assert packet["protocol_yuan_ceiling"] is None
    assert packet["proposed_authorization_yuan"] is None
    assert packet["status"] == "V02A_DEV_PAID_READINESS_BLOCKED"


def test_planning_never_constructs_provider_or_mutates_gold(monkeypatch):
    from citeweave import llm

    monkeypatch.setattr(llm.DeepSeekProvider, "__init__", lambda *a, **k: pytest.fail("provider constructed"))
    names = (
        "evals/citeweave-v02a-development-v3.json",
        "evals/approvals/citeweave-v02a-development-v3-human-gold-20261001.json",
    )
    before = {name: (ROOT / name).read_bytes() for name in names}
    path = ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    if not path.is_file():
        pytest.skip("pinned local tokenizer absent")
    result = build_readiness(ROOT, DeepSeekAccounting(path))
    assert result["execution"] == {s: "NOT_RUN" for s in ("DEV", "HARD", "REG")}
    assert before == {name: (ROOT / name).read_bytes() for name in names}
