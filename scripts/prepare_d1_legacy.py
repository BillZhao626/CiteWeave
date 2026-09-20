"""Isolated D1 namespaces; reuse frozen canonical geometry, never reparse sources."""

import json
import os
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, insert, select, text
from sqlalchemy.engine import make_url

from citeweave.blobs import LocalBlobStore
from citeweave.db import engine, migrate, transaction
from citeweave.domain import ChunkRow, DocumentRow, IndexRow, KnowledgeBaseRow, VersionRow
from citeweave.embeddings import E5
from citeweave.evaluation.dataset import load_dataset
from citeweave.evidence import Block, digest
from citeweave.index import QdrantIndex
from citeweave.model_client import ModelGateway
from citeweave.pipeline import PROFILE, chunk_blocks
from citeweave.retrieval import BM25Encoder
from citeweave.settings import ROOT, settings

LEGACY_DB = "cw_d1_legacy_20260920"
STRUCTURAL_DB = "cw_d1_structural_v2_20260920"
ACCEPTED_DB = "cw_stage_c5_release"


def use_database(base, name):
    assert name in {LEGACY_DB, STRUCTURAL_DB}
    os.environ["CW_DATABASE_URL"] = base.set(drivername="postgresql", database=name).render_as_string(
        hide_password=False
    )
    os.environ["DEEPSEEK_API_KEY"] = ""
    os.environ["CW_BLOB_ROOT"] = str(ROOT / ".runtime/private/c2-test-blobs")
    if engine.cache_info().currsize:
        engine().dispose()
    settings.cache_clear()
    engine.cache_clear()


def main():
    output = Path(os.environ["CW_D1_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    base = make_url(settings().db_url())
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as db:
        for name in (LEGACY_DB, STRUCTURAL_DB):
            if not db.scalar(text("SELECT 1 FROM pg_database WHERE datname=:n"), {"n": name}):
                db.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    source = create_engine(base.set(database=ACCEPTED_DB))
    # Copy only the immutable corpus tables into a fresh evaluation database.
    # CREATE DATABASE TEMPLATE would require interrupting accepted product sessions.
    use_database(base, STRUCTURAL_DB)
    migrate()
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from citeweave.domain import (
        ChildSpanRow,
        IngestionJobRow,
        RetrievalChildRow,
        StructureArtifactRow,
        StructureNodeRow,
    )

    with source.connect() as reader, transaction() as writer:
        reader.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        if not writer.scalar(select(IndexRow.name).limit(1)):
            for cls in (
                KnowledgeBaseRow,
                DocumentRow,
                VersionRow,
                IngestionJobRow,
                ChunkRow,
                StructureArtifactRow,
                StructureNodeRow,
                RetrievalChildRow,
                ChildSpanRow,
                IndexRow,
            ):
                stream = (
                    reader.execution_options(stream_results=True).execute(select(cls.__table__)).mappings()
                )
                for batch in stream.partitions(100):
                    values = [
                        dict(r, state="DRAFT") if cls is StructureArtifactRow else dict(r) for r in batch
                    ]
                    writer.execute(pg_insert(cls).values(values))
                print(json.dumps(dict(stage="copy_frozen_table", table=cls.__tablename__)), flush=True)
            for artifact in writer.scalars(select(StructureArtifactRow)):
                artifact.state = "PUBLISHED"
    dataset, dataset_hash = load_dataset("citeweave-public-telecom-eval-v1")
    hashes = {s["sha256"] for s in dataset["sources"]}
    with source.connect() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        versions = [
            dict(r)
            for r in db.execute(
                select(VersionRow.__table__).where(
                    VersionRow.source_sha256.in_(hashes), VersionRow.status == "READY"
                )
            ).mappings()
        ]
        assert len(versions) == 7
        kb_ids = {r["kb_id"] for r in versions}
        docs = [
            dict(r)
            for r in db.execute(select(DocumentRow.__table__).where(DocumentRow.kb_id.in_(kb_ids))).mappings()
        ]
        kbs = [
            dict(r)
            for r in db.execute(
                select(KnowledgeBaseRow.__table__).where(KnowledgeBaseRow.id.in_(kb_ids))
            ).mappings()
        ]
    source.dispose()
    use_database(base, LEGACY_DB)
    migrate()
    with transaction() as db:
        for cls, rows in ((KnowledgeBaseRow, kbs), (DocumentRow, docs)):
            for row in rows:
                if db.get(cls, row["id"]) is None:
                    db.execute(insert(cls).values(**row))
    blob = LocalBlobStore(settings().blob_root)
    model, index = ModelGateway(), QdrantIndex()
    manifest = dict(
        dataset_hash=dataset_hash,
        database=LEGACY_DB,
        structural_database=STRUCTURAL_DB,
        profile="legacy-glyph-large-v1",
        max_chunks=100000,
        canonical_policy="accepted canonical bytes; no reparse",
        sources=[],
    )
    for v in sorted(versions, key=lambda v: v["source_sha256"]):
        with transaction() as db:
            prior = db.get(VersionRow, v["id"])
            if prior and prior.status == "READY":
                manifest["sources"].append(
                    dict(
                        source_sha256=v["source_sha256"],
                        version_id=str(v["id"]),
                        canonical_sha256=v["canonical_key"],
                        index=prior.index_collection,
                        count=prior.chunk_count,
                    )
                )
                continue
        raw = blob.get(v["blob_key"])
        assert digest(raw) == v["source_sha256"]
        canonical = blob.get(v["canonical_key"])
        assert digest(canonical) == v["canonical_key"]
        blocks = [Block.model_validate(b) for b in json.loads(canonical)]
        chunks = chunk_blocks(blocks, max_chunks=100000)
        encoder = BM25Encoder.fit([c["text"] for c in chunks])
        name = "cw_d1_glyph_" + v["id"].hex
        with transaction() as db:
            if db.get(VersionRow, v["id"]) is None:
                db.execute(
                    insert(VersionRow).values(
                        **dict(
                            v,
                            status="INDEXING",
                            index_collection=None,
                            profile=dict(
                                PROFILE,
                                parser_revision=v["profile"]["parser_revision"],
                                experiment_build="legacy-glyph-large-v1",
                            ),
                        )
                    )
                )
            if db.get(IndexRow, name) is None:
                db.add(
                    IndexRow(
                        name=name,
                        workspace_id=kbs[0]["workspace_id"],
                        version_id=v["id"],
                        state="BUILDING",
                        unit_kind="legacy_span",
                        embedding_identity=E5,
                    )
                )
        if not index.client.collection_exists(name):
            index.create(name)
        print(json.dumps(dict(stage="legacy_index", source=v["filename"], chunks=len(chunks))), flush=True)
        # Resuming an unfinished build upserts the same IDs in the isolated namespace.
        for start in range(0, len(chunks), 200):
            batch = chunks[start : start + 200]
            dense = []
            for offset in range(0, len(batch), 20):
                dense.extend(model.embed([c["text"] for c in batch[offset : offset + 20]]))
            index.write(name, batch, dense, encoder, start)
            if start % 1000 == 0:
                print(
                    json.dumps(dict(stage="embedding", index=name, completed=start + len(batch))), flush=True
                )
        index.verify(name, [c["id"] for c in chunks])
        with transaction() as db:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            for start in range(0, len(chunks), 100):
                db.execute(
                    pg_insert(ChunkRow)
                    .values(
                        [
                            dict(
                                id=UUID(c["id"]),
                                version_id=v["id"],
                                text=c["text"],
                                block=c["block"],
                                evidence=c["evidence"],
                            )
                            for c in chunks[start : start + 100]
                        ]
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                )
            row = db.get(VersionRow, v["id"])
            row.bm25, row.index_collection, row.chunk_count, row.status = (
                asdict(encoder),
                name,
                len(chunks),
                "READY",
            )
            db.get(IndexRow, name).state = "PUBLISHED"
        manifest["sources"].append(
            dict(
                source_sha256=v["source_sha256"],
                version_id=str(v["id"]),
                canonical_sha256=v["canonical_key"],
                index=name,
                count=len(chunks),
            )
        )
        (output / "legacy-build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "legacy-build.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(dict(status="READY", sources=len(manifest["sources"]))))


if __name__ == "__main__":
    main()
