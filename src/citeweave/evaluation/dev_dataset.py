"""Original DEV proposals, byte-locked admission and no sealed-resource discovery."""

import hashlib
import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

from pydantic import model_validator

from citeweave.conversation_contract import DurableDTO, ResolvedSignals

DATASET_ID = "citeweave-v02a-development-v3"
DATASET_HASH = "a01953930e2893065dc6f724b6ce896015124744d6614ac14a6354f087636023"
V2_DATASET_HASH = "3b1ef5dc37376cf26b5fb20aa8367d76ed2af5ccf376a312a62fc2d6dbcd20a7"
HISTORICAL_DATASET_HASH = "f33f96f51f1e5bf310bc9034e673c40ffd74f6a1fe91a4a62d2a1af45be0dd44"
HARD = {"D1.V2", "D3.V1", "D3.V2", "D4.V1", "D5.V2", "D6.V1", "D6.V2"}
NAMESPACE = UUID("03cf46c7-cb8a-5400-a214-270cfc7f6d0e")


def identity(key):
    return uuid5(NAMESPACE, key)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class Source(DurableDTO):
    id: str
    family: str
    document_id: UUID
    version_id: UUID
    text: str
    canonical_sha256: str
    pdf_sha256: str
    pdf_box: tuple[float, float, float, float]
    provenance: Literal["original_AI_assisted_MIT_review_pending"]


class SeedValue(DurableDTO):
    key: str
    kind: Literal["entity", "constraint", "topic", "ambiguity"]
    value: str
    replaces: str | None = None


class Prefix(DurableDTO):
    id: str
    question: str
    signals: ResolvedSignals
    state: tuple[SeedValue, ...] = ()
    correction: str | None = None
    scope: tuple[str, ...]
    control: Literal["intent_seed", "clarification"] = "intent_seed"


class Group(DurableDTO):
    id: str
    alternatives: tuple[tuple[str, ...], ...]
    old: bool = False


class Assertion(DurableDTO):
    id: str
    dimension: str
    statement: str
    severity: Literal["critical", "material", "ordinary"] = "critical"


class View(DurableDTO):
    id: str
    family: str
    primary_category: str
    categories: tuple[str, ...]
    hard: bool
    prefix: tuple[Prefix, ...]
    question: str
    scope: tuple[str, ...]
    query_signals: ResolvedSignals
    required_history: tuple[Group, ...]
    irrelevant_history: tuple[str, ...]
    facts: tuple[tuple[str, str, str], ...]  # kind, value, prefix source or CURRENT
    protected: tuple[tuple[str, str], ...]
    dependency: Literal["none", "required", "unresolved"]
    topic_relation: Literal["continue", "shift", "return"]
    outcome: Literal["documentary_answer", "clarification", "evidence_insufficient"]
    reference: str
    reference_answer: str
    required_aspects: tuple[str, ...]
    evidence_support: tuple[tuple[str, int, int], ...]
    assertions: tuple[Assertion, ...]
    allowed_equivalence: tuple[str, ...]
    diagnostic_limits: dict[str, str]
    state_only_intent: bool
    sha256: str


class DevManifest(DurableDTO):
    schema_revision: Literal["v02a-multiturn-dev-v3"]
    dataset_id: Literal["citeweave-v02a-development-v3"]
    version: Literal[3]
    predecessor: dict[str, str]
    split: Literal["Development"]
    owner_review: Literal["PENDING"]
    sealed_content: Literal["ABSENT_INACCESSIBLE"]
    author: str
    license: Literal["MIT"]
    protocol_sha256: str
    clarification_revision: Literal["owner-topic-focus-return-20261001"]
    seed: Literal[20260929]
    repeat: Literal[1]
    sources: tuple[Source, ...]
    views: tuple[View, ...]
    category_coverage: dict[str, tuple[str, ...]]
    connectivity_review: Literal["OWNER_PENDING_NO_CAL_OR_G_REUSE"]
    closed_loop_branch: dict[str, str]

    @model_validator(mode="after")
    def integrity(self):
        ids = [v.id for v in self.views]
        if ids != [f"D{i}.V{j}" for i in range(1, 7) for j in (1, 2)]:
            raise ValueError("dev_membership_mismatch")
        if {v.id for v in self.views if v.hard} != HARD:
            raise ValueError("dev_hard_membership_mismatch")
        if {v.id for v in self.views if v.state_only_intent} != {"D1.V2", "D3.V1"}:
            raise ValueError("dev_state_intent_membership_mismatch")
        if self.predecessor != dict(
            dataset_id="citeweave-v02a-development-v2",
            sha256=V2_DATASET_HASH,
            owner_decision="D1_V2_TOPIC_RETURN_CLARIFIED",
        ):
            raise ValueError("dev_predecessor_identity_mismatch")
        if next(v for v in self.views if v.id == "D1.V2").topic_relation != "return":
            raise ValueError("dev_owner_topic_relation_mismatch")
        sources = {s.id: s for s in self.sources}
        if len(sources) != len(self.sources) or len({s.version_id for s in self.sources}) != len(sources):
            raise ValueError("dev_source_identity_mismatch")
        for s in self.sources:
            if hashlib.sha256(s.text.encode()).hexdigest() != s.canonical_sha256:
                raise ValueError("dev_canonical_hash_mismatch")
        for v in self.views:
            if (
                v.family != v.id.split(".")[0]
                or digest(v.model_dump(mode="json", exclude={"sha256"})) != v.sha256
            ):
                raise ValueError("dev_view_hash_mismatch")
            prefix = {p.id for p in v.prefix}
            if len(prefix) != len(v.prefix) or not set(v.scope) <= sources.keys():
                raise ValueError("dev_scope_or_prefix_mismatch")
            for p in v.prefix:
                if not set(p.scope) <= sources.keys() or p.correction and p.correction not in prefix:
                    raise ValueError("dev_prefix_reference_mismatch")
            for group in v.required_history:
                if not group.alternatives or any(
                    not alt or not set(alt) <= prefix for alt in group.alternatives
                ):
                    raise ValueError("dev_history_label_mismatch")
            for sid, start, end in v.evidence_support:
                if sid not in sources or not 0 <= start < end <= len(sources[sid].text):
                    raise ValueError("dev_evidence_label_mismatch")
            if not v.assertions or not any(a.severity == "critical" for a in v.assertions):
                raise ValueError("dev_critical_labels_missing")
        return self


def load_dev(root: Path, *, identity=DATASET_ID, split="Development", expected_hash=None):
    # Reject identities BEFORE filesystem access, no glob/rglob/dataset catalog.
    if split != "Development":
        raise ValueError("dev_split_rejected")
    if identity != DATASET_ID:
        raise ValueError("dev_dataset_rejected")
    raw = (root / "evals" / (DATASET_ID + ".json")).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != DATASET_HASH or expected_hash is not None and actual != expected_hash:
        raise ValueError("dev_hash_mismatch")
    data = DevManifest.model_validate_json(raw)
    if raw != canonical(data.model_dump(mode="json")):
        raise ValueError("dev_noncanonical_manifest")
    protocol = (root / "docs/V02_COMPARISON_PROTOCOL.md").read_bytes()
    if hashlib.sha256(protocol).hexdigest() != data.protocol_sha256:
        raise ValueError("dev_protocol_drift")
    return data, actual


def verify_original_sources(root, data):
    """Explicit seven PDF paths; no dataset discovery or sealed access."""
    import io

    import pdfplumber

    for source in data.sources:
        raw = (root / ".runtime/evaluation/v02-dev-sources" / (source.id + ".pdf")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source.pdf_sha256:
            raise ValueError("dev_pdf_hash_mismatch")
        with pdfplumber.open(io.BytesIO(raw)) as parsed:
            text = "\n".join(page.extract_text() for page in parsed.pages)
        if text != source.text:
            raise ValueError("dev_pdf_canonical_mismatch")
    return len(data.sources)
