"""Procedural holdout admission: a selected, source-frozen candidate must exist first."""

import hashlib
import json

from citeweave.settings import ROOT

HOLDOUT_ID = "public-protocols-holdout-v1"
HOLDOUT_SHA256 = "a9347c585d08b833fd891729c8691c669d19c4af0622ce1fc127aa873eb64a03"


def runtime_sources(root=ROOT):
    paths = [*root.joinpath("src/citeweave").rglob("*.py"), *root.joinpath("prompts").glob("*.txt")]
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def require_selection(profile, judge, split, root=ROOT):
    marker = root / "evals/m3-revisit-selection.json"
    if not marker.exists():
        raise ValueError("holdout_candidate_not_frozen")
    freeze = json.loads(marker.read_text(encoding="utf-8"))
    if freeze.get("status") != "FROZEN_BEFORE_HOLDOUT" or freeze.get("holdout_sha256") != HOLDOUT_SHA256:
        raise ValueError("holdout_selection_invalid")
    if profile not in {"m3-context", freeze["selected_profile"]} or judge != "judge-v4" or split != "test":
        raise ValueError("holdout_configuration_not_frozen")
    actual = runtime_sources(root)
    if not actual or freeze["runtime_sources"] != actual:
        raise ValueError("holdout_runtime_changed_after_selection")
    return freeze


def open_sealed(path, freeze_path, expected, decision_id):
    """Procedural one-decision gate. Caller supplies exact source/profile/prompt freeze.

    Used in C only with an original dummy fixture. Real telecom content does not
    yet exist here; an independent Stage-D custodian must provision it.
    """
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("status") != "SEALED" or freeze.get("candidate") != expected:
        raise ValueError("holdout_candidate_not_frozen")
    if set(expected) != {"source_commit", "source_tree", "profile_sha256", "prompt_sha256", "dataset_sha256"}:
        raise ValueError("holdout_freeze_incomplete")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != freeze["content_sha256"]:
        raise ValueError("holdout_integrity_mismatch")
    receipt = freeze_path.with_suffix(".opened.json")
    with receipt.open("x", encoding="utf-8") as stream:
        from datetime import datetime, timezone

        json.dump(
            dict(
                decision_id=decision_id,
                opened_at=datetime.now(timezone.utc).isoformat(),
                candidate=expected,
                content_sha256=freeze["content_sha256"],
            ),
            stream,
            sort_keys=True,
        )
    return json.loads(raw)
