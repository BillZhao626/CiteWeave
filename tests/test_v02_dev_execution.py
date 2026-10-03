"""Bounded fake L1 fixtures only; no semantic candidate results or DEV run."""

from pathlib import Path

import pytest

from citeweave.evaluation.dev_arms import ARM_IDS
from citeweave.evaluation.dev_dataset import load_dev
from citeweave.evaluation.dev_execution import execute_l1, save_receipt
from citeweave.evaluation.dev_fixtures import FixtureRepository

ROOT = Path(__file__).parents[1]


@pytest.fixture
def repository():
    data, _ = load_dev(ROOT)
    return FixtureRepository(data)


def test_all_views_generate_typed_receipts_with_zero_external_dispatch(repository, monkeypatch):
    import citeweave.llm

    monkeypatch.setattr(
        citeweave.llm.DeepSeekProvider,
        "__init__",
        lambda *a, **k: pytest.fail("external provider must not be constructed"),
    )
    data, _ = load_dev(ROOT)
    for view in data.views:
        for config in ARM_IDS[1:]:
            receipt = execute_l1(ROOT, view.id, config, retriever=repository)
            assert receipt["external_calls"] == 0 and receipt["execution_kind"] == "FAKE_L1_NOT_DEV"
            assert receipt["view_hash"] == view.sha256 and receipt["arm_config_hash"]
            assert receipt["runtime_sources"] and receipt["human_review"] is None
            assert receipt["semantic_quality"] is None
            if config == ARM_IDS[-1]:
                assert receipt["status"] == "COMPLETED", (view.id, receipt.get("error_code"))
                assert receipt["acceptance"]["durable"] is False


@pytest.mark.parametrize("config", ARM_IDS[1:3])
def test_correction_boundary_fails_before_interpretation_and_generation(repository, config):
    result = execute_l1(ROOT, "D3.V2", config, retriever=repository)
    assert result["status"] == "GUARD_FAILURE" and result["error_code"] == "incomplete_group"
    assert not result["calls"] and result["acceptance"] is None


def test_clarification_and_use_original_skip_purposes(repository):
    clarify = execute_l1(ROOT, "D4.V1", ARM_IDS[-1], retriever=repository)
    assert [c["purpose"] for c in clarify["calls"]] == ["interpretation"]
    direct = execute_l1(ROOT, "D2.V1", ARM_IDS[-1], retriever=repository)
    assert [c["purpose"] for c in direct["calls"]] == ["generation"]


def test_receipts_are_write_once_and_do_not_retry(repository, tmp_path):
    receipt = execute_l1(ROOT, "D2.V1", ARM_IDS[-1], retriever=repository)
    path = tmp_path / "receipt.json"
    save_receipt(path, receipt)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_receipt(path, receipt)
    assert path.read_bytes() == original


def test_d6_complete_context_capacity_boundary_keeps_overflow_distinct(repository):
    from citeweave.conversation_evidence import GenerationContext

    full = execute_l1(ROOT, "D6.V1", ARM_IDS[-1], retriever=repository)
    context = GenerationContext.model_validate(full["calls"][0]["context"])
    limit = len(context.model_dump_json().encode())
    for capacity in (limit - 1, limit, limit + 1):
        result = execute_l1(ROOT, "D6.V1", ARM_IDS[-1], retriever=repository, test_max_input_bytes=capacity)
        if capacity < limit:
            assert result["error_code"] == "conversation_context_overflow"
            assert result["acceptance"] is None and not result["calls"]
        else:
            assert result["status"] == "COMPLETED" and len(result["calls"]) == 1


def test_harness_rejects_holdout_before_any_file_or_retriever_access(monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("must not read split input"))
    with pytest.raises(ValueError, match="dev_split_rejected"):
        execute_l1(ROOT, "sealed-unknown", "cp-ab0-v1", retriever=None, split="Holdout")


def test_clarification_closed_loop_keeps_identity_and_unrun_denominator(repository):
    from citeweave.evaluation.dev_execution import closed_loop_l1

    result = closed_loop_l1(ROOT, "cp-ab0-v1", retriever=repository)
    assert result["branch_status"] == "TAKEN" and result["planned"] == 2
    first, second = result["receipts"]
    assert first["status"] == second["status"] == "COMPLETED"
    assert first["conversation_id"] == second["conversation_id"]
    assert first["run_id"] != second["run_id"] and first["turn_id"] != second["turn_id"]
    assert second["prefix_receipts"][-1]["kind"] == "ACTUAL_PRIOR_L1_CONTROL_ACCEPTANCE_NOT_MANUAL_SEED"
    assert second["interpretation"]["delta"]["deactivate"]
    skipped = closed_loop_l1(ROOT, "cp-ab0-v1", retriever=repository, allow_branch=False)
    assert skipped["planned"] == 2 and skipped["not_run"] == ["D4.V2"]


@pytest.mark.parametrize("vid", ["D1.V2", "D3.V1"])
def test_a_state_intent_succeeds_without_old_raw_or_b_credit(repository, vid):
    from citeweave.evaluation.dev_arms import arm
    from citeweave.evaluation.dev_execution import DtoBackend
    from citeweave.evaluation.dev_metrics import citation_checks, history_metrics

    data, _ = load_dev(ROOT)
    view = next(v for v in data.views if v.id == vid)
    backend = DtoBackend(data, view, arm("cp-a-v1"))
    names = {str(ref.acceptance_id): pid for pid, ref in backend.refs.items()}
    a = execute_l1(ROOT, vid, "cp-a-v1", retriever=repository)
    r = execute_l1(ROOT, vid, "cp-r-v1", retriever=repository)
    ab = execute_l1(ROOT, vid, "cp-ab0-v1", retriever=repository)
    assert a["status"] == ab["status"] == "COMPLETED" and r["status"] == "GUARD_FAILURE"
    old = str(backend.refs["T1"].acceptance_id)
    assert old not in {f["acceptance_id"] for f in a["raw_fetches"]}
    metrics = history_metrics(view, a, names)
    assert metrics["old_candidate_recovery"]["value"] == 0
    assert metrics["old_recovery_B"]["value"] == 0
    assert metrics["state_intent_items_used"] == 1
    assert not a["calls"][-1]["context"]["history"]
    assert a["acceptance"] is None and a["publication"] == "EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED"
    assert citation_checks(data, view, a)["physical_validity"]["value"] == 1
    ab_names = {p["acceptance_id"]: p["prefix_id"] for p in ab["prefix_receipts"]}
    ab_metrics = history_metrics(view, ab, ab_names)
    assert ab_metrics["old_recovery_B"]["value"] == 1
    assert ab_metrics["old_final_recovery"]["value"] == 1
    assert metrics["old_final_recovery"]["value"] == 0


def test_d4_v2_has_no_required_history_coverage(repository):
    from citeweave.evaluation.dev_metrics import history_metrics

    data, _ = load_dev(ROOT)
    view = next(v for v in data.views if v.id == "D4.V2")
    assert not view.required_history
    receipt = execute_l1(ROOT, view.id, "cp-ab0-v1", retriever=repository)
    assert history_metrics(view, receipt, {})["required_candidate"]["union"]["status"] == "N/A"
    assert history_metrics(view, receipt, {})["generation_coverage"]["status"] == "N/A"


@pytest.mark.parametrize("damage", ["value", "state_id", "rewrite"])
def test_state_intent_rejects_unbound_or_drifting_facts(repository, monkeypatch, damage):
    from uuid import uuid4

    import citeweave.evaluation.dev_execution as execution

    original = execution.fixture_draft

    def altered(view, backend, context):
        draft = original(view, backend, context)
        if damage == "rewrite":
            return draft.model_copy(update={"rewrite": draft.rewrite.model_copy(update={"text": "drift"})})
        facts = tuple(
            f.model_copy(update={"value": "invented"} if damage == "value" else {"state_item_id": uuid4()})
            if f.source
            else f
            for f in draft.facts
        )
        return draft.model_copy(update={"facts": facts})

    monkeypatch.setattr(execution, "fixture_draft", altered)
    result = execute_l1(ROOT, "D1.V2", "cp-a-v1", retriever=repository)
    assert result["status"] == "GUARD_FAILURE" and result["acceptance"] is None
    assert all(c["purpose"] != "generation" for c in result["calls"])


def test_state_cannot_supply_documentary_evidence(repository):
    class InvalidEvidence:
        def retrieve(self, workspace, scope, query):
            current = repository.retrieve(workspace, scope, query)
            return current.model_copy(update={"citations": ()})

    result = execute_l1(ROOT, "D3.V1", "cp-a-v1", retriever=InvalidEvidence())
    assert result["status"] == "GUARD_FAILURE" and result["acceptance"] is None
    assert result["error_code"] == "documentary_pack_invalid"
    assert all(c["purpose"] != "generation" for c in result["calls"])


def test_topic_return_does_not_invalidate_pending_semantic_state(repository):
    from citeweave.evaluation.dev_metrics import history_metrics

    data, _ = load_dev(ROOT)
    expected = {"D1.V1": "continue", "D1.V2": "return", "D3.V1": "return"}
    for vid, relation in expected.items():
        view = next(v for v in data.views if v.id == vid)
        assert view.topic_relation == relation
        for aid in ARM_IDS[1:]:
            result = execute_l1(ROOT, vid, aid, retriever=repository)
            if aid == "cp-r-v1" and vid != "D1.V1":
                assert result["status"] == "GUARD_FAILURE"
                assert result["error_code"] == "interpretation_source_unavailable"
                continue
            assert result["status"] == "COMPLETED", result.get("error_code")
            assert result["interpretation"]["topic_relation"] == relation
            if aid == "cp-a-v1" and vid != "D1.V1":
                context = result["calls"][-1]["context"]
                assert len(context["working_state"]) == 1 and context["working_state"][0]["active"]
                assert not context["history"] and not result["interpretation"]["delta"]["deactivate"]
                names = {p["acceptance_id"]: p["prefix_id"] for p in result["prefix_receipts"]}
                metrics = history_metrics(view, result, names)
                assert metrics["old_recovery_B"]["value"] == metrics["old_candidate_recovery"]["value"] == 0
                assert metrics["state_intent_items_used"] == 1
