"""Authenticated observations of local services and owner-scoped durable indexes.

Observations never dispatch ingestion, model inference or provider requests.
PostgreSQL remains the authority for usable document versions.
"""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

import httpx
from fastapi import Depends
from pydantic import Field
from sqlalchemy import select, text

from citeweave.conversation_models import ConversationRow, ConversationRunRow
from citeweave.db import transaction
from citeweave.domain import DocumentRow, IngestionJobRow, KnowledgeBaseRow, VersionRow
from citeweave.schemas import Contract
from citeweave.settings import settings


class ServiceObservation(Contract):
    component: Literal["FastAPI", "PostgreSQL", "Redis", "Celery", "Qdrant", "Model gateway", "LLM provider"]
    status: Literal["available", "unavailable", "not_checked"]
    detail: str
    version: str | None = None


class CollectionObservation(Contract):
    collection: str
    document_id: UUID
    document_version_id: UUID
    filename: str
    version_sequence: int
    durable_status: str
    current_version: bool
    index_status: str | None = None
    points_count: int | None = None
    indexed_vectors_count: int | None = None
    observed: bool = False


class LatestJobObservation(Contract):
    id: UUID
    document_version_id: UUID
    status: str
    attempt: int
    created_at: datetime
    finished_at: datetime | None


class LatestRunObservation(Contract):
    id: UUID
    conversation_id: UUID
    turn_id: UUID
    status: str
    created_at: datetime
    completed_at: datetime | None


class OperationsObservation(Contract):
    observed_at: datetime
    authority: Literal["PostgreSQL"] = "PostgreSQL"
    services: list[ServiceObservation]
    workers: list[str] = Field(default_factory=list)
    collections: list[CollectionObservation] = Field(default_factory=list)
    latest_job: LatestJobObservation | None = None
    latest_run: LatestRunObservation | None = None


def observe_model(config):
    try:
        response = httpx.get(config.model_url + "/health", timeout=2, trust_env=False)
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("invalid_gateway_health")
        ready = value.get("status") == "ready"
        detail = "Embedding and reranker gateway reports READY" if ready else "Gateway did not report READY"
        return ServiceObservation(
            component="Model gateway", status="available" if ready else "unavailable", detail=detail
        )
    except (httpx.HTTPError, ValueError, TypeError):
        return ServiceObservation(
            component="Model gateway", status="unavailable", detail="Gateway health request failed"
        )


def observe_broker(config):
    import redis

    try:
        with redis.Redis.from_url(config.broker_url, socket_connect_timeout=1, socket_timeout=1) as client:
            if not client.ping():
                raise redis.RedisError("ping_failed")
            value = client.info("server")
        return ServiceObservation(
            component="Redis",
            status="available",
            detail="Broker PING succeeded",
            version=value.get("redis_version"),
        )
    except (redis.RedisError, OSError, ValueError):
        return ServiceObservation(component="Redis", status="unavailable", detail="Broker PING failed")


def observe_workers():
    from celery.exceptions import CeleryError
    from kombu.exceptions import KombuError

    from citeweave.celery_app import app

    try:
        replies = app.control.inspect(timeout=1).ping() or {}
        if not isinstance(replies, dict):
            raise ValueError("invalid_worker_ping")
        workers = sorted(
            name
            for name, value in replies.items()
            if isinstance(name, str) and isinstance(value, dict) and value.get("ok") == "pong"
        )
        return ServiceObservation(
            component="Celery",
            status="available" if workers else "unavailable",
            detail=f"{len(workers)} worker(s) answered PING",
        ), workers
    except (CeleryError, KombuError, OSError, ValueError, TimeoutError):
        return ServiceObservation(component="Celery", status="unavailable", detail="No worker PING reply"), []


def observe_collections(config, collections):
    try:
        with httpx.Client(base_url=config.qdrant_url, timeout=2, trust_env=False) as client:
            response = client.get("/collections")
            response.raise_for_status()
            available = {item["name"] for item in response.json()["result"]["collections"]}
            for item in collections:
                if item.collection not in available:
                    continue
                response = client.get("/collections/" + item.collection)
                response.raise_for_status()
                value = response.json()["result"]
                item.index_status = value.get("status")
                item.points_count = value.get("points_count")
                item.indexed_vectors_count = value.get("indexed_vectors_count")
                item.observed = True
        return ServiceObservation(
            component="Qdrant",
            status="available",
            detail=f"{sum(item.observed for item in collections)} durable collection(s) observed",
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return ServiceObservation(
            component="Qdrant", status="unavailable", detail="Collection inspection failed"
        )


def snapshot(workspace):
    config = settings()
    with transaction() as db:
        db.execute(text("SET LOCAL statement_timeout = 2000"))
        db.execute(text("SELECT 1"))
        versions = db.execute(
            select(VersionRow, DocumentRow.active_version_id)
            .join(DocumentRow, DocumentRow.id == VersionRow.document_id)
            .join(KnowledgeBaseRow, KnowledgeBaseRow.id == VersionRow.kb_id)
            .where(
                KnowledgeBaseRow.workspace_id == workspace,
                VersionRow.status == "READY",
                VersionRow.index_collection.is_not(None),
            )
            .order_by(VersionRow.created_at.desc(), VersionRow.id)
            .limit(30)
        ).all()
        collections = [
            CollectionObservation(
                collection=v.index_collection,
                document_id=v.document_id,
                document_version_id=v.id,
                filename=v.filename,
                version_sequence=v.sequence,
                durable_status=v.status,
                current_version=current == v.id,
            )
            for v, current in versions
        ]
        job = db.scalar(
            select(IngestionJobRow)
            .join(VersionRow, VersionRow.id == IngestionJobRow.document_version_id)
            .join(KnowledgeBaseRow, KnowledgeBaseRow.id == VersionRow.kb_id)
            .where(KnowledgeBaseRow.workspace_id == workspace)
            .order_by(IngestionJobRow.created_at.desc(), IngestionJobRow.id)
            .limit(1)
        )
        run = db.scalar(
            select(ConversationRunRow)
            .join(ConversationRow, ConversationRow.id == ConversationRunRow.conversation_id)
            .where(ConversationRow.workspace_id == workspace)
            .order_by(ConversationRunRow.created_at.desc(), ConversationRunRow.id)
            .limit(1)
        )
        latest_job = LatestJobObservation.model_validate(job) if job else None
        latest_run = LatestRunObservation.model_validate(run) if run else None
    broker = observe_broker(config)
    if broker.status == "available":
        worker, workers = observe_workers()
    else:
        worker, workers = (
            ServiceObservation(
                component="Celery", status="not_checked", detail="Broker unavailable; worker PING skipped"
            ),
            [],
        )
    return OperationsObservation(
        observed_at=datetime.now(timezone.utc),
        services=[
            ServiceObservation(
                component="FastAPI", status="available", detail="Authenticated API request succeeded"
            ),
            ServiceObservation(
                component="PostgreSQL", status="available", detail="Owner-scoped durable read succeeded"
            ),
            broker,
            worker,
            observe_collections(config, collections),
            observe_model(config),
            ServiceObservation(
                component="LLM provider",
                status="not_checked",
                detail="Configured; no provider health call"
                if config.deepseek_api_key.get_secret_value()
                else "Provider key not configured",
            ),
        ],
        workers=workers,
        collections=collections,
        latest_job=latest_job,
        latest_run=latest_run,
    )


def mount(app, principal):
    @app.get("/v1/runtime/operations", response_model=OperationsObservation)
    def operations(workspace=Depends(principal)):
        return snapshot(workspace)
