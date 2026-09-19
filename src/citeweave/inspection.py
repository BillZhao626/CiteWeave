"""Read-only, owner-scoped product inspection of already durable facts."""

from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import select

from citeweave import schemas
from citeweave.db import transaction
from citeweave.domain import (
    ChunkRow,
    EvalCaseRow,
    EvalOutboxRow,
    ProviderPhaseRow,
    RetrievalChildRow,
    StructureNodeRow,
)
from citeweave.evaluation.service import authorized_eval
from citeweave.structure_views import NodeView, artifact_for


class NodeContext(schemas.Contract):
    node: NodeView
    ancestors: list[NodeView]
    spans: list[schemas.Citation]
    total_spans: int


class PhaseView(schemas.Contract):
    id: UUID
    phase: str
    phase_attempt: int
    state: str
    outcome: str
    query_run_id: UUID | None
    dispatched_at: schemas.datetime | None
    reserved_yuan: float
    estimated_yuan: float | None
    result_hash: str | None
    error_code: str | None


class DispatchView(schemas.Contract):
    dispatch_generation: int
    state: str
    send_count: int
    task_id: str | None


class CaseRuntime(schemas.Contract):
    phases: list[PhaseView]
    dispatches: list[DispatchView]
    retry_state: str
    observed_at: schemas.datetime
    authority: str = "PostgreSQL"


class BrokerView(schemas.Contract):
    status: str
    version: str | None = None
    ping: bool = False
    authority: str = "PostgreSQL"
    role: str = "Redis transports Celery notifications; PostgreSQL owns task state."
    task_names: list[str] = Field(default_factory=lambda: ["citeweave.ingest", "citeweave.evaluate_case"])


def mount(app, principal):
    @app.get("/v1/versions/{version_id}/structure/nodes/{node_id}", response_model=NodeContext)
    def context(
        version_id: UUID,
        node_id: UUID,
        artifact_id: UUID | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(40, ge=1, le=100),
        workspace=Depends(principal),
    ):
        from citeweave.answering import citation_for

        with transaction() as db:
            artifact = artifact_for(db, workspace, version_id, artifact_id)
            node = db.get(StructureNodeRow, node_id)
            if not node or node.artifact_id != artifact.id:
                raise HTTPException(404, "structure_node_not_found")
            parent_ids = set(
                db.scalars(
                    select(RetrievalChildRow.parent_node_id)
                    .where(RetrievalChildRow.artifact_id == artifact.id)
                    .distinct()
                )
            )

            def view(value):
                return NodeView.model_validate(value).model_copy(update={"is_parent": value.id in parent_ids})

            ancestors, cursor = [], node
            while cursor.parent_node_id and len(ancestors) < 32:
                cursor = db.get(StructureNodeRow, cursor.parent_node_id)
                if not cursor or cursor.artifact_id != artifact.id:
                    raise HTTPException(409, "structure_parent_invalid")
                ancestors.insert(0, view(cursor))
            ids = list(dict.fromkeys([*node.heading_ids, *node.content_ids]))
            chosen = ids[offset : offset + limit]
            chunks = {
                str(c.id): c
                for c in db.scalars(
                    select(ChunkRow).where(ChunkRow.version_id == version_id, ChunkRow.id.in_(chosen))
                )
            }
            return NodeContext(
                node=view(node),
                ancestors=ancestors,
                total_spans=len(ids),
                spans=[citation_for(chunks[str(identity)], "Source") for identity in chosen],
            )

    @app.get("/v1/evaluations/{eval_id}/cases/{case_id}/runtime", response_model=CaseRuntime)
    def case_runtime(eval_id: UUID, case_id: str, workspace=Depends(principal)):
        from sqlalchemy import func

        with transaction() as db:
            run = authorized_eval(db, workspace, eval_id)
            case = db.get(EvalCaseRow, (eval_id, case_id))
            if not case:
                raise HTTPException(404, "evaluation_case_not_found")
            phases = list(
                db.scalars(
                    select(ProviderPhaseRow)
                    .where(ProviderPhaseRow.eval_run_id == eval_id, ProviderPhaseRow.case_id == case_id)
                    .order_by(ProviderPhaseRow.created_at)
                    .limit(4)
                )
            )
            now = db.scalar(select(func.clock_timestamp()))
            terminal = case.status in {"COMPLETED", "FAILED", "CANCELLED", "OUTCOME_UNKNOWN"}
            expired = any(
                deadline and deadline <= now
                for deadline in [run.total_deadline, case.absolute_deadline, case.active_deadline]
            )
            if terminal or run.cancel_requested_at or expired:
                retry = "not_eligible"
            elif any(p.state in {"UNKNOWN", "DISPATCHED"} for p in phases):
                retry = "no_automatic_provider_resend"
            elif case.status == "RETRY_WAIT":
                retry = "awaiting_authoritative_scheduler_checks"
            else:
                retry = "not_a_retry_wait"
            return CaseRuntime(
                phases=[PhaseView.model_validate(p) for p in phases],
                dispatches=[
                    DispatchView.model_validate(d)
                    for d in db.scalars(
                        select(EvalOutboxRow)
                        .where(EvalOutboxRow.eval_run_id == eval_id, EvalOutboxRow.case_id == case_id)
                        .order_by(EvalOutboxRow.dispatch_generation)
                        .limit(30)
                    )
                ],
                retry_state=retry,
                observed_at=now,
            )

    @app.get("/v1/runtime/broker", response_model=BrokerView)
    def broker(workspace=Depends(principal)):
        import redis

        from citeweave.settings import settings

        try:
            with redis.Redis.from_url(
                settings().broker_url, socket_connect_timeout=1, socket_timeout=1
            ) as client:
                ping = client.ping()
                info = client.info("server")
                return BrokerView(status="available", ping=ping, version=info.get("redis_version"))
        except Exception:
            return BrokerView(status="unavailable")
