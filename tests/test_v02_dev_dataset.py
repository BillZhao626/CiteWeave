"""DEV admission uses one literal allowlist; no sealed-content lookup."""

import json
from pathlib import Path

import pytest

from citeweave.evaluation.dev_dataset import DATASET_ID, HARD, load_dev

ROOT = Path(__file__).parents[1]


def test_twelve_original_review_pending_views_have_stable_complete_hash():
    data, digest = load_dev(ROOT)
    assert data.dataset_id == DATASET_ID
    assert [v.id for v in data.views] == [f"D{i}.V{j}" for i in range(1, 7) for j in (1, 2)]
    assert {v.id for v in data.views if v.hard} == HARD
    assert data.owner_review == "PENDING" and data.split == "Development"
    assert load_dev(ROOT)[1] == digest
    assert data.sealed_content == "ABSENT_INACCESSIBLE"


def test_source_pdf_tamper_rejected_before_parsing(tmp_path):
    from citeweave.evaluation.dev_dataset import verify_original_sources

    data, _ = load_dev(ROOT)
    folder = tmp_path / ".runtime/evaluation/v02-dev-sources"
    folder.mkdir(parents=True)
    (folder / (data.sources[0].id + ".pdf")).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="dev_pdf_hash_mismatch"):
        verify_original_sources(tmp_path, data)


@pytest.mark.parametrize("split", ["REG", "Regression", "Holdout", "test"])
def test_other_split_rejected_before_any_path_read(monkeypatch, split):
    def forbidden(*args, **kwargs):
        pytest.fail("input paths must not be read for a forbidden split")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with pytest.raises(ValueError, match="dev_split_rejected"):
        load_dev(ROOT, split=split)


def test_unknown_identity_rejected_without_read(monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("must not open unknown identities"))
    with pytest.raises(ValueError, match="dev_dataset_rejected"):
        load_dev(ROOT, identity="../../sealed")


def test_digest_mismatch_is_not_repaired_or_refetched():
    with pytest.raises(ValueError, match="dev_hash_mismatch"):
        load_dev(ROOT, expected_hash="0" * 64)


def test_manifest_rejects_sealed_content_or_missing_view(tmp_path):
    data, _ = load_dev(ROOT)
    value = data.model_dump(mode="json")
    value["views"].pop()
    from citeweave.evaluation.dev_dataset import DevManifest

    with pytest.raises(ValueError):
        DevManifest.model_validate(value)
    value = data.model_dump(mode="json")
    value["sealed_cases"] = [{"id": "do-not-consume"}]
    with pytest.raises(ValueError):
        DevManifest.model_validate(value)


def test_file_bytes_are_canonical_json_lf():
    path = ROOT / "evals" / f"{DATASET_ID}.json"
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw == (json.dumps(json.loads(raw), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def test_revised_manifest_preserves_rejected_proposal_and_sources():
    import hashlib

    from citeweave.evaluation.dev_dataset import HISTORICAL_DATASET_HASH

    data, _ = load_dev(ROOT)
    old_path = ROOT / "evals/citeweave-v02a-development-v1.json"
    raw = old_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == HISTORICAL_DATASET_HASH
    old = json.loads(raw)
    assert data.version == 3 and data.predecessor["owner_decision"] == "D1_V2_TOPIC_RETURN_CLARIFIED"
    assert [s.model_dump(mode="json") for s in data.sources] == old["sources"]
    assert {v.id for v in data.views if v.state_only_intent} == {"D1.V2", "D3.V1"}
    before = next(v for v in old["views"] if v["id"] == "D3.V2")
    after = next(v for v in data.views if v.id == "D3.V2").model_dump(mode="json")
    after.pop("state_only_intent")
    after.pop("sha256")
    before.pop("sha256")
    assert before == after
    assert not next(v for v in data.views if v.id == "D4.V2").required_history
    with pytest.raises(ValueError, match="dev_dataset_rejected"):
        load_dev(ROOT, identity=old["dataset_id"])


def test_v3_changes_only_owner_clarified_d1_v2_labels():
    import hashlib

    data, sha = load_dev(ROOT)
    raw = (ROOT / "evals/citeweave-v02a-development-v2.json").read_bytes()
    old_sha = "3b1ef5dc37376cf26b5fb20aa8367d76ed2af5ccf376a312a62fc2d6dbcd20a7"
    assert hashlib.sha256(raw).hexdigest() == old_sha
    old = json.loads(raw)
    assert data.version == 3 and sha != old_sha
    assert data.predecessor["sha256"] == old_sha
    assert data.predecessor["dataset_id"] == old["dataset_id"]
    assert [s.model_dump(mode="json") for s in data.sources] == old["sources"]
    for current, previous in zip(data.views, old["views"], strict=True):
        value = current.model_dump(mode="json")
        if current.id != "D1.V2":
            assert value == previous
        else:
            changed = {k for k in value if value[k] != previous[k]}
            assert changed == {"topic_relation", "reference", "assertions", "sha256"}
            assert current.topic_relation == "return" and previous["topic_relation"] == "continue"
    for identity in (old["dataset_id"], "citeweave-v02a-development-v1"):
        with pytest.raises(ValueError, match="dev_dataset_rejected"):
            load_dev(ROOT, identity=identity)
