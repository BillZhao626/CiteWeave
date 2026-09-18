"""HTTP and SSE contracts; OpenAPI generates the browser's domain types."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, computed_field, model_validator

from citeweave.evidence import EvidenceSpan
from citeweave.profiles import QueryProfile
from citeweave.query_evidence import EvidencePack, StructuralCandidate, StructuralSnapshot


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)


class KnowledgeBaseCreate(Contract):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)


class KnowledgeBase(Contract):
    id: UUID
    workspace_id: UUID
    name: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime


class Login(Contract):
    token: SecretStr


class Version(Contract):
    id: UUID
    document_id: UUID
    kb_id: UUID
    sequence: int
    filename: str
    license: str
    source_sha256: str
    status: str
    chunk_count: int
    page_count: int
    profile: dict
    index_collection: str | None
    created_at: datetime


class Job(Contract):
    id: UUID
    document_version_id: UUID
    status: str
    kind: str
    attempt: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    absolute_deadline: datetime | None = None
    pipeline_version: str
    events: list[dict]


class UploadResult(Contract):
    version: Version
    job: Job


class Document(Contract):
    id: UUID
    kb_id: UUID
    title: str
    active_version_id: UUID | None
    versions: list[UploadResult]


class QueryCreate(Contract):
    kb_id: UUID
    question: str = Field(min_length=1, max_length=512)
    profile: QueryProfile = "m3-context"
    evidence_mode: Literal["auto", "single", "compare"] = "auto"
    document_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=10)

    @model_validator(mode="after")
    def query_contract(self):
        if self.profile != "telecom-structural-v1" and (
            len(self.question) > 160 or self.evidence_mode != "auto" or self.document_ids is not None
        ):
            raise ValueError("legacy_query_contract")
        if self.document_ids and len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("duplicate_document_scope")
        return self


class Citation(Contract):
    label: str
    evidence_id: UUID
    document_version_id: UUID
    filename: str
    span: EvidenceSpan
    content_url: str


class Answer(Contract):
    run_id: UUID
    text: str
    citations: list[Citation]
    prompt_version: str
    usage: dict | None = None
    estimated_yuan: float | None = None
    actual_cost: Literal["unavailable"] = "unavailable"


class StreamEvent(Contract):
    type: Literal["stage", "delta", "final", "error"]
    run_id: UUID
    stage: str | None = None
    text: str | None = None
    provisional: bool = False
    answer: Answer | None = None
    code: str | None = None


class Run(Contract):
    id: UUID
    kb_id: UUID
    question: str
    trace_schema_revision: Literal["legacy-v1", "structural-trace-v1"] = "legacy-v1"
    structural_snapshot: StructuralSnapshot | None = None
    evidence_pack: EvidencePack | None = None
    status: str
    versions: list[str]
    candidates: list[dict]
    result: Answer | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None
    index_bindings: dict[str, str]
    runtime_config: dict
    stages: list[dict]
    calls: list[dict]
    usage: dict | None
    estimated_yuan: float | None
    reserved_yuan: float
    error_category: str | None
    absolute_deadline: datetime | None = None
    runtime_policy: str | None = None
    actual_charge: Literal["unavailable"] = "unavailable"

    @computed_field
    @property
    def structural_candidates(self) -> list[StructuralCandidate] | None:
        if self.trace_schema_revision == "structural-trace-v1":
            return [StructuralCandidate.model_validate(c) for c in self.candidates]
        return None
