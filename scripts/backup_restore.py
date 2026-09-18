"""Project-only consistent backup and isolated restoration of PG + content-addressed blobs.

No production database is overwritten. The rehearsal owns one UUID-named database,
one temporary Qdrant container and one directory under .runtime/backups.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select, text

from citeweave.blobs import LocalBlobStore
from citeweave.db import transaction
from citeweave.domain import CitationRow, EvalRunRow, IngestionJobRow, QueryRunRow, VersionRow
from citeweave.settings import ROOT, settings

COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".env",
    "-f",
    "deploy/compose.m0.yml",
    "-f",
    "deploy/compose.m1.yml",
]


def command(args, **kwargs):
    result = subprocess.run(args, cwd=ROOT, timeout=90, **kwargs)
    if result.returncode:
        raise RuntimeError("recovery_command_failed:" + Path(args[0]).name)
    return result


def verify_blob_tree(root):
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if not re.fullmatch("[a-f0-9]{64}", path.name):
            raise ValueError("unexpected_blob_filename")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != path.name:
            raise ValueError("backup_blob_integrity_mismatch")
        files.append(dict(path=path.relative_to(root).as_posix(), sha256=digest, bytes=path.stat().st_size))
    return files


def restore_helper(directory):
    """Executed with explicitly isolated DB/blob/Qdrant configuration; cannot target production."""
    from sqlalchemy.engine import make_url

    from citeweave import answering, lifecycle
    from citeweave.domain import KnowledgeBaseRow
    from citeweave.evidence import resolve_span
    from citeweave.hybrid import HybridRetriever
    from citeweave.index import QdrantIndex
    from citeweave.ingestion import run_ingestion
    from citeweave.parsing import parse_simple_pdf

    database = make_url(settings().db_url()).database
    if not re.fullmatch(r"cw_restore_[a-f0-9]{32}", database or ""):
        raise ValueError("restore_requires_isolated_database")
    if (
        settings().qdrant_url != "http://127.0.0.1:16334"
        or settings().blob_root.resolve() != (directory / "blobs").resolve()
    ):
        raise ValueError("restore_requires_isolated_resources")
    index = QdrantIndex()
    assert not index.client.get_collections().collections, "restore_qdrant_must_start_empty"
    verified_blobs = verify_blob_tree(settings().blob_root)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert verified_blobs == manifest["blobs"]
    with transaction() as db:
        ready = list(
            db.scalars(select(VersionRow).where(VersionRow.status == "READY").order_by(VersionRow.id))
        )
        expected_runs = db.scalar(select(func.count()).select_from(QueryRunRow))
        expected_citations = db.scalar(select(func.count()).select_from(CitationRow))
        workspaces = {kb.id: kb.workspace_id for kb in db.scalars(select(KnowledgeBaseRow))}
    assert expected_runs == manifest["query_runs"] and expected_citations == manifest["citations"]
    rebuilt = []
    for version in ready:
        original = version.index_collection
        op = lifecycle.rebuild(workspaces[version.kb_id], version.id, "restore:" + str(version.id))
        run_ingestion(op.detail["job_id"])
        with transaction() as db:
            restored = db.get(VersionRow, version.id)
            job = db.get(IngestionJobRow, UUID(op.detail["job_id"]))
            assert job.status == "READY", job.error_code
            assert restored.index_collection != original and restored.canonical_key == version.canonical_key
        rebuilt.append(
            dict(
                version_id=str(version.id), collection=restored.index_collection, chunks=restored.chunk_count
            )
        )
        print("RESTORED INDEX", len(rebuilt), "/", len(ready), str(version.id), flush=True)
    blobs, parsed, grounded = LocalBlobStore(settings().blob_root), {}, 0
    with transaction() as db:
        references = list(
            db.execute(
                select(CitationRow.run_id, CitationRow.evidence_id, QueryRunRow.workspace_id).join(
                    QueryRunRow
                )
            ).all()
        )
    for run_id, evidence_id, workspace in references:
        citation = answering.get_citation(workspace, run_id, evidence_id)
        span = citation.span
        blobs.get(span.source_sha256)
        if span.scope.revision_id not in parsed:
            parsed[span.scope.revision_id] = {
                b.block_id: b for b in parse_simple_pdf(blobs.path(span.source_sha256), span.scope)
            }
        resolve_span(span, parsed[span.scope.revision_id][span.block_id], span.scope)
        grounded += 1
    assert grounded == expected_citations and grounded > 0
    with transaction() as db:
        example = db.get(QueryRunRow, references[0][0])
    chunks, trace = HybridRetriever().retrieve(example.question, example.versions)
    assert chunks and trace
    result = dict(
        status="PASS",
        database=database,
        query_runs=expected_runs,
        citations_revalidated=grounded,
        blobs_verified=len(verified_blobs),
        rebuilt_versions=len(rebuilt),
        indexes=rebuilt,
        fresh_qdrant_before=0,
        fresh_qdrant_after=len(index.client.get_collections().collections),
        local_retrieval_evidence_count=len(chunks),
        provider_calls=0,
    )
    (directory / "restore-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("RESTORE PASS", len(rebuilt), "versions;", grounded, "citations", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore-helper", type=Path)
    parser.add_argument("--milestone", choices=["m2", "m3"], default="m3")
    parser.add_argument("--report-prefix")
    args = parser.parse_args()
    root = (ROOT / ".runtime/backups").resolve()
    if args.restore_helper:
        directory = args.restore_helper.resolve()
        if not directory.is_relative_to(root) or not re.fullmatch("[a-f0-9]{32}", directory.name):
            raise ValueError("unsafe_restore_directory")
        restore_helper(directory)
        return
    identity = uuid4().hex
    directory = root / identity
    directory.mkdir(parents=True)
    database, container = "cw_restore_" + identity, "citeweave-m2-restore-" + identity[:12]
    admin = create_engine(settings().db_url(), isolation_level="AUTOCOMMIT")
    created_database = started_container = False
    start = time.monotonic()
    manifest = dict(
        id=identity,
        at=datetime.now(timezone.utc).isoformat(),
        consistency="CiteWeave API and worker quiesced; pg_dump plus immutable CAS copy",
        status="RUNNING",
    )
    try:
        command(COMPOSE + ["stop", "api", "m1-worker"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            with transaction() as db:
                assert not db.scalar(
                    select(IngestionJobRow.id)
                    .where(
                        IngestionJobRow.status.in_(
                            ["PENDING", "PARSING", "CHUNKING", "EMBEDDING", "INDEXING", "RETRY_WAIT"]
                        )
                    )
                    .limit(1)
                ), "wait_for_ingestion_before_backup"
                assert not db.scalar(
                    select(QueryRunRow.id).where(QueryRunRow.status == "RUNNING").limit(1)
                ), "wait_for_queries_before_backup"
                assert not db.scalar(
                    select(EvalRunRow.id).where(EvalRunRow.status.in_(["PENDING", "RUNNING"])).limit(1)
                ), "wait_for_evaluation_before_backup"
                manifest["query_runs"] = db.scalar(select(func.count()).select_from(QueryRunRow))
                manifest["citations"] = db.scalar(select(func.count()).select_from(CitationRow))
            with (directory / "postgres.dump").open("wb") as output:
                command(
                    [
                        "docker",
                        "exec",
                        "citeweave-m0-postgres-1",
                        "pg_dump",
                        "-U",
                        "citeweave",
                        "-Fc",
                        "--no-owner",
                        "--no-privileges",
                        "citeweave",
                    ],
                    stdout=output,
                    stderr=subprocess.PIPE,
                )
            shutil.copytree(settings().blob_root, directory / "blobs")
            manifest["blobs"] = verify_blob_tree(directory / "blobs")
            manifest["dump_sha256"] = hashlib.sha256((directory / "postgres.dump").read_bytes()).hexdigest()
            (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        finally:
            command(
                COMPOSE + ["start", "api", "m1-worker"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        print("BACKUP SAVED; live services resumed", identity, flush=True)
        with admin.connect() as connection:
            connection.execute(text('CREATE DATABASE "' + database + '"'))
        created_database = True
        with (directory / "postgres.dump").open("rb") as dump:
            command(
                [
                    "docker",
                    "exec",
                    "-i",
                    "citeweave-m0-postgres-1",
                    "pg_restore",
                    "--no-owner",
                    "--no-privileges",
                    "-U",
                    "citeweave",
                    "-d",
                    database,
                ],
                stdin=dump,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        image = command(
            ["docker", "inspect", "--format", "{{.Config.Image}}", "citeweave-m0-qdrant-1"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        command(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                container,
                "--memory",
                "256m",
                "-p",
                "127.0.0.1:16334:6333",
                image,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        started_container = True
        import httpx

        for _ in range(40):
            try:
                if httpx.get("http://127.0.0.1:16334/readyz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        target = admin.url.set(database=database)
        env = dict(
            os.environ,
            CW_DATABASE_URL=target.render_as_string(hide_password=False),
            CW_BLOB_ROOT=str(directory / "blobs"),
            CW_QDRANT_URL="http://127.0.0.1:16334",
            PYTHONIOENCODING="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-u", str(Path(__file__).resolve()), "--restore-helper", str(directory)],
            cwd=ROOT,
            env=env,
            timeout=1200,
        )
        if result.returncode:
            raise RuntimeError("isolated_restore_failed")
        report = json.loads((directory / "restore-result.json").read_text(encoding="utf-8"))
        report.update(
            backup_id=identity,
            duration_seconds=round(time.monotonic() - start, 2),
            dump_sha256=manifest["dump_sha256"],
            consistency=manifest["consistency"],
            production_database_overwritten=False,
            old_ragflow_touched=False,
        )
        label = args.report_prefix or args.milestone
        if not label.replace("-", "").isalnum():
            raise ValueError("invalid_report_prefix")
        (ROOT / f"docs/reports/{label}-recovery.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    finally:
        if started_container:
            command(["docker", "stop", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if created_database:
            assert re.fullmatch(r"cw_restore_[a-f0-9]{32}", database)
            with admin.connect() as connection:
                connection.execute(text('DROP DATABASE "' + database + '"'))
        admin.dispose()


if __name__ == "__main__":
    main()
