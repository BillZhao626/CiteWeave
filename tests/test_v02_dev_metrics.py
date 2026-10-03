"""Meaningful hard failures, missing review, zero denominators and stop rules."""

import pytest
from test_v02_dev_execution import ROOT

from citeweave.evaluation.dev_comparison import compare_pairs, futility, pareto, schedule
from citeweave.evaluation.dev_dataset import load_dev
from citeweave.evaluation.dev_metrics import CRITICAL, aggregate_metrics, hard_gates


def test_physical_citation_and_each_critical_violation_fail_gate():
    clean = {k: 0 for k in CRITICAL}
    assert hard_gates(accepted_citations=0, valid_citations=0, violations=clean)["status"] == "NOT_VERIFIED"
    assert (
        hard_gates(accepted_citations=1, valid_citations=0, violations=clean, verified=True)["status"]
        == "FAIL"
    )
    for dimension in CRITICAL:
        bad = dict(clean, **{dimension: 1})
        assert (
            hard_gates(accepted_citations=1, valid_citations=1, violations=bad, verified=True)["status"]
            == "FAIL"
        )


def test_missing_review_and_stopped_outputs_keep_planned_denominator():
    plan = [("D1.V1", "cp-ab0-v1"), ("D1.V2", "cp-ab0-v1")]
    report = aggregate_metrics(plan, [])
    assert report["not_run"] == 2
    for field in report["quality"].values():
        assert field == dict(planned=2, attempted=0, evaluable=0, missing=2, na=0, mean=None)
    assert report["latency"]["median"] is None
    assert "p95" not in report["latency"]


def test_not_run_has_no_winner_and_fixed_execution_order():
    data, _ = load_dev(ROOT)
    report = compare_pairs([v.id for v in data.views], {}, {})
    assert report["status"] == "NOT_RUN" and report["winner"] is None
    sequence = schedule(data.views)
    assert len(sequence["paid"]) == 24 and sequence["repeat"] == 1
    assert [r["arm"] for r in sequence["paid"][:2]] == ["cp-a-v1", "cp-ab0-v1"]
    assert [r["arm"] for r in sequence["paid"] if r["view"] == "D2.V1"] == ["cp-ab0-v1", "cp-a-v1"]


def test_futility_needs_registered_reviewed_bounds_and_maintains_inconclusive():
    args = dict(
        irreversible_new_material_failures=1,
        remaining=6,
        completion_best_case_can_match=True,
        similar_cheaper_path=False,
        reviewed=True,
    )
    assert futility("DEV_FIRST_6", **args) == "STOP_FUTILITY"
    assert futility("DEV_FIRST_6", **dict(args, reviewed=False)) == "INCONCLUSIVE"
    with pytest.raises(ValueError):
        futility("AFTER_ONE_GOOD_ANSWER", **args)
    assert pareto({"quality": 1}, {"quality": 1}, {"tokens": 10}, {"tokens": 11}) == "INCONCLUSIVE"
    assert (
        pareto({"quality": 1}, {"quality": 1}, {"tokens": 10}, {"tokens": 11}, fully_reviewed=True)
        == "LEFT_DOMINATES_FINITE_SET"
    )


def test_completion_loss_fails_even_without_new_critical_error():
    from citeweave.evaluation.dev_metrics import QUALITY

    left = dict.fromkeys(QUALITY, 1)
    right = dict(left, behavior_completion=0)
    assert compare_pairs(["D1.V1"], {"D1.V1": left}, {"D1.V1": right})["noninferiority"] == "FAIL"


def test_partial_groups_zero_coverage_and_b_owns_old_recovery():
    from citeweave.evaluation.dev_arms import arm
    from citeweave.evaluation.dev_execution import DtoBackend, execute_l1
    from citeweave.evaluation.dev_fixtures import FixtureRepository
    from citeweave.evaluation.dev_metrics import history_metrics

    data, _ = load_dev(ROOT)
    repo = FixtureRepository(data)
    for vid in ("D1.V1", "D3.V2"):
        view = next(v for v in data.views if v.id == vid)
        for aid in ("cp-r-v1", "cp-a-v1", "cp-ab0-v1"):
            backend = DtoBackend(data, view, arm(aid))
            mapping = {str(r.acceptance_id): pid for pid, r in backend.refs.items()}
            receipt = execute_l1(ROOT, vid, aid, retriever=repo)
            report = history_metrics(view, receipt, mapping)
            if vid == "D3.V2" and aid != "cp-ab0-v1":
                assert not report["selected_raw_sources"]
                assert report["required_candidate"]["union"]["value"] == 0
            elif vid == "D3.V2":
                assert report["old_recovery_B"]["value"] == 1
                assert report["required_candidate"]["A"]["value"] == 0
            else:
                assert report["required_candidate"]["A"]["value"] == 1


def test_comparison_rejects_drift_and_cannot_promote_fake_scores():
    from citeweave.evaluation.dev_comparison import comparison_report
    from citeweave.evaluation.dev_execution import execute_l1
    from citeweave.evaluation.dev_fixtures import FixtureRepository
    from citeweave.evaluation.dev_metrics import QUALITY

    data, _ = load_dev(ROOT)
    receipt = execute_l1(ROOT, "D2.V1", "cp-ab0-v1", retriever=FixtureRepository(data))
    report = comparison_report(
        data,
        [receipt],
        {("D2.V1", "cp-ab0-v1"): dict.fromkeys(QUALITY, 1)},
        condition_identity="fixture-only",
    )
    assert all(c["status"] == "NOT_RUN" for c in report["comparisons"].values())
    with pytest.raises(ValueError, match="comparison_receipt_identity_conflict"):
        comparison_report(data, [dict(receipt, view_hash="0" * 64)], {}, condition_identity="fixture-only")


def test_citation_physical_identity_tamper_does_not_pass():
    from copy import deepcopy

    from citeweave.evaluation.dev_execution import execute_l1
    from citeweave.evaluation.dev_fixtures import FixtureRepository
    from citeweave.evaluation.dev_metrics import citation_checks

    data, _ = load_dev(ROOT)
    view = next(v for v in data.views if v.id == "D2.V1")
    receipt = execute_l1(ROOT, view.id, "cp-ab0-v1", retriever=FixtureRepository(data))
    assert citation_checks(data, view, receipt)["physical_validity"]["value"] == 1
    changed = deepcopy(receipt)
    changed["acceptance"]["result"]["answer"]["citations"][0]["span"]["quote"] = "fabricated"
    checked = citation_checks(data, view, changed)
    assert checked["physical_validity"]["value"] == 0 and checked["semantic_support"] is None


def test_unknown_usage_remains_unknown_and_keeps_dispatch_count():
    from citeweave.evaluation.dev_metrics import provider_resources

    report = provider_resources(
        [
            dict(
                calls=[
                    dict(
                        purpose="generation",
                        state="UNKNOWN",
                        execution_kind="provider",
                        provider_usage=None,
                        estimated_yuan=None,
                        rate_revision="test-only",
                    )
                ]
            )
        ]
    )
    p = report["provider_reported_tokens"]["generation"]
    assert p["input"] is None and p["output"] is None
    assert p["unknown"] == 1 and p["dispatched"] == 1 and report["estimated_yuan"] is None
