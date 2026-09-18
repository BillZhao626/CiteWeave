"""Separate typed query and citation identities, with an explicit legacy reader."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Typed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StructuralBinding(Typed):
    document_id: str
    version_id: str
    filename: str
    source_sha256: str
    artifact_id: str
    canonical_sha: str
    tree_hash: str
    membership_hash: str
    index_name: str
    unit_kind: Literal["structural_child"] = "structural_child"
    index_profile_hash: str
    bm25_hash: str
    embedding_identity: dict
    tokenizers: dict


class StructuralSnapshot(Typed):
    revision: Literal["structural-trace-v1"] = "structural-trace-v1"
    workspace_id: str
    kb_id: str
    evidence_mode: Literal["single", "compare"]
    requested_documents: list[str]
    bindings: list[StructuralBinding]
    query_tokens: dict


class BranchHit(Typed):
    branch: Literal["dense", "bm25"]
    rank: int
    raw_score: float
    score_scope: str


class RerankerRanking(Typed):
    input_rank: int = Field(ge=1, le=20)
    output_rank: int | None = Field(default=None, ge=1, le=20)
    score: float = Field(allow_inf_nan=False)
    model: dict[str, str]
    pair_tokens: int = Field(ge=1, le=512)
    body_tokens: int = Field(ge=1, le=320)
    query_tokens: int = Field(ge=1, le=128)
    queue_ms: float = Field(ge=0, allow_inf_nan=False)
    inference_ms: float = Field(ge=0, allow_inf_nan=False)


class StructuralCandidate(Typed):
    candidate_id: str
    child_id: str
    document_id: str
    version_id: str
    artifact_id: str
    parent_id: str
    section_path: list[dict]
    evidence_ids: list[str]
    retrieval: list[BranchHit]
    rrf_rank: int
    rrf_score: float
    pool_reason: Literal["top20", "outside_pool"]
    bge: RerankerRanking | None = None
    seed_rank: int | None = None
    selection_reason: str = "outside_pool"


class PackSpan(Typed):
    label: str
    evidence_id: str
    document_id: str
    version_id: str
    parent_id: str
    seed_child_id: str
    origin: Literal["seed", "heading", "sibling"]
    cross_page: bool
    budget_before: int
    budget_after: int
    covered_by: list[str] = Field(default_factory=list)


class SourceCoverage(Typed):
    requested: list[str]
    eligible: list[str]
    selected: list[str]
    missing: list[str]
    coverage_unmet: bool


class EvidencePack(Typed):
    revision: Literal["evidence-pack-v1"] = "evidence-pack-v1"
    token_proxy: Literal["context-bge-token-proxy-v1"] = "context-bge-token-proxy-v1"
    evidence_mode: Literal["single", "compare"]
    spans: list[PackSpan]
    seed_child_ids: list[str]
    source_coverage: SourceCoverage
    degraded: Literal["degraded_reranker_unavailable"] | None = None
    fallback_reason: str | None = None
    seed_chars: int
    seed_spans: int
    seed_tokens: int
    added_chars: int
    serialized_chars: int
    serialized_tokens: int
    # This exact string, including all metadata and labels, is inserted into the prompt.
    prompt_json: str
    decisions: list[dict]


def read_query(row):
    """Never reinterpret historical candidate IDs or rewrite historical JSON."""
    revision = getattr(row, "trace_schema_revision", "legacy-v1")
    if revision == "legacy-v1":
        if row.evidence_pack is not None or row.structural_snapshot is not None:
            raise ValueError("legacy_trace_identity_mismatch")
        return row
    if revision != "structural-trace-v1":
        raise ValueError("unsupported_query_trace_revision")
    StructuralSnapshot.model_validate(row.structural_snapshot)
    for candidate in row.candidates:
        StructuralCandidate.model_validate(candidate)
    if row.evidence_pack is not None:
        EvidencePack.model_validate(row.evidence_pack)
    return row
