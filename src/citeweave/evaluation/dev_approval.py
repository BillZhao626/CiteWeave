"""Pinned Human Owner attestation, separate from immutable proposal bytes.

Integrity validation, not a cryptographic personal signature or execution grant.
Only literal Development/approval paths are admitted; no dataset discovery.
"""

import hashlib
import json

from citeweave.evaluation.dev_dataset import DATASET_HASH, DATASET_ID, canonical, load_dev

APPROVAL_ID = "citeweave-v02a-development-v3-human-gold-20261001"
APPROVAL_SHA256 = "df55c120f92ee4998083872cb6bea421101fc1c9eb89c3dd730242b064debd66"
REFERENCES = (
    "docs/V02_DEV_TEST_FIRST_AUDIT_V3.md",
    "docs/V02_DEV_TEST_FIRST_AUDIT.md",
    "evals/citeweave-v02a-development-v1.json",
    "evals/citeweave-v02a-development-v2.json",
    "docs/V02_DEV_DATA_REVIEW_V1.md",
    "docs/V02_DEV_DATA_REVIEW_V2.md",
    "docs/V02_DEV_READINESS_BLOCKER.md",
)


def load_human_gold(root, *, dataset_id=DATASET_ID, split="Development", approval_id=APPROVAL_ID):
    """Future DEV must validate this plus its independent execution authority."""
    if split != "Development":
        raise ValueError("dev_split_rejected")
    if dataset_id != DATASET_ID or approval_id != APPROVAL_ID:
        raise ValueError("dev_approval_identity_rejected")
    data, sha = load_dev(root, identity=dataset_id, split=split)
    try:
        raw = (root / "evals/approvals" / (APPROVAL_ID + ".json")).read_bytes()
    except OSError as exc:
        raise ValueError("dev_approval_unavailable") from exc
    actual = hashlib.sha256(raw).hexdigest()
    if actual != APPROVAL_SHA256:
        raise ValueError("dev_approval_hash_mismatch")
    try:
        approval = json.loads(raw)
        if raw != canonical(approval):
            raise ValueError("dev_approval_noncanonical")
        expected = {
            "approval_id": APPROVAL_ID,
            "schema_revision": "v02a-human-gold-attestation-v1",
            "dataset_id": DATASET_ID,
            "dataset_version": 3,
            "dataset_sha256": DATASET_HASH,
            "decision": "APPROVE",
            "review_date": "2026-10-01",
            "reviewer_role": "Human Product Owner",
            "reviewer_personal_name": None,
            "review_units_completed": 12,
            "actual_review_minutes": None,
            "review_duration_status": "NOT_MEASURED",
            "execution_at_approval": {s: "NOT_RUN" for s in ("DEV", "HARD", "REG")},
            "provider_model_judge_outputs_used_to_tune": False,
            "paid_execution_authorized": False,
            "approved_views": {v.id: v.sha256 for v in data.views},
            "completed_label_units": ["LABEL:" + v.id for v in data.views],
        }
        if sha != DATASET_HASH or any(approval.get(k) != v for k, v in expected.items()):
            raise ValueError("dev_approval_binding_mismatch")
        refs = approval["references"]
        if set(refs) != set(REFERENCES):
            raise ValueError("dev_approval_reference_mismatch")
        for path in REFERENCES:
            if hashlib.sha256((root / path).read_bytes()).hexdigest() != refs[path]:
                raise ValueError("dev_approval_reference_mismatch")
    except (KeyError, TypeError, json.JSONDecodeError, OSError) as exc:
        raise ValueError("dev_approval_invalid") from exc
    return data, approval, actual
