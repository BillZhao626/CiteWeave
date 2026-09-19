"""Authorized, bounded inspection of published immutable structure."""

from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from citeweave.db import transaction
from citeweave.domain import ChildSpanRow, IndexRow, RetrievalChildRow, StructureArtifactRow, StructureNodeRow
from citeweave.lifecycle import authorized_version


class ArtifactView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version_id: UUID
    parser_revision: str
    profile_hash: str
    canonical_sha: str
    tree_hash: str
    membership_hash: str
    state: str
    tokenizers: dict


class NodeView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    artifact_id: UUID
    parent_node_id: UUID | None
    kind: str
    number: str | None
    title: str
    heading_ids: list[UUID]
    content_ids: list[UUID]
    reading_order: int
    page_start: int
    page_end: int
    confidence: str
    reasons: list[str]
    details: dict
    is_parent: bool = False


class ChildView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version_id: UUID
    artifact_id: UUID
    parent_node_id: UUID
    ordinal: int
    retrieval_text: str
    text_hash: str
    membership_hash: str
    tokenizers: dict
    token_counts: dict
    details: dict
    span_ids: list[UUID] = []


def artifact_for(db, workspace, version_id, artifact_id):
    version = authorized_version(db, workspace, version_id)
    if artifact_id is None:
        index = db.get(IndexRow, version.index_collection) if version.index_collection else None
        artifact_id = index.artifact_id if index and index.unit_kind == "structural_child" else None
    artifact = db.get(StructureArtifactRow, artifact_id) if artifact_id else None
    if not artifact or artifact.version_id != version_id or artifact.state != "PUBLISHED":
        raise HTTPException(409, "structure_not_published")
    return artifact


def mount(app, principal):
    @app.get("/v1/versions/{version_id}/structure", response_model=ArtifactView)
    def artifact(version_id: UUID, artifact_id: UUID | None = None, workspace=Depends(principal)):
        with transaction() as db:
            return ArtifactView.model_validate(artifact_for(db, workspace, version_id, artifact_id))

    @app.get("/v1/versions/{version_id}/structure/nodes", response_model=list[NodeView])
    def nodes(
        version_id: UUID,
        artifact_id: UUID | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        workspace=Depends(principal),
    ):
        with transaction() as db:
            artifact = artifact_for(db, workspace, version_id, artifact_id)
            parent_ids = set(
                db.scalars(
                    select(RetrievalChildRow.parent_node_id)
                    .where(RetrievalChildRow.artifact_id == artifact.id)
                    .distinct()
                )
            )
            return [
                NodeView.model_validate(n).model_copy(update={"is_parent": n.id in parent_ids})
                for n in db.scalars(
                    select(StructureNodeRow)
                    .where(StructureNodeRow.artifact_id == artifact.id)
                    .order_by(StructureNodeRow.details["artifact_order"].as_integer())
                    .offset(offset)
                    .limit(limit)
                )
            ]

    @app.get("/v1/versions/{version_id}/structure/children", response_model=list[ChildView])
    def children(
        version_id: UUID,
        artifact_id: UUID | None = None,
        parent_id: UUID | None = None,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        workspace=Depends(principal),
    ):
        with transaction() as db:
            artifact = artifact_for(db, workspace, version_id, artifact_id)
            query = select(RetrievalChildRow).where(RetrievalChildRow.artifact_id == artifact.id)
            if parent_id:
                query = query.where(RetrievalChildRow.parent_node_id == parent_id)
            rows = list(
                db.scalars(
                    query.order_by(RetrievalChildRow.details["artifact_order"].as_integer())
                    .offset(offset)
                    .limit(limit)
                )
            )
            members = list(
                db.scalars(
                    select(ChildSpanRow)
                    .where(ChildSpanRow.child_id.in_([r.id for r in rows]))
                    .order_by(ChildSpanRow.position)
                )
            )
            return [
                ChildView.model_validate(c).model_copy(
                    update={"span_ids": [m.evidence_id for m in members if m.child_id == c.id]}
                )
                for c in rows
            ]
