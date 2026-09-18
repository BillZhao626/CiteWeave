"""Owner-scoped production operations; every route is an API consumer contract."""

from typing import Literal
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import Field
from sqlalchemy import func, select

from citeweave import lifecycle, schemas
from citeweave.db import transaction
from citeweave.domain import (
    CircuitRow,
    DocumentRow,
    EvalCaseRow,
    EvalRunRow,
    IngestionJobRow,
    KnowledgeBaseRow,
    OperationRow,
    QueryRunRow,
    VersionRow,
)
from citeweave.evaluation import service
from citeweave.evaluation.comparison import compare
from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.reporting import markdown, refresh
from citeweave.profiles import QueryProfile
from citeweave.settings import settings


class Operation(schemas.Contract):
    id: UUID
    kind: str
    target: str
    status: str
    detail: dict
    created_at: schemas.datetime


class GCEntry(schemas.Contract):
    name: str
    disposition: Literal["candidate", "protected"]
    reasons: list[str]
    exists: bool
    state: str
    version_id: UUID | None


class GCDelete(schemas.Contract):
    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_-]+$")


class Rollback(schemas.Contract):
    target_version_id: UUID
    expected_active_version_id: UUID


class EvaluationCreate(schemas.Contract):
    kb_id: UUID
    dataset_id: Literal["public-standards-v1", "public-protocols-holdout-v1"] = "public-standards-v1"
    split: Literal["dev", "test", "all"] = "dev"
    profile: QueryProfile = "m3-context"
    judge_profile: Literal["judge-v1", "judge-v2", "judge-v3", "judge-v4"] = "judge-v4"
    replay_source: UUID | None = None


class Evaluation(schemas.Contract):
    id: UUID
    kb_id: UUID
    dataset_id: str
    dataset_hash: str
    split: str
    status: str
    versions: dict[str, str]
    runtime_config: dict
    summary: dict
    created_at: schemas.datetime
    completed_at: schemas.datetime | None


class EvalCase(schemas.Contract):
    eval_run_id: UUID
    case_id: str
    status: str
    query_run_id: UUID | None
    result: dict
    judge: dict
    human_review: dict
    judge_reserved_yuan: float
    judge_estimated_yuan: float | None
    judge_reserved_at: schemas.datetime | None


class HumanReview(schemas.Contract):
    verdict: Literal["correct_complete", "partial", "incorrect_or_unjustified_refusal", "unassessable"]
    reason: str = Field(min_length=1, max_length=1000)


class DatasetSource(schemas.Contract):
    source_id: str
    title: str
    download_url: str
    canonical_url: str
    acquired_date: str
    sha256: str
    license_notes: str
    redistribute_raw: bool
    filename: str


class DatasetSummary(schemas.Contract):
    dataset_id: str
    sha256: str
    sources: list[DatasetSource]
    case_count: int
    splits: list[str]
    split_policy: str


class EvaluationArtifact(schemas.Contract):
    evaluation: Evaluation
    cases: list[EvalCase]


class RunSummary(schemas.Contract):
    id: UUID
    kb_id: UUID
    question: str
    status: str
    created_at: schemas.datetime
    estimated_yuan: float | None
    error_code: str | None


class SystemStatus(schemas.Contract):
    model_gateway: dict
    circuits: list[dict]
    jobs: dict[str, int]
    query_count: int
    known_estimated_yuan: float
    unknown_reserved_yuan: float
    actual_charge: Literal["unavailable"] = "unavailable"


class VersionList(schemas.Contract):
    document_id: UUID
    active_version_id: UUID | None
    versions: list[schemas.Version]


def mount(app, principal):
    @app.get("/v1/evaluations/{eval_id}/compare", response_model=dict)
    def compare_evaluations(eval_id: UUID, baseline_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            baseline = service.authorized_eval(db, workspace, baseline_id)
            candidate = service.authorized_eval(db, workspace, eval_id)
            if baseline.status != "COMPLETED" or candidate.status != "COMPLETED":
                raise HTTPException(409, "comparison_not_complete")
            cases = [
                list(db.scalars(select(EvalCaseRow).where(EvalCaseRow.eval_run_id == i)))
                for i in (baseline_id, eval_id)
            ]
            try:
                return compare(baseline, candidate, *cases)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/v1/runs", response_model=list[RunSummary])
    def runs(
        workspace=Depends(principal),
        kb_id: UUID | None = None,
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with transaction() as db:
            query = select(QueryRunRow).where(QueryRunRow.workspace_id == workspace)
            if kb_id:
                query = query.where(QueryRunRow.kb_id == kb_id)
            return [
                RunSummary.model_validate(r)
                for r in db.scalars(
                    query.order_by(QueryRunRow.created_at.desc(), QueryRunRow.id).limit(limit).offset(offset)
                )
            ]

    @app.get("/v1/jobs", response_model=list[schemas.Job])
    def jobs(
        workspace=Depends(principal), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        with transaction() as db:
            query = (
                select(IngestionJobRow)
                .join(VersionRow)
                .join(KnowledgeBaseRow)
                .where(KnowledgeBaseRow.workspace_id == workspace)
            )
            return [
                schemas.Job.model_validate(r)
                for r in db.scalars(
                    query.order_by(IngestionJobRow.created_at.desc(), IngestionJobRow.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    @app.get("/v1/documents/{document_id}/versions", response_model=VersionList)
    def versions(
        document_id: UUID,
        workspace=Depends(principal),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with transaction() as db:
            doc = db.get(DocumentRow, document_id)
            if not doc:
                raise HTTPException(404, "document_not_found")
            lifecycle.authorized_kb(db, doc.kb_id, workspace)
            values = db.scalars(
                select(VersionRow)
                .where(VersionRow.document_id == document_id)
                .order_by(VersionRow.sequence.desc())
                .limit(limit)
                .offset(offset)
            )
            return VersionList(
                document_id=doc.id,
                active_version_id=doc.active_version_id,
                versions=[schemas.Version.model_validate(v) for v in values],
            )

    @app.post("/v1/document-versions/{version_id}/rebuild", response_model=Operation, status_code=202)
    def rebuild(
        version_id: UUID,
        workspace=Depends(principal),
        idempotency_key: str = Header(min_length=1, max_length=128),
    ):
        return lifecycle.rebuild(workspace, version_id, idempotency_key)

    @app.post("/v1/documents/{document_id}/rollback", response_model=Operation)
    def rollback(
        document_id: UUID,
        body: Rollback,
        workspace=Depends(principal),
        idempotency_key: str = Header(min_length=1, max_length=128),
    ):
        return lifecycle.rollback(
            workspace, document_id, body.target_version_id, body.expected_active_version_id, idempotency_key
        )

    @app.get("/v1/indexes/gc", response_model=list[GCEntry])
    def gc_plan(
        workspace=Depends(principal), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        try:
            return lifecycle.gc_plan(workspace)[offset : offset + limit]
        except Exception as exc:
            raise HTTPException(503, "index_unavailable") from exc

    @app.post("/v1/indexes/gc", response_model=Operation)
    def gc_delete(
        body: GCDelete,
        workspace=Depends(principal),
        idempotency_key: str = Header(min_length=1, max_length=128),
    ):
        return lifecycle.gc_delete(workspace, body.name, idempotency_key)

    @app.get("/v1/operations", response_model=list[Operation])
    def operations(
        workspace=Depends(principal), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        with transaction() as db:
            return [
                Operation.model_validate(r)
                for r in db.scalars(
                    select(OperationRow)
                    .where(OperationRow.workspace_id == workspace)
                    .order_by(OperationRow.created_at.desc(), OperationRow.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    @app.get("/v1/evaluation-datasets", response_model=list[DatasetSummary])
    def datasets(workspace=Depends(principal)):
        dataset, digest = load_dataset()
        return [
            dict(
                dataset_id=dataset["dataset_id"],
                sha256=digest,
                sources=dataset["sources"],
                case_count=len(dataset["cases"]),
                splits=["dev", "test", "all"],
                split_policy=dataset["split_policy"],
            )
        ]

    @app.post("/v1/evaluations", response_model=Evaluation, status_code=202)
    def create_evaluation(
        body: EvaluationCreate,
        workspace=Depends(principal),
        idempotency_key: str = Header(min_length=1, max_length=128),
    ):
        return service.create(
            workspace,
            body.kb_id,
            body.dataset_id,
            body.split,
            idempotency_key,
            body.profile,
            body.judge_profile,
            body.replay_source,
        )

    @app.get("/v1/evaluations", response_model=list[Evaluation])
    def evaluations(
        workspace=Depends(principal), limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)
    ):
        with transaction() as db:
            return [
                Evaluation.model_validate(r)
                for r in db.scalars(
                    select(EvalRunRow)
                    .where(EvalRunRow.workspace_id == workspace)
                    .order_by(EvalRunRow.created_at.desc(), EvalRunRow.id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    @app.get("/v1/evaluations/{eval_id}", response_model=Evaluation)
    def evaluation(eval_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            return Evaluation.model_validate(service.authorized_eval(db, workspace, eval_id))

    @app.post("/v1/evaluations/{eval_id}/cancel", response_model=Evaluation)
    def cancel_evaluation(eval_id: UUID, workspace=Depends(principal)):
        return service.cancel(workspace, eval_id)

    @app.get("/v1/evaluations/{eval_id}/cases", response_model=list[EvalCase])
    def cases(
        eval_id: UUID,
        workspace=Depends(principal),
        limit: int = Query(25, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        with transaction() as db:
            service.authorized_eval(db, workspace, eval_id)
            return [
                EvalCase.model_validate(r)
                for r in db.scalars(
                    select(EvalCaseRow)
                    .where(EvalCaseRow.eval_run_id == eval_id)
                    .order_by(EvalCaseRow.case_id)
                    .limit(limit)
                    .offset(offset)
                )
            ]

    @app.get("/v1/evaluations/{eval_id}/artifact", response_model=EvaluationArtifact)
    def artifact(eval_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            row = service.authorized_eval(db, workspace, eval_id)
            values = db.scalars(
                select(EvalCaseRow).where(EvalCaseRow.eval_run_id == eval_id).order_by(EvalCaseRow.case_id)
            )
            return dict(
                evaluation=Evaluation.model_validate(row).model_dump(mode="json"),
                cases=[EvalCase.model_validate(c).model_dump(mode="json") for c in values],
            )

    @app.get("/v1/evaluations/{eval_id}/report", response_class=PlainTextResponse)
    def report(eval_id: UUID, workspace=Depends(principal)):
        with transaction() as db:
            service.authorized_eval(db, workspace, eval_id)
        return markdown(eval_id, refresh(eval_id))

    @app.post("/v1/evaluations/{eval_id}/cases/{case_id}/review", response_model=EvalCase)
    def review(eval_id: UUID, case_id: str, body: HumanReview, workspace=Depends(principal)):
        with transaction() as db:
            service.authorized_eval(db, workspace, eval_id)
            row = db.get(EvalCaseRow, (eval_id, case_id))
            if not row:
                raise HTTPException(404, "evaluation_case_not_found")
            row.human_review = dict(
                body.model_dump(),
                source="owner_api_submission",
                recorded_at=db.scalar(select(func.clock_timestamp())).isoformat(),
            )
            value = EvalCase.model_validate(row)
        refresh(eval_id)
        return value

    @app.get("/v1/system", response_model=SystemStatus)
    def system(workspace=Depends(principal)):
        try:
            response = httpx.get(settings().model_url + "/health", timeout=2, trust_env=False)
            response.raise_for_status()
            model = response.json()
        except Exception:
            model = {"status": "unavailable"}
        with transaction() as db:
            jobs = dict(
                db.execute(
                    select(IngestionJobRow.status, func.count())
                    .join(VersionRow)
                    .join(KnowledgeBaseRow)
                    .where(KnowledgeBaseRow.workspace_id == workspace)
                    .group_by(IngestionJobRow.status)
                ).all()
            )
            count = db.scalar(
                select(func.count()).select_from(QueryRunRow).where(QueryRunRow.workspace_id == workspace)
            )
            known = float(
                db.scalar(
                    select(func.coalesce(func.sum(QueryRunRow.estimated_yuan), 0)).where(
                        QueryRunRow.workspace_id == workspace
                    )
                )
            )
            known += float(
                db.scalar(
                    select(func.coalesce(func.sum(EvalCaseRow.judge_estimated_yuan), 0))
                    .join(EvalRunRow)
                    .where(EvalRunRow.workspace_id == workspace)
                )
            )
            unknown = float(
                db.scalar(
                    select(func.coalesce(func.sum(QueryRunRow.reserved_yuan), 0)).where(
                        QueryRunRow.workspace_id == workspace, QueryRunRow.estimated_yuan.is_(None)
                    )
                )
            )
            unknown += float(
                db.scalar(
                    select(func.coalesce(func.sum(EvalCaseRow.judge_reserved_yuan), 0))
                    .join(EvalRunRow)
                    .where(EvalRunRow.workspace_id == workspace, EvalCaseRow.judge_estimated_yuan.is_(None))
                )
            )
            return SystemStatus(
                model_gateway=model,
                circuits=[dict(name=r.name, **r.value) for r in db.scalars(select(CircuitRow))],
                jobs=jobs,
                query_count=count,
                known_estimated_yuan=known,
                unknown_reserved_yuan=unknown,
            )
