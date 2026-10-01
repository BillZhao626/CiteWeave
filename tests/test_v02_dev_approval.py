"""Approval identity/hash/semantic binding, without providers or sealed input."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import citeweave.evaluation.dev_approval as module
from citeweave.evaluation.dev_dataset import DATASET_HASH, DATASET_ID, canonical

ROOT = Path(__file__).parents[1]


def test_exact_human_approval_is_external_to_unchanged_pending_manifest():
    data, approval, sha = module.load_human_gold(ROOT)
    assert sha == module.APPROVAL_SHA256
    assert data.owner_review == "PENDING" and approval["decision"] == "APPROVE"
    assert approval["approved_views"] == {v.id: v.sha256 for v in data.views}
    assert len(approval["completed_label_units"]) == approval["review_units_completed"] == 12
    assert approval["actual_review_minutes"] is approval["reviewer_personal_name"] is None
    assert not approval["paid_execution_authorized"]
    assert hashlib.sha256((ROOT / "evals" / (DATASET_ID + ".json")).read_bytes()).hexdigest() == DATASET_HASH


@pytest.fixture
def copied(tmp_path):
    for path in (
        *module.REFERENCES,
        "docs/V02_COMPARISON_PROTOCOL.md",
        "evals/" + DATASET_ID + ".json",
        "evals/approvals/" + module.APPROVAL_ID + ".json",
    ):
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, dest)
    return tmp_path


@pytest.mark.parametrize(
    "damage", ["decision", "dataset_id", "dataset_version", "dataset_sha256", "approved_views", "approval_id"]
)
def test_binding_fails_even_if_changed_artifact_hash_is_rebound(copied, monkeypatch, damage):
    path = copied / "evals/approvals" / (module.APPROVAL_ID + ".json")
    value = json.loads(path.read_bytes())
    if damage == "approved_views":
        value[damage]["D1.V2"] = "0" * 64
    else:
        value[damage] = 4 if damage == "dataset_version" else "WRONG"
    raw = canonical(value)
    path.write_bytes(raw)
    monkeypatch.setattr(module, "APPROVAL_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="dev_approval_binding_mismatch"):
        module.load_human_gold(copied)


def test_artifact_and_dataset_drift_fail_closed(copied):
    path = copied / "evals/approvals" / (module.APPROVAL_ID + ".json")
    raw = path.read_bytes()
    path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="dev_approval_hash_mismatch"):
        module.load_human_gold(copied)
    path.write_bytes(raw)
    dataset = copied / "evals" / (DATASET_ID + ".json")
    dataset.write_bytes(dataset.read_bytes() + b" ")
    with pytest.raises(ValueError, match="dev_hash_mismatch"):
        module.load_human_gold(copied)


@pytest.mark.parametrize(
    "kwargs",
    [{"split": "REG"}, {"split": "Holdout"}, {"dataset_id": "other"}, {"approval_id": "../../sealed"}],
)
def test_unapproved_identity_or_split_rejected_before_input_read(monkeypatch, kwargs):
    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("no input access permitted"))
    with pytest.raises(ValueError):
        module.load_human_gold(ROOT, **kwargs)


def test_missing_approval_does_not_invent_gold(copied):
    (copied / "evals/approvals" / (module.APPROVAL_ID + ".json")).unlink()
    with pytest.raises(ValueError, match="dev_approval_unavailable"):
        module.load_human_gold(copied)
