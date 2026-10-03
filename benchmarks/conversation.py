"""Provider-free, disposable-PG, real HTTP Conversation benchmark.

Run from the repository: python -m benchmarks.conversation freeze|run|report.
Only the project-owned original synthetic fixture is seeded. No configured DB is
migrated. Receipts are append-only and confined to ignored .runtime/performance/m3.
"""

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import socket
import subprocess
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
import psutil
from pydantic import SecretStr
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from benchmarks.conversation_server import TOKEN, fixture_for
from benchmarks.report import percentiles
from citeweave.conversation_contract import Scope
from citeweave.conversation_models import ConversationAcceptanceRow, ConversationRunRow, ConversationTurnRow
from citeweave.db import engine, migrate, transaction
from citeweave.domain import DocumentRow, KnowledgeBaseRow, ProviderPhaseRow, VersionRow
from citeweave.settings import ROOT, settings

CONTRACT_PATH = ROOT / "benchmarks/conversation_contract.json"
EVIDENCE = ROOT / ".runtime/performance/m3"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def write(path, value):
    # Existing receipts must never be overwritten by another execution.
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def owned_output(name):
    if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in name):
        raise ValueError("simple_receipt_name_required")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    folder = EVIDENCE / name
    folder.mkdir(exist_ok=False)
    return folder


def source():
    files = git(
        "ls-files", "src", "migrations", "prompts", "tests/conversation_evidence_fixtures.py", "uv.lock"
    ).splitlines()
    return dict(
        commit=git("rev-parse", "HEAD"),
        tree=git("rev-parse", "HEAD^{tree}"),
        product_hashes={p: sha(ROOT / p) for p in files},
        harness_hashes={
            p: sha(ROOT / p)
            for p in (
                "benchmarks/conversation.py",
                "benchmarks/conversation_server.py",
                "benchmarks/conversation_contract.json",
                "benchmarks/report.py",
            )
        },
        dirty=bool(git("status", "--porcelain")),
    )


def freeze():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if git("rev-parse", "HEAD") != contract["baseline_commit"]:
        raise ValueError("baseline_mismatch")
    # Harness/doc changes are allowed; production code must still match HEAD.
    if git("diff", "HEAD", "--", "src", "migrations", "prompts"):
        raise ValueError("baseline_product_changed")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    write(
        EVIDENCE / "frozen-contract.json",
        dict(
            contract=contract,
            contract_sha256=sha(CONTRACT_PATH),
            source=source(),
            frozen_at=datetime.now(timezone.utc).isoformat(),
        ),
    )
    print("Benchmark contract frozen; product source unchanged.")


@contextmanager
def disposable_pg():
    config = settings()
    original = config.database_url
    url = make_url(config.db_url())
    if url.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("loopback_postgres_required")
    name = "cw_conversation_test_" + uuid4().hex
    assert UUID(name.removeprefix("cw_conversation_test_")).hex == name.removeprefix("cw_conversation_test_")
    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 3})
    created = False
    try:
        with admin.connect() as db:
            db.execute(text('CREATE DATABASE "' + name + '"'))
        created = True
        engine.cache_clear()
        config.database_url = SecretStr(url.set(database=name).render_as_string(hide_password=False))
        migrate()
        yield name, url.set(database=name)
    finally:
        if created:
            engine().dispose()
            engine.cache_clear()
            config.database_url = original
            with admin.connect() as db:
                db.execute(text('DROP DATABASE "' + name + '"'))
        admin.dispose()


def seed(contract):
    namespace = uuid5(NAMESPACE_URL, f"citeweave-m3-original-{contract['seed']}")
    workspace, kb, document, version = (
        uuid5(namespace, k) for k in ("workspace", "kb", "document", "version")
    )
    scope = Scope(kb_id=kb, version_ids=(version,))
    with transaction() as db:
        db.add(
            KnowledgeBaseRow(
                id=kb, workspace_id=workspace, name="M3 original synthetic", key="m3", fingerprint="0" * 64
            )
        )
        db.flush()
        db.add(DocumentRow(id=document, kb_id=kb, title="M3 original fixture", active_version_id=version))
        db.flush()
        db.add(
            VersionRow(
                id=version,
                document_id=document,
                kb_id=kb,
                sequence=1,
                filename="synthetic.pdf",
                license="original",
                source_sha256="0" * 64,
                blob_key="0" * 64,
                status="READY",
                profile={},
                key="m3",
                fingerprint="0" * 64,
            )
        )
    fixture = fixture_for(workspace, scope, document, namespace)
    fixture.persist()
    return dict(
        workspace=str(workspace),
        scope=scope.model_dump(mode="json"),
        document=str(document),
        namespace=str(namespace),
    ), fixture


@contextmanager
def retrieval(profile, fixture):
    if profile == "A":
        yield None
        return
    from qdrant_client import QdrantClient
    from qdrant_client import models as qm

    from citeweave.retrieval import BM25Encoder

    parsed = httpx.URL(settings().qdrant_url)
    if parsed.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("loopback_qdrant_required")
    client = QdrantClient(url=settings().qdrant_url, trust_env=False, check_compatibility=False)
    name = fixture.binding.index_name
    created = False
    try:
        if client.collection_exists(name):
            raise ValueError("owned_collection_already_exists")
        client.create_collection(
            name,
            vectors_config={"dense": qm.VectorParams(size=2, distance=qm.Distance.COSINE)},
            sparse_vectors_config={"bm25": qm.SparseVectorParams()},
        )
        created = True
        payload = fixture.branch(fixture.binding, fixture.snapshot, "dense", [1, 0], Event())[0].payload
        sparse = BM25Encoder(**fixture.bm25).document_vector(0)
        vectors = {"dense": [1.0, 0.0], "bm25": qm.SparseVector(indices=sparse.indices, values=sparse.values)}
        client.upsert(
            name,
            points=[
                qm.PointStruct(id=str(fixture.child_id), vector=vectors, payload=payload),
                qm.PointStruct(
                    id=str(uuid4()), vector=vectors, payload=dict(payload, version_id=str(uuid4()))
                ),
                qm.PointStruct(
                    id=str(uuid4()), vector=vectors, payload=dict(payload, workspace_id=str(uuid4()))
                ),
            ],
            wait=True,
        )
        with httpx.Client(trust_env=False) as http:
            version = http.get(settings().qdrant_url).json()["version"]
        yield version
    finally:
        if created:
            client.delete_collection(name)
        client.close()


class Resources:
    def __init__(self, pid, url, name):
        launched = psutil.Process(pid)
        # Windows venv python.exe is a launcher; sample its actual Python worker.
        workers = [
            p for p in launched.children(recursive=True) if "benchmarks.conversation_server" in p.cmdline()
        ]
        self.process = workers[-1] if workers else launched
        self.monitor = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 3})
        self.name, self.stop = name, Event()
        self.rows, self.errors = [], []
        self.thread = Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop.is_set():
            started = time.perf_counter()
            try:
                with self.monitor.connect() as db:
                    connections, active, waiting = db.execute(
                        text("""SELECT count(*),
                        count(*) FILTER (WHERE state='active'), count(*) FILTER (WHERE wait_event_type='Lock')
                        FROM pg_stat_activity WHERE datname=:name AND pid<>pg_backend_pid()"""),
                        {"name": self.name},
                    ).one()
                cpu = self.process.cpu_times()
                self.rows.append(
                    dict(
                        monotonic=started,
                        server_cpu_seconds=cpu.user + cpu.system,
                        server_rss_bytes=self.process.memory_info().rss,
                        system_cpu_percent=psutil.cpu_percent(),
                        available_memory_bytes=psutil.virtual_memory().available,
                        pg_connections=connections,
                        pg_active=active,
                        pg_lock_waiters=waiting,
                    )
                )
            except Exception as exc:
                self.errors.append(type(exc).__name__)
            self.stop.wait(0.2)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(5)
        self.monitor.dispose()
        if self.thread.is_alive():
            raise RuntimeError("sampler_did_not_stop")


async def operation(client, item, timeout):
    start = time.perf_counter()
    row = dict(
        identity=item["identity"], arrival=start, queued_at=item.get("queued_at", start), status="failure"
    )
    headers = {"Idempotency-Key": item["identity"], "x-m3-operation": item["identity"]}
    try:
        async with asyncio.timeout(timeout):
            response = await client.post(
                f"/v1/conversations/{item['conversation']}/turns", json=item["body"], headers=headers
            )
            row["post_ms"] = (time.perf_counter() - start) * 1000
            row["http_status"] = response.status_code
            if response.status_code != 200 or response.json().get("status") != "ACCEPTED":
                row["error"] = "post_not_accepted"
                return row
            run = response.json()["id"]
            row["run_id"], row["conversation"] = run, item["conversation"]
            path = f"/v1/conversations/{item['conversation']}/runs/{run}"
            result = await client.get(path + "/result", headers=headers)
            trace = await client.get(path + "/trace", headers=headers)
            if result.status_code != 200 or trace.status_code != 200:
                row["error"] = "readback_failed"
                return row
            value = result.json()
            diagnostic = trace.json()
            citations = value["result"]["citations"]
            op = diagnostic["operational"]
            valid = (
                value["run_id"] == run
                and value["result"]["kind"] == "documentary_answer"
                and len(citations) == 1
                and citations[0]["span"]["quote"] == "The receiver discards the damaged message."
                and op["publication"] == "ACCEPTED"
                and not op["truncated"]
                and len(op["provider_phases"]) == 1
                and op["provider_phases"][0]["state"] == "COMPLETED"
                and op["provider_phases"][0]["attempt"] == 1
                and citations[0]["document_version_id"] == item["body"]["scope"]["version_ids"][0]
                and diagnostic["run_id"] == run
                and diagnostic["acceptance_id"] == value["acceptance_id"]
            )
            if item["body"]["expected_head"] is not None:
                valid = valid and bool(diagnostic["history_sources"])
            if not valid:
                row["error"] = "correctness_failed"
                return row
            row.update(status="success", trace=diagnostic, acceptance_id=value["acceptance_id"])
    except (TimeoutError, httpx.TimeoutException):
        row.update(status="timeout", error="workflow_timeout")
    except Exception as exc:
        row["error"] = type(exc).__name__
    finally:
        row["finish"] = time.perf_counter()
        row["latency_ms"] = (row["finish"] - start) * 1000
        row["enqueue_to_finish_ms"] = (row["finish"] - row["queued_at"]) * 1000
    return row


async def workload(client, items, concurrency, timeout):
    pending = asyncio.Queue()
    enqueue = time.perf_counter()
    for item in items:
        pending.put_nowait(dict(item, queued_at=enqueue))
    rows = []

    async def worker():
        while not pending.empty():
            item = pending.get_nowait()
            rows.append(await operation(client, item, timeout))

    started = time.perf_counter()
    await asyncio.gather(*(worker() for _ in range(concurrency)))
    return rows, time.perf_counter() - started


def summarize(rows, wall):
    if not rows or len({r["identity"] for r in rows}) != len(rows):
        raise ValueError("missing_or_duplicate_outcome")
    if wall <= 0 or not all(math.isfinite(r["latency_ms"]) and r["latency_ms"] >= 0 for r in rows):
        raise ValueError("invalid_timing")
    successes = [r for r in rows if r["status"] == "success"]
    return dict(
        attempted=len(rows),
        successful=len(successes),
        failed=len(rows) - len(successes),
        timeouts=sum(r["status"] == "timeout" for r in rows),
        statuses=dict(Counter(r["status"] for r in rows)),
        success_rate=len(successes) / len(rows),
        wall_seconds=wall,
        throughput_rps=len(successes) / wall,
        latency_ms=percentiles(r["latency_ms"] for r in rows),
        success_latency_ms=percentiles(r["latency_ms"] for r in successes),
        post_ms=percentiles(r["post_ms"] for r in rows if "post_ms" in r),
        enqueue_to_finish_ms=percentiles(r["enqueue_to_finish_ms"] for r in rows),
    )


async def prepare(client, config, contract, prefix, count):
    async def one(index):
        identity = f"{prefix}-{index:03}"
        response = await client.post("/v1/conversations", headers={"Idempotency-Key": identity})
        if response.status_code != 200:
            raise RuntimeError("seed_conversation_failed")
        item = dict(
            identity=identity + "-seed",
            conversation=response.json()["id"],
            body=dict(question=contract["seed_question"], scope=config["scope"], expected_head=None),
        )
        row = await operation(client, item, contract["timeout_seconds"])
        if row["status"] != "success":
            raise RuntimeError("seed_turn_failed_" + row.get("error", "unknown"))
        return dict(
            identity=identity,
            conversation=item["conversation"],
            body=dict(
                question=contract["measured_question"],
                scope=config["scope"],
                expected_head=row["acceptance_id"],
            ),
        )

    # Untimed setup uses five bounded workers and never becomes a load sample.
    limit = asyncio.Semaphore(5)

    async def bounded(index):
        async with limit:
            return await one(index)

    return await asyncio.gather(*(bounded(i) for i in range(count)))


def cardinalities():
    with transaction() as db:
        return {
            name: db.scalar(select(func.count()).select_from(model))
            for name, model in (
                ("runs", ConversationRunRow),
                ("turns", ConversationTurnRow),
                ("acceptances", ConversationAcceptanceRow),
                ("phases", ProviderPhaseRow),
            )
        }


async def sweep(config, contract, folder, pid, url, name, concurrency):
    async with httpx.AsyncClient(
        base_url=f"http://127.0.0.1:{config['port']}",
        trust_env=False,
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=contract["timeout_seconds"],
        limits=httpx.Limits(max_connections=40, max_keepalive_connections=40),
    ) as client:
        for _ in range(120):
            try:
                if (await client.get("/health/live")).status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            await asyncio.sleep(0.25)
        else:
            raise RuntimeError("benchmark_server_unavailable")
        for c in concurrency:
            for repeat in range(1, contract["repeats"] + 1):
                before = cardinalities()
                prefix = f"c{c:02}-r{repeat}"
                warm = await prepare(
                    client, config, contract, prefix + "-warm", contract["warmup_per_repeat"]
                )
                measured = await prepare(client, config, contract, prefix, contract["requests_per_repeat"])
                await client.get("/__m3_metrics")  # Drain untimed setup only.
                warm_rows, warm_wall = await workload(client, warm, c, contract["timeout_seconds"])
                write(
                    folder / f"{prefix}-warmup.json",
                    dict(rows=warm_rows, summary=summarize(warm_rows, warm_wall)),
                )
                warm_correct = all(r["status"] == "success" for r in warm_rows)
                await client.get("/__m3_metrics")
                with Resources(pid, url, name) as resources:
                    rows, wall = await workload(client, measured, c, contract["timeout_seconds"])
                metric_response = await client.get("/__m3_metrics")
                metric_response.raise_for_status()
                metrics = metric_response.json()
                for row in rows:
                    row["instrumentation"] = metrics.get(row["identity"], [])
                after = cardinalities()
                delta = {k: after[k] - before[k] for k in after}
                expected = 2 * (len(warm) + len(measured))
                consistent = len(rows) == len(measured) and all(v == expected for v in delta.values())
                summary = summarize(rows, wall)
                write(
                    folder / f"{prefix}.json",
                    dict(
                        concurrency=c,
                        repeat=repeat,
                        inputs=measured,
                        rows=rows,
                        summary=summary,
                        resources=resources.rows,
                        resource_errors=resources.errors,
                        cardinality_delta=delta,
                        expected_delta=expected,
                        correctness_cardinality=consistent,
                        warmup_correct=warm_correct,
                    ),
                )
                print(
                    f"{config['profile']} {prefix}: {summary['successful']}/{summary['attempted']} "
                    f"p95={summary['latency_ms']['p95']:.1f}ms rps={summary['throughput_rps']:.2f}",
                    flush=True,
                )
                # Preserve the full finite sweep including failure onset. Such
                # evidence is invalid for a successful performance claim.
                if psutil.virtual_memory().available < 512 * 1024**2:
                    raise RuntimeError("resource_health_floor_reached")
        # A separate 20-client duplicate wave on one fresh logical request.
        duplicate = (await prepare(client, config, contract, "duplicate", 1))[0]
        before = cardinalities()
        responses = await asyncio.gather(
            *(
                client.post(
                    f"/v1/conversations/{duplicate['conversation']}/turns",
                    json=duplicate["body"],
                    headers={"Idempotency-Key": duplicate["identity"]},
                )
                for _ in range(20)
            )
        )
        after = cardinalities()
        identities = {r.json().get("id") for r in responses}
        correct = (
            len(identities) == 1
            and all(r.status_code in {200, 202} for r in responses)
            and all(after[k] - before[k] == 1 for k in after)
        )
        write(
            folder / "duplicate.json",
            dict(
                attempted=20,
                statuses=dict(Counter(r.status_code for r in responses)),
                distinct_runs=len(identities),
                delta={k: after[k] - before[k] for k in after},
                correct=correct,
            ),
        )
        if not correct:
            raise RuntimeError("duplicate_correctness_failed")


def environment(qdrant_version):
    with transaction() as db:
        values = {
            key: db.scalar(text("SHOW " + key))
            for key in (
                "server_version",
                "max_connections",
                "shared_buffers",
                "work_mem",
                "synchronous_commit",
                "max_locks_per_transaction",
            )
        }
        values["alembic_head"] = db.scalar(text("SELECT version_num FROM alembic_version"))
    return dict(
        os=platform.system(),
        os_release=platform.release(),
        architecture=platform.machine(),
        python=platform.python_version(),
        logical_cpus=psutil.cpu_count(),
        available_memory_bytes=psutil.virtual_memory().available,
        total_memory_bytes=psutil.virtual_memory().total,
        postgres=values,
        qdrant=qdrant_version,
        packages={
            p: importlib.metadata.version(p)
            for p in (
                "fastapi",
                "starlette",
                "anyio",
                "uvicorn",
                "sqlalchemy",
                "psycopg",
                "httpx",
                "qdrant-client",
                "psutil",
            )
        },
        service_scope="Existing project PostgreSQL (320MiB Docker limit), optional project Qdrant (512MiB); native Windows API process; existing unrelated services stay stopped",
    )


def run(args):
    frozen = json.loads((EVIDENCE / "frozen-contract.json").read_text(encoding="utf-8"))
    if frozen["contract_sha256"] != sha(CONTRACT_PATH):
        raise ValueError("frozen_contract_changed")
    current = source()
    if current["harness_hashes"] != frozen["source"]["harness_hashes"]:
        raise ValueError("frozen_harness_changed")
    contract = frozen["contract"]
    concurrency = [args.concurrency] if args.concurrency else contract["concurrency"]
    if args.concurrency and args.concurrency not in contract["concurrency"]:
        raise ValueError("unfrozen_concurrency")
    folder = owned_output(args.name)
    with disposable_pg() as (name, url):
        config, fixture = seed(contract)
        config["profile"] = args.profile
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            config["port"] = sock.getsockname()[1]
        write(folder / "server.json", config)
        with retrieval(args.profile, fixture) as qdrant_version:
            write(
                folder / "manifest.json",
                dict(
                    contract_sha256=frozen["contract_sha256"],
                    contract=contract,
                    source=current,
                    profile=args.profile,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    environment=environment(qdrant_version),
                    concurrency=concurrency,
                    provider_model_judge_calls=0,
                    monetary_spend_cny=0,
                ),
            )
            env = {k: v for k, v in os.environ.items() if not k.startswith("CW_") and k != "DEEPSEEK_API_KEY"}
            env.update(
                CW_DATABASE_URL=url.render_as_string(hide_password=False),
                DEEPSEEK_API_KEY="",
                CW_CONVERSATION_RUNTIME_POLICY="",
                CW_CONVERSATION_TOKENIZER="",
                CW_QDRANT_URL=settings().qdrant_url,
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
                PYTHONUTF8="1",
                PYTHONIOENCODING="utf-8",
            )
            with (folder / "server.log").open("x", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "benchmarks.conversation_server", str(folder / "server.json")],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                try:
                    asyncio.run(sweep(config, contract, folder, process.pid, url, name, concurrency))
                finally:
                    process.terminate()
                    process.wait(timeout=15)
    write(
        folder / "completed.json",
        dict(
            disposable_database_dropped=True,
            disposable_collection_dropped=args.profile == "B",
            finished=datetime.now(timezone.utc).isoformat(),
        ),
    )
    report(folder)


def report(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    result = {}
    for c in manifest["concurrency"]:
        receipts = [
            json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob(f"c{c:02}-r[123].json"))
        ]
        if len(receipts) != manifest["contract"]["repeats"]:
            raise ValueError("incomplete_repeat_evidence")
        rows = [r for receipt in receipts for r in receipt["rows"]]
        result[str(c)] = dict(
            summarize(rows, sum(r["summary"]["wall_seconds"] for r in receipts)),
            repeats=[r["summary"] for r in receipts],
            correctness_cardinality=all(r["correctness_cardinality"] for r in receipts),
            warmup_correct=all(r["warmup_correct"] for r in receipts),
            phase_ms={
                phase: percentiles(
                    d["latency_ms"]
                    for r in rows
                    for d in r.get("trace", {}).get("operational", {}).get("durations", [])
                    if d["phase"] == phase and d["latency_ms"] is not None
                )
                for phase in (
                    "admission_queue",
                    "history",
                    "interpretation",
                    "retrieval",
                    "generation",
                    "validation",
                    "publication",
                )
            },
            instrumentation={
                key: percentiles(sum(part[key] for part in r["instrumentation"]) for r in rows)
                for key in (
                    "sql_count",
                    "sql_ms",
                    "scope_sql_ms",
                    "pool_acquisition_ms",
                    "record_ms",
                    "record_count",
                    "event_insert_ms",
                    "synthetic_sends",
                )
            },
        )
    if (folder / "summary.json").exists():
        if json.loads((folder / "summary.json").read_text(encoding="utf-8")) != result:
            raise ValueError("receipt_summary_mismatch")
        return result
    write(folder / "summary.json", result)
    write(
        folder / "hashes.json",
        {p.name: sha(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name != "server.log"},
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("freeze")
    load = actions.add_parser("run")
    load.add_argument("--profile", choices=["A", "B"], required=True)
    load.add_argument("--name", required=True)
    load.add_argument("--concurrency", type=int)
    summarize_parser = actions.add_parser("report")
    summarize_parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze()
    elif args.action == "run":
        run(args)
    else:
        report(args.directory)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Benchmark stopped: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
