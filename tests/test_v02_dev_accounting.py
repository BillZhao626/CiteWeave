"""Pinned real offline tokenizer; no provider request is sent."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_v02_dev_execution import ROOT

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_runtime import PhasePlan, RuntimeCalls
from citeweave.evaluation.dev_accounting import offline_measurements
from citeweave.evaluation.dev_dataset import load_dev
from citeweave.evaluation.dev_execution import execute_l1
from citeweave.evaluation.dev_fixtures import FixtureRepository
from citeweave.llm import completion_payload
from citeweave.provider_accounting import DeepSeekAccounting


@pytest.fixture
def accounting():
    path = ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    if not path.is_file():
        pytest.skip("pinned ignored tokenizer absent; real accounting is NOT_VERIFIED")
    return DeepSeekAccounting(path)


def test_d6_full_real_tokenizer_boundary_l_minus_one_l_l_plus_one(accounting, monkeypatch):
    data, _ = load_dev(ROOT)
    receipt = execute_l1(ROOT, "D6.V1", "cp-ab0-v1", retriever=FixtureRepository(data))
    messages = receipt["calls"][0]["messages"]
    view = next(v for v in data.views if v.id == "D6.V1")
    output = len(accounting.tokenizer.encode(view.reference_answer, add_special_tokens=False).ids)
    length = accounting.measure(completion_payload(messages, "deepseek-flash", output))["input_tokens"]
    import citeweave.conversation_runtime as runtime

    monkeypatch.setattr(runtime, "settings", lambda: SimpleNamespace(deepseek_model="deepseek-flash"))
    for cap in (length - 1, length, length + 1):
        policy = SimpleNamespace(
            phases=(PhasePlan(purpose="generation", input_tokens=cap, output_tokens=output),),
            context_max_bytes=100000,
        )
        calls = RuntimeCalls(
            uuid4(),
            SimpleNamespace(),
            policy,
            accounting,
            provider_factory=lambda: pytest.fail("no dispatch"),
        )
        if cap < length:
            with pytest.raises(CoreConflict, match="provider_input_authorization_exceeded"):
                calls.request("generation", messages)
        else:
            _, measured = calls.request("generation", messages)
            assert measured["input_tokens"] == length


def test_reference_specimen_does_not_freeze_live_caps_or_money(accounting):
    data, _ = load_dev(ROOT)
    receipt = execute_l1(ROOT, "D2.V1", "cp-ab0-v1", retriever=FixtureRepository(data))
    measured = offline_measurements(data, [receipt], accounting)
    assert measured["worst_case_dev_yuan"] is None
    assert measured["actual_external_calls"] == 0 and measured["actual_paid_cost_yuan"] == 0
    assert measured["paid_fixture_ranges"]["generation"]["live_output_reserve"] is None
    assert measured["per_call"][0]["body"]["messages"] == receipt["calls"][0]["messages"]


def test_official_rate_snapshot_drift_is_not_silently_current(accounting, tmp_path):
    data, _ = load_dev(ROOT)
    path = tmp_path / "pricing.html"
    path.write_text("changed provider page", encoding="utf-8")
    with pytest.raises(ValueError, match="dev_official_identity_mismatch"):
        offline_measurements(data, [], accounting, official_snapshot=path)
