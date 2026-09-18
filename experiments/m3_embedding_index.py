"""Fenced, resumable experimental Dense indexes; active version indexes never change."""

import argparse
import json
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from citeweave.blobs import LocalBlobStore
from citeweave.db import transaction
from citeweave.document_profiles import structural
from citeweave.domain import ChunkRow, IndexRow, OperationRow
from citeweave.embeddings import embedding_identity
from citeweave.index import QdrantIndex
from citeweave.lifecycle import authorized_version, governance_lock, operation
from citeweave.model_client import ModelGateway
from citeweave.retrieval import BM25Encoder
from citeweave.settings import ROOT, settings


def now():
    return datetime.now(timezone.utc)


def owned(db, identity, fence):
    row = db.get(OperationRow, identity)
    if (
        row.status != "RUNNING"
        or row.detail["fence"] != fence
        or datetime.fromisoformat(row.detail["lease_until"]) <= now()
    ):
        raise ValueError("embedding_index_fence_lost")
    return row


def renew(identity, fence):
    with transaction() as db:
        governance_lock(db)
        row = owned(db, identity, fence)
        row.detail = dict(row.detail, lease_until=(now() + timedelta(minutes=5)).isoformat())


def build(version_id, model_key, key):
    workspace, model = settings().workspace_id, embedding_identity(model_key)
    start = time.perf_counter()
    with transaction() as db:
        governance_lock(db)
        version = authorized_version(db, workspace, version_id)
        if version.status != "READY":
            raise ValueError("source_version_not_ready")
        if structural(version.profile):
            raise ValueError("structural_experiment_index_not_enabled")
        row, _ = operation(db, workspace, key, "embedding_index", str(version_id))
        if row.detail and row.detail["embedding"] != model:
            raise ValueError("embedding_index_idempotency_conflict")
        if row.status == "COMPLETED":
            return row.detail
        if row.status == "RUNNING" and datetime.fromisoformat(row.detail["lease_until"]) > now():
            raise ValueError("embedding_index_owned_by_live_attempt")
        fence = row.detail.get("fence", 0) + 1
        name = f"cw3x_{version_id.hex}_{row.id.hex}_a{fence}"
        row.status, row.detail = (
            "RUNNING",
            dict(
                embedding=model,
                collection=name,
                fence=fence,
                lease_until=(now() + timedelta(minutes=5)).isoformat(),
                source_sha256=version.source_sha256,
            ),
        )
        db.add(
            IndexRow(name=name, workspace_id=workspace, version_id=version_id, fence=fence, state="BUILDING")
        )
        identity = row.id
        chunks = list(db.scalars(select(ChunkRow).where(ChunkRow.version_id == version_id)))
        canonical = json.loads(LocalBlobStore(settings().blob_root).get(version.canonical_key))
        block_order = {b["block_id"]: i for i, b in enumerate(canonical)}
        chunks.sort(key=lambda c: (block_order[c.block["block_id"]], c.evidence["start_offset"]))
        encoder = BM25Encoder.fit([c.text for c in chunks])
        stats = asdict(encoder)
        stats["documents"] = []
        if stats != version.bm25:
            raise ValueError("original_bm25_order_mismatch")
        records = [dict(id=str(c.id), evidence=c.evidence) for c in chunks]
    index, gateway = QdrantIndex(), ModelGateway(embedding_key=model_key)
    embed_seconds, write_seconds = 0.0, 0.0
    try:
        index.create(name, dimension=model["dimension"])
        for at in range(0, len(chunks), 20):
            renew(identity, fence)
            clock = time.perf_counter()
            vectors = gateway.embed([c.text for c in chunks[at : at + 20]])
            embed_seconds += time.perf_counter() - clock
            clock = time.perf_counter()
            index.write(name, records[at : at + 20], vectors, encoder, at)
            write_seconds += time.perf_counter() - clock
        index.verify(name, [str(c.id) for c in chunks])
        collection = index.client.get_collection(name)
        if collection.config.params.vectors["dense"].size != model["dimension"]:
            raise ValueError("embedding_collection_dimension_mismatch")
        with transaction() as db:
            governance_lock(db)
            row = owned(db, identity, fence)
            target = db.get(IndexRow, name)
            if target.state != "BUILDING" or target.fence != fence:
                raise ValueError("embedding_index_publication_fenced")
            target.state = "EXPERIMENT_READY"
            row.status = "COMPLETED"
            row.detail = dict(
                row.detail,
                chunk_count=len(chunks),
                embed_seconds=embed_seconds,
                write_seconds=write_seconds,
                build_seconds=time.perf_counter() - start,
                completed_at=now().isoformat(),
                original_index=version.index_collection,
                operation_id=str(identity),
                verified_ids=True,
            )
            return row.detail
    except Exception as exc:
        with transaction() as db:
            governance_lock(db)
            row = db.get(OperationRow, identity)
            if row.detail.get("fence") == fence and row.status == "RUNNING":
                row.status = "FAILED"
                row.detail = dict(row.detail, error_type=type(exc).__name__)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--embedding", required=True, choices=["e5-small", "bge-m3"])
    parser.add_argument("--versions", required=True, nargs="+", type=UUID)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    if not args.key.replace("-", "").isalnum() or len(args.key) > 40:
        raise ValueError("invalid_build_key")
    results = []
    for version in args.versions:
        result = build(version, args.embedding, args.key + ":" + str(version))
        results.append(result)
        print(json.dumps(result), flush=True)
    path = ROOT / "docs/reports/m3-revisit" / (args.key + "-indexes.json")
    if path.exists():
        if json.loads(path.read_text()) != results:
            raise ValueError("index_report_exists")
    else:
        path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
