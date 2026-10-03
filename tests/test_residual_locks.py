"""Current Human-approved RC locks replay exactly; no new Human judgments.

The immutable paid receipts and approved adjudication are local-only fixtures.
Public checkouts skip their absence rather than manufacturing paid evidence.
"""

import json
from pathlib import Path

import pytest

from citeweave.conversation_interpretation import InterpretationDraft, InterpretationInput, interpret
from citeweave.evaluation.dev_dataset import digest
from citeweave.evaluation.dev_dispatch import slots_for_view
from citeweave.evaluation.dev_residual_closure import refreeze_residual
from citeweave.evaluation.dev_state import state_intent
from citeweave.provider_accounting import DeepSeekAccounting
from citeweave.runtime_residual_closure import decode_residual

ROOT = Path(__file__).resolve().parents[1]
PASS_LOCKS = (
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
    "D4.V1:cp-ab0-v1",
    "D4.V2:cp-a-v1",
    "D4.V2:cp-ab0-v1",
    "D5.V1:cp-a-v1",
    "D5.V1:cp-ab0-v1",
    "D5.V2:cp-a-v1",
    "D5.V2:cp-ab0-v1",
    "D6.V1:cp-a-v1",
    "D6.V1:cp-ab0-v1",
    "D6.V2:cp-a-v1",
    "D6.V2:cp-ab0-v1",
)
RESIDUALS = ("D1.V2:cp-a-v1", "D1.V2:cp-ab0-v1")


@pytest.fixture(scope="module")
def frozen():
    folder = ROOT / ".runtime/evaluation"
    paths = {
        "execution": folder / "rc-closure/execution-reconciliation.json",
        "prior": folder / "rc-closure/contracts.json",
        "original": folder / "0012-accepted-runtime/contracts.json",
        "adjudication": folder / "residual-closure/human-adjudication.json",
        "tokenizer": ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json",
    }
    if not all(p.exists() for p in paths.values()):
        pytest.skip("immutable local RC receipts/approved Human v5 adjudication absent in public checkout")
    execution = json.loads(paths["execution"].read_bytes())
    cases = {c["case_id"]: c for c in execution["cases"]}
    prior = json.loads(paths["prior"].read_bytes())
    original = json.loads(paths["original"].read_bytes())
    adjudication = json.loads(paths["adjudication"].read_bytes())
    labels = {row["case"]: row["rc_human_label"] for row in adjudication["rows"]}
    assert len(labels) == len(adjudication["rows"]) == 24
    assert {key for key, label in labels.items() if label == "PASS"} == set(PASS_LOCKS)
    assert {key for key, label in labels.items() if label == "FAIL"} == set(RESIDUALS)
    assert set(labels) == set(cases)
    assert adjudication["active_human_pass_count"] == 22
    assert set(adjudication["active_residuals"]) == set(RESIDUALS)
    original_labels = {row["case"]: row["rc_human_v5_original"] for row in adjudication["rows"]}
    assert {key for key, label in original_labels.items() if label == "FAIL"} == {
        *RESIDUALS,
        "D5.V1:cp-ab0-v1",
    }
    assert adjudication["human_correction"]["text"]
    assert all(row["new_human_label"] == "PENDING" for row in adjudication["rows"])
    before = digest(original)
    new = refreeze_residual(original, DeepSeekAccounting(paths["tokenizer"]), ROOT)
    assert digest(original) == before
    return dict(cases=cases, prior=prior, new=new, labels=labels)


def probe_for(packet, key):
    return next(probe for probe in packet["probes"] if probe["view"] + ":" + probe["arm"] == key)


def replay(case, packet):
    result = case["result"]
    context = InterpretationInput.model_validate(result["target_context"]["input"])
    raw = result.get("provider_outputs", {}).get("interpretation")
    draft = (
        decode_residual(raw, context, fact_bytes_cap=packet["normalized_fact_bytes_cap"])
        if raw is not None
        else InterpretationDraft.model_validate(
            probe_for(packet, case["case_id"])["reviewed_independent_draft"]
        )
    )
    return (
        state_intent(context, draft)
        if result["target_context"]["state_only"]
        else interpret(context, draft=draft)
    )


@pytest.mark.parametrize("key", PASS_LOCKS)
def test_all22_current_approved_locks_preserve_exact_interpretation_query_and_delta(frozen, key):
    assert frozen["labels"][key] == "PASS"
    case = frozen["cases"][key]
    probe = probe_for(frozen["new"], key)
    if not probe["dispatch_slots"]:
        context = InterpretationInput.model_validate(case["result"]["target_context"]["input"])
        assert context.history.failure == "incomplete_group"
        assert case["result"]["result"] == {"calls": 0, "guard": "incomplete_group"}
        view, aid = key.split(":")
        assert slots_for_view(type("View", (), {"id": view})(), aid) == ()
        assert not case["result"].get("phase_ids")
        return
    current = replay(case, frozen["new"])
    assert current.model_dump(mode="json") == case["result"]["result"]["interpretation"]


@pytest.mark.parametrize(
    "key",
    tuple(
        f"{view}:{arm}" for view in ("D2.V1", "D2.V2", "D6.V1", "D6.V2") for arm in ("cp-a-v1", "cp-ab0-v1")
    ),
)
def test_independent_generation_user_and_evidence_requests_remain_exact(frozen, key):
    new = probe_for(frozen["new"], key)
    prior = probe_for(frozen["prior"], key)
    assert new["dispatch_slots"] == prior["dispatch_slots"] == ["generation"]
    assert new["reviewed_independent_draft"] == prior["reviewed_independent_draft"]
    assert new["generation_request"] == prior["generation_request"]
    assert new["generation_measurement"] == prior["generation_measurement"]
    assert frozen["cases"][key]["result"].get("provider_outputs", {}).get("interpretation") is None


def test_all_current_valid_outputs_are_covered_without_creating_new_human_labels(frozen):
    # This equality describes this approved fixture only. Mechanical completion
    # never supplies the semantic label; those labels come from Human approval.
    assert {key for key, case in frozen["cases"].items() if case["status"] == "COMPLETED"} == set(PASS_LOCKS)
    assert len(PASS_LOCKS) == 22 and len(RESIDUALS) == 2
