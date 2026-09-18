"""Bounded PostgreSQL reads for captured structural builds and original atoms."""

import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import load_only

from citeweave.db import transaction
from citeweave.document_profiles import content_hash, structural, validate_profile
from citeweave.domain import (
    ChildSpanRow,
    ChunkRow,
    DocumentRow,
    IndexRow,
    RetrievalChildRow,
    StructureArtifactRow,
    StructureNodeRow,
    VersionRow,
)
from citeweave.embeddings import E5
from citeweave.evidence import Block, EvidenceSpan, resolve_span
from citeweave.query_evidence import StructuralBinding, StructuralSnapshot
from citeweave.tokenization import TOKENIZERS


def capture(db, workspace, body, versions, query_tokens):
    requested = [str(v) for v in (body.document_ids or [])]
    docs = list(db.scalars(select(DocumentRow).where(DocumentRow.kb_id == body.kb_id)))
    by_id = {str(d.id): d for d in docs}
    if requested and any(d not in by_id for d in requested):
        raise HTTPException(404, "document_scope_not_found")
    if requested:
        docs = [by_id[d] for d in requested]
    else:
        docs = sorted((d for d in docs if d.active_version_id in versions), key=lambda d: str(d.id))
    bindings = []
    for doc in docs:
        if doc.active_version_id not in versions:
            raise HTTPException(409, "structure_not_ready")
        v = db.get(VersionRow, doc.active_version_id)
        i = db.get(IndexRow, v.index_collection) if v.index_collection else None
        a = db.get(StructureArtifactRow, i.artifact_id) if i and i.artifact_id else None
        try:
            if (
                not i
                or not a
                or i.state != "PUBLISHED"
                or a.state != "PUBLISHED"
                or i.unit_kind != "structural_child"
                or i.version_id != v.id
                or a.version_id != v.id
                or i.workspace_id != workspace
                or not structural(v.profile)
                or a.profile != v.profile
                or a.profile_hash != content_hash(a.profile)
                or i.index_profile_hash != a.profile_hash
                or i.embedding_identity != E5
                or a.tokenizers != TOKENIZERS
                or not i.bm25
                or i.bm25_hash != content_hash(i.bm25)
            ):
                raise ValueError("binding_mismatch")
            validate_profile(a.profile)
        except ValueError:
            raise HTTPException(409, "structure_not_ready") from None
        bindings.append(
            StructuralBinding(
                document_id=str(doc.id),
                version_id=str(v.id),
                filename=v.filename,
                source_sha256=v.source_sha256,
                artifact_id=str(a.id),
                canonical_sha=a.canonical_sha,
                tree_hash=a.tree_hash,
                membership_hash=a.membership_hash,
                index_name=i.name,
                index_profile_hash=i.index_profile_hash,
                bm25_hash=i.bm25_hash,
                embedding_identity=i.embedding_identity,
                tokenizers=a.tokenizers,
            )
        )
    mode = body.evidence_mode
    if mode == "auto":
        mode = (
            "compare"
            if re.search(
                r"\b(compare|comparison|versus|vs\.?|difference|differences)\b|对比|比较|区别",
                body.question,
                re.I,
            )
            else "single"
        )
    return StructuralSnapshot(
        workspace_id=str(workspace),
        kb_id=str(body.kb_id),
        evidence_mode=mode,
        requested_documents=requested,
        bindings=bindings,
        query_tokens=query_tokens,
    )


class StructuralRepository:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.bindings = {b.version_id: b for b in snapshot.bindings}

    def builds(self):
        result = {}
        with transaction() as db:
            for b in self.bindings.values():
                index = db.get(IndexRow, b.index_name)
                artifact = db.get(StructureArtifactRow, UUID(b.artifact_id))
                version = db.get(VersionRow, UUID(b.version_id))
                if (
                    not index
                    or not artifact
                    or not version
                    or index.state not in {"PUBLISHED", "SUPERSEDED"}
                    or artifact.state != "PUBLISHED"
                    or str(index.artifact_id) != b.artifact_id
                    or str(index.version_id) != b.version_id
                    or index.unit_kind != b.unit_kind
                    or str(index.workspace_id) != self.snapshot.workspace_id
                    or index.index_profile_hash != b.index_profile_hash
                    or index.embedding_identity != b.embedding_identity
                    or index.bm25_hash != b.bm25_hash
                    or content_hash(index.bm25) != b.bm25_hash
                    or artifact.tree_hash != b.tree_hash
                    or artifact.membership_hash != b.membership_hash
                    or artifact.canonical_sha != b.canonical_sha
                    or version.source_sha256 != b.source_sha256
                ):
                    raise ValueError("structural_snapshot_mismatch")
                result[b.version_id] = index.bm25
        return result

    def children(self, identities):
        if len(identities) > 800:
            raise ValueError("candidate_read_limit")
        with transaction() as db:
            rows = list(
                db.scalars(
                    select(RetrievalChildRow).where(RetrievalChildRow.id.in_([UUID(i) for i in identities]))
                )
            )
            members = (
                db.execute(
                    select(ChildSpanRow)
                    .where(ChildSpanRow.child_id.in_([c.id for c in rows]))
                    .order_by(ChildSpanRow.child_id, ChildSpanRow.position)
                )
                .scalars()
                .all()
            )
            groups = {str(c.id): [] for c in rows}
            for m in members:
                groups[str(m.child_id)].append(m)
            nodes, pending = {}, {c.parent_node_id for c in rows}
            for _ in range(24):
                if not pending:
                    break
                fetched = list(
                    db.scalars(
                        select(StructureNodeRow)
                        .options(
                            load_only(
                                StructureNodeRow.id,
                                StructureNodeRow.artifact_id,
                                StructureNodeRow.parent_node_id,
                                StructureNodeRow.kind,
                                StructureNodeRow.number,
                                StructureNodeRow.title,
                                StructureNodeRow.heading_ids,
                                StructureNodeRow.content_ids,
                                StructureNodeRow.confidence,
                            )
                        )
                        .where(StructureNodeRow.id.in_(pending))
                    )
                )
                nodes.update({n.id: n for n in fetched})
                pending = {
                    n.parent_node_id for n in fetched if n.parent_node_id and n.parent_node_id not in nodes
                }
            result = {}
            for c in rows:
                b = self.bindings.get(str(c.version_id))
                ms = groups[str(c.id)]
                ids = [str(m.evidence_id) for m in ms]
                if (
                    not b
                    or str(c.artifact_id) != b.artifact_id
                    or c.tokenizers != TOKENIZERS
                    or not ids
                    or c.membership_hash != content_hash(ids)
                    or any(m.version_id != c.version_id or m.position != n for n, m in enumerate(ms))
                ):
                    raise ValueError("child_membership_mismatch")
                parent = nodes.get(c.parent_node_id)
                if (
                    not parent
                    or parent.artifact_id != c.artifact_id
                    or not set(ids) <= set(parent.content_ids)
                ):
                    raise ValueError("child_parent_mismatch")
                path, node = [], parent
                for _ in range(24):
                    if node.artifact_id != c.artifact_id:
                        raise ValueError("section_artifact_mismatch")
                    path.append(
                        {"id": str(node.id), "number": node.number, "title": node.title, "kind": node.kind}
                    )
                    if node.parent_node_id is None:
                        break
                    node = nodes.get(node.parent_node_id)
                    if not node:
                        raise ValueError("section_parent_missing")
                else:
                    raise ValueError("section_depth_limit")
                result[str(c.id)] = dict(
                    row=c, span_ids=ids, parent=parent, binding=b, section_path=list(reversed(path))
                )
            if set(result) != set(identities):
                raise ValueError("child_scope_mismatch")
        return result

    def atoms(self, identities):
        if len(identities) > 2000:
            raise ValueError("evidence_read_limit")
        with transaction() as db:
            rows = list(db.scalars(select(ChunkRow).where(ChunkRow.id.in_([UUID(i) for i in identities]))))
        result = {}
        for row in rows:
            b = self.bindings.get(str(row.version_id))
            span, block = EvidenceSpan.model_validate(row.evidence), Block.model_validate(row.block)
            if (
                not b
                or span.id != row.id
                or str(span.scope.revision_id) != b.version_id
                or str(span.scope.workspace_id) != self.snapshot.workspace_id
                or str(span.scope.kb_id) != self.snapshot.kb_id
                or span.source_sha256 != b.source_sha256
                or row.text != span.quote
            ):
                raise ValueError("evidence_scope_mismatch")
            resolve_span(span, block, block.scope)
            result[str(row.id)] = row
        if set(result) != set(identities):
            raise ValueError("evidence_membership_missing")
        return result

    def neighbors(self, seeds):
        identities = []
        with transaction() as db:
            for seed in seeds:
                c = seed["row"]
                identities.extend(
                    str(i)
                    for i in db.scalars(
                        select(RetrievalChildRow.id)
                        .where(
                            RetrievalChildRow.parent_node_id == c.parent_node_id,
                            RetrievalChildRow.artifact_id == c.artifact_id,
                            RetrievalChildRow.version_id == c.version_id,
                            RetrievalChildRow.ordinal.in_([c.ordinal - 1, c.ordinal + 1]),
                        )
                        .order_by(RetrievalChildRow.ordinal)
                    )
                )
        return self.children(list(dict.fromkeys(identities))) if identities else {}
