"""Review budget, reports and accounting stay provider-free and unsigned."""

import pytest
from test_v02_dev_execution import ROOT

from citeweave.evaluation.dev_dataset import DATASET_HASH, load_dev
from citeweave.evaluation.dev_review import review_plan, review_surface


def test_complete_unsigned_review_surface_and_bounded_units():
    data, _ = load_dev(ROOT)
    plan = review_plan(data)
    assert len(plan["units"]) == 48 and len({u["id"] for u in plan["units"]}) == 48
    assert plan["maximum_minutes"] == 384
    assert all(u["owner_decision"] is None and u["actual_minutes"] is None for u in plan["units"])
    surface = review_surface(data)
    assert DATASET_HASH in surface and "PENDING" in surface
    assert all(v.id in surface and v.question in surface and v.sha256 in surface for v in data.views)
    assert all(s.pdf_sha256 in surface and str(s.version_id) in surface for s in data.sources)


def test_unknown_execution_identity_rejected_without_reading_sealed_path(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("no content access allowed"))
    with pytest.raises(ValueError, match="dev_split_rejected"):
        load_dev(ROOT, split="Holdout")


def test_frozen_review_plan_records_owner_labels_but_no_output_scores_or_minutes():
    from citeweave.evaluation.dev_approval import load_human_gold

    data, approval, _ = load_human_gold(ROOT)
    plan = review_plan(data, approval=approval)
    labels = [u for u in plan["units"] if u["kind"] == "label"]
    assert len(labels) == plan["label_units_completed"] == 12
    assert all(u["owner_decision"] == "APPROVE" and u["actual_minutes"] is None for u in labels)
    assert all(u["owner_decision"] is None for u in plan["units"] if u["kind"] != "label")
    surface = review_surface(data, approval=approval)
    assert "Human Gold APPROVED / FROZEN" in surface and "NOT_MEASURED" in surface
