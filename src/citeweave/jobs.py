"""PostgreSQL is the durable authority; broker messages are disposable wakeups."""

from __future__ import annotations

import hashlib
import json
import os
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def connect():
    return psycopg.connect(os.environ["CW_DATABASE_URL"], row_factory=dict_row, connect_timeout=3)


def initialize():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS cw_jobs (
          id uuid PRIMARY KEY, scope uuid NOT NULL, key text NOT NULL, fingerprint text NOT NULL,
          payload jsonb NOT NULL, status text NOT NULL DEFAULT 'queued',
          fence bigint NOT NULL DEFAULT 0, owner text, lease_until timestamptz,
          attempts int NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(scope,key), CHECK(status IN ('queued','running','completed','failed')));
        CREATE TABLE IF NOT EXISTS cw_outbox (
          id bigserial PRIMARY KEY, job_id uuid NOT NULL REFERENCES cw_jobs(id),
          published_at timestamptz, created_at timestamptz NOT NULL DEFAULT now());
        CREATE TABLE IF NOT EXISTS cw_effects (
          job_id uuid PRIMARY KEY REFERENCES cw_jobs(id), result jsonb NOT NULL, fence bigint NOT NULL);
        CREATE TABLE IF NOT EXISTS cw_job_events (
          id bigserial PRIMARY KEY, job_id uuid NOT NULL REFERENCES cw_jobs(id),
          event text NOT NULL, owner text, created_at timestamptz NOT NULL DEFAULT now());""")


def submit(scope: str, key: str, payload: dict) -> tuple[str, bool]:
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    identity = str(uuid4())
    with connect() as db:
        row = db.execute(
            """INSERT INTO cw_jobs(id,scope,key,fingerprint,payload) VALUES (%s,%s,%s,%s,%s)
          ON CONFLICT(scope,key) DO NOTHING RETURNING id""",
            (identity, scope, key, fingerprint, Jsonb(payload)),
        ).fetchone()
        if row:
            db.execute("INSERT INTO cw_outbox(job_id) VALUES (%s)", (identity,))
            return identity, True
        existing = db.execute(
            "SELECT id,fingerprint FROM cw_jobs WHERE scope=%s AND key=%s", (scope, key)
        ).fetchone()
        if existing["fingerprint"] != fingerprint:
            raise ValueError("idempotency_conflict")
        return str(existing["id"]), False


def claim(identity: str, owner: str, lease_seconds: int = 8) -> dict | None:
    with connect() as db:
        db.execute(
            "INSERT INTO cw_job_events(job_id,event,owner) VALUES (%s,%s,%s)", (identity, "delivery", owner)
        )
        return db.execute(
            """UPDATE cw_jobs SET status='running', fence=fence+1, attempts=attempts+1,
            owner=%s, lease_until=now()+%s*interval '1 second'
            WHERE id=%s AND (status='queued' OR (status='running' AND lease_until<now()))
            RETURNING *""",
            (owner, lease_seconds, identity),
        ).fetchone()


def heartbeat(identity: str, fence: int, lease_seconds: int = 8) -> bool:
    with connect() as db:
        return (
            db.execute(
                """UPDATE cw_jobs SET lease_until=now()+%s*interval '1 second'
          WHERE id=%s AND fence=%s AND status='running' AND lease_until>now()""",
                (lease_seconds, identity, fence),
            ).rowcount
            == 1
        )


def complete(identity: str, fence: int, result: dict) -> bool:
    with connect() as db:
        row = db.execute(
            """UPDATE cw_jobs SET status='completed',lease_until=NULL
          WHERE id=%s AND fence=%s AND status='running' AND lease_until>now() RETURNING id""",
            (identity, fence),
        ).fetchone()
        if not row:
            return False
        db.execute(
            "INSERT INTO cw_effects(job_id,result,fence) VALUES (%s,%s,%s)", (identity, Jsonb(result), fence)
        )
        db.execute("INSERT INTO cw_job_events(job_id,event) VALUES (%s,%s)", (identity, "committed"))
        return True


def get_job(identity: str) -> dict:
    with connect() as db:
        return db.execute("SELECT * FROM cw_jobs WHERE id=%s", (identity,)).fetchone()


def dispatch(app, limit: int = 100) -> dict:
    # send -> mark: a crash between these operations duplicates delivery, never loses durable intent.
    sent = 0
    with connect() as db:
        rows = db.execute(
            "SELECT id,job_id FROM cw_outbox WHERE published_at IS NULL ORDER BY id LIMIT %s", (limit,)
        ).fetchall()
    for row in rows:
        try:
            app.send_task("citeweave.execute", args=[str(row["job_id"])], queue="citeweave-m0", retry=False)
        except Exception as exc:
            return {"sent": sent, "error_type": type(exc).__name__}
        with connect() as db:
            db.execute("UPDATE cw_outbox SET published_at=now() WHERE id=%s", (row["id"],))
        sent += 1
    return {"sent": sent, "error_type": None}


def reconcile() -> int:
    # Even lost acknowledged broker messages converge from DB state; identity never depends on hostname.
    with connect() as db:
        return db.execute("""INSERT INTO cw_outbox(job_id)
          SELECT j.id FROM cw_jobs j WHERE
          (j.status='queued' OR (j.status='running' AND j.lease_until<now()))
          AND NOT EXISTS(SELECT 1 FROM cw_outbox o WHERE o.job_id=j.id AND o.published_at IS NULL)""").rowcount
