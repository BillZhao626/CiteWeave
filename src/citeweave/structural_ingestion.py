"""Profile adapter for the existing fenced ingestion lifecycle, not a second job system."""

import tempfile
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import insert, select

from citeweave import ingestion_state as state
from citeweave.blobs import LocalBlobStore
from citeweave.db import transaction
from citeweave.document_profiles import canonical_block_bytes, content_hash, validate_profile
from citeweave.domain import (
    ChildSpanRow,
    ChunkRow,
    IndexRow,
    RetrievalChildRow,
    StructureArtifactRow,
    StructureNodeRow,
)
from citeweave.embeddings import E5
from citeweave.evidence import Scope
from citeweave.index import QdrantIndex
from citeweave.model_client import ModelGateway
from citeweave.parsing import parse_structural_pdf
from citeweave.retrieval import BM25Encoder
from citeweave.settings import settings
from citeweave.structure import build_children, parse_structure, validate_draft
from citeweave.tokenization import CONTRACT, GatewayTokenizer


def values(row):
    return {
        c.name: str(v) if isinstance(v := getattr(row, c.name), UUID) else v for c in row.__table__.columns
    }


def load_published(db, artifact_id):
    artifact = db.get(StructureArtifactRow, artifact_id)
    if not artifact or artifact.state != "PUBLISHED":
        raise ValueError("structure_not_published")
    nodes = [
        values(n)
        for n in db.scalars(select(StructureNodeRow).where(StructureNodeRow.artifact_id == artifact.id))
    ]
    # Persisted ordering is explicit, including deterministic partition placement.
    nodes.sort(key=lambda n: n["details"].get("artifact_order", 0))
    children = [
        values(c)
        for c in db.scalars(select(RetrievalChildRow).where(RetrievalChildRow.artifact_id == artifact.id))
    ]
    children.sort(key=lambda c: c["details"]["artifact_order"])
    memberships = defaultdict_memberships(db, artifact.id)
    for child in children:
        child["span_ids"] = memberships[child["id"]]
    chunks = [
        dict(id=str(c.id), text=c.text, block=c.block, evidence=c.evidence)
        for c in db.scalars(select(ChunkRow).where(ChunkRow.version_id == artifact.version_id))
    ]
    draft = dict(artifact=values(artifact), nodes=nodes, children=children, chunks=chunks)
    validate_draft(draft)
    return draft


def defaultdict_memberships(db, artifact_id):
    from collections import defaultdict

    result = defaultdict(list)
    for member in db.scalars(
        select(ChildSpanRow)
        .join(RetrievalChildRow, ChildSpanRow.child_id == RetrievalChildRow.id)
        .where(RetrievalChildRow.artifact_id == artifact_id)
        .order_by(ChildSpanRow.position)
    ):
        result[str(member.child_id)].append(str(member.evidence_id))
    return result


def register_build(lease, collection, draft, stats):
    from citeweave.lifecycle import governance_lock

    artifact = draft["artifact"]
    with transaction() as db:
        governance_lock(db)
        state.owned(db, lease["job_id"], lease["fence"])
        existing = db.get(StructureArtifactRow, UUID(artifact["id"]))
        if existing:
            expected = {**artifact, "state": existing.state}
            if values(existing) != expected:
                raise ValueError("artifact_identity_collision")
        else:
            db.add(StructureArtifactRow(**artifact))
            db.flush()
        db.add(
            IndexRow(
                name=collection,
                workspace_id=lease["workspace_id"],
                version_id=lease["version_id"],
                job_id=lease["job_id"],
                fence=lease["fence"],
                state="BUILDING",
                unit_kind="structural_child",
                artifact_id=UUID(artifact["id"]),
                index_profile_hash=artifact["profile_hash"],
                embedding_identity=E5,
                bm25=stats,
                bm25_hash=content_hash(stats),
            )
        )


def publish_structure(db, version, index, job, draft, chunks, stats, canonical_key, page_count):
    validate_draft(draft)
    artifact = draft["artifact"]
    if (
        artifact["version_id"] != str(version.id)
        or artifact["profile"] != version.profile
        or artifact["canonical_sha"] != canonical_key
        or chunks != draft["chunks"]
        or index.unit_kind != "structural_child"
        or str(index.artifact_id) != artifact["id"]
        or index.index_profile_hash != artifact["profile_hash"]
        or index.embedding_identity != E5
        or index.bm25 != stats
        or index.bm25_hash != content_hash(stats)
        or not 0 < page_count <= version.profile["limits"]["pages"]
    ):
        raise ValueError("structural_publication_binding_mismatch")
    expected_scope = dict(
        workspace_id=str(index.workspace_id), kb_id=str(version.kb_id), revision_id=str(version.id)
    )
    if any(
        c["block"]["scope"] != expected_scope or c["block"]["source_sha256"] != version.source_sha256
        for c in chunks
    ):
        raise ValueError("structural_publication_source_mismatch")
    stored = db.get(StructureArtifactRow, UUID(artifact["id"]))
    if not stored or values(stored) != {**artifact, "state": stored.state}:
        raise ValueError("artifact_identity_collision")
    if job.kind == "rebuild":
        frozen = load_published(db, stored.id)
        if frozen["nodes"] != draft["nodes"] or frozen["children"] != draft["children"]:
            raise ValueError("rebuild_structure_mismatch")
        return
    if stored.state != "DRAFT":
        raise ValueError("published_structure_immutable")
    for start in range(0, len(chunks), 100):
        db.execute(
            insert(ChunkRow),
            [{**c, "id": UUID(c["id"]), "version_id": version.id} for c in chunks[start : start + 100]],
        )
    for start in range(0, len(draft["nodes"]), 100):
        db.execute(insert(StructureNodeRow), draft["nodes"][start : start + 100])
    for start in range(0, len(draft["children"]), 100):
        batch = draft["children"][start : start + 100]
        db.execute(
            insert(RetrievalChildRow), [{k: v for k, v in c.items() if k != "span_ids"} for c in batch]
        )
        db.execute(
            insert(ChildSpanRow),
            [
                dict(child_id=c["id"], evidence_id=eid, version_id=version.id, position=i)
                for c in batch
                for i, eid in enumerate(c["span_ids"])
            ],
        )
    stored.state = "PUBLISHED"


def run_structural_ingestion(lease, lost):
    from citeweave.ingestion import fault_gate
    from citeweave.structure import seal

    profile = validate_profile(lease["profile"])
    job_id, fence = lease["job_id"], lease["fence"]
    blobs = LocalBlobStore(settings().blob_root)
    if lease["kind"] == "rebuild":
        with transaction() as db:
            index = db.get(IndexRow, lease["index_collection"])
            if not index or index.unit_kind != "structural_child":
                raise ValueError("rebuild_index_unit_mismatch")
            draft = load_published(db, index.artifact_id)
        canonical_key = lease["canonical_key"]
        blobs.get(canonical_key)  # Integrity checked by the content-addressed store; no reparse.
        if canonical_key != draft["artifact"]["canonical_sha"]:
            raise ValueError("rebuild_canonical_mismatch")
        # The PDF and current parser are deliberately not used for a rebuild.
        page_count = lease["page_count"]
        state.stage(job_id, fence, "CHUNKING")
    else:
        with tempfile.TemporaryDirectory(prefix="cw-structure-") as temporary:
            path = Path(temporary) / "source.pdf"
            path.write_bytes(blobs.get(lease["blob_key"]))
            blocks, hints, page_count = parse_structural_pdf(
                path,
                Scope(
                    workspace_id=lease["workspace_id"], kb_id=lease["kb_id"], revision_id=lease["version_id"]
                ),
                profile,
            )
        state.stage(job_id, fence, "CHUNKING")
        canonical_key = blobs.put_stream(canonical_block_bytes(blocks))
        draft = parse_structure(blocks, hints, profile)
        del blocks, hints
        draft = build_children(draft, GatewayTokenizer())
        # Stable artifact order makes PG reconstruction independent of physical row order.
        for i, n in enumerate(draft["nodes"]):
            n["details"]["artifact_order"] = i
        for i, c in enumerate(draft["children"]):
            c["details"]["artifact_order"] = i
        seal(draft)
    validate_draft(draft)
    children = draft["children"]
    encoder = BM25Encoder.fit([c["retrieval_text"] for c in children])
    stats = asdict(encoder)
    stats["documents"] = []
    state.stage(job_id, fence, "EMBEDDING")
    fault_gate(job_id, "EMBEDDING")
    # Batch vectors, then write while INDEXING; all physical output remains private until publish.
    model = ModelGateway()
    state.stage(job_id, fence, "INDEXING")
    collection = f"cw3_v{lease['version_id'].hex}_j{job_id.hex}_f{fence}"
    register_build(lease, collection, draft, stats)
    index = QdrantIndex()
    index.create(collection)
    binding = dict(
        unit_kind="structural_child",
        artifact_id=draft["artifact"]["id"],
        index_profile_hash=draft["artifact"]["profile_hash"],
        embedding_identity=E5,
        bm25_hash=content_hash(stats),
    )
    scope = {k: str(lease[k]) for k in ("workspace_id", "kb_id", "version_id")}
    for start in range(0, len(children), 16):
        if lost.is_set():
            raise state.StaleAttempt()
        batch = children[start : start + 16]
        dense = model.embed([c["retrieval_text"] for c in batch], contract=CONTRACT)
        index.write_children(collection, batch, dense, encoder, start, binding, scope)
        if start == 0:
            fault_gate(job_id, "INDEXING")
    index.verify_children(collection, children, binding, scope)
    state.publish(
        job_id, fence, draft["chunks"], collection, stats, canonical_key, page_count, structure=draft
    )
