"""Allowlisted, hash-locked datasets. Raw third-party PDFs stay outside source control."""

import hashlib
import json

from citeweave.evaluation.holdout import HOLDOUT_ID, HOLDOUT_SHA256
from citeweave.settings import ROOT


def load_dataset(identity="public-standards-v1"):
    if identity not in {"public-standards-v1", HOLDOUT_ID}:
        raise ValueError("unknown_dataset")
    path = ROOT / "evals" / (identity + ".json")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("dataset_integrity_mismatch")
    if identity == HOLDOUT_ID and digest != HOLDOUT_SHA256:
        raise ValueError("holdout_integrity_mismatch")
    return json.loads(raw), digest
