"""Bounded query diagnostics. No prompts, credentials or raw upstream bodies are logged."""

import hashlib
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from sqlalchemy import select

from citeweave.costs import attempt_cost
from citeweave.db import transaction
from citeweave.domain import QueryRunRow
from citeweave.pipeline import PROFILE
from citeweave.profiles import DEFAULT_PROFILE, query_profile
from citeweave.reliability import error_category
from citeweave.retrieval import ANALYZER_REVISION
from citeweave.settings import ROOT, settings

current_trace = ContextVar("query_trace", default=None)


def runtime_config(profile=DEFAULT_PROFILE):
    config = settings()
    revision = query_profile(profile)
    if revision.get("unit_kind") == "structural_child":
        revision["answer_prompt"] = config.telecom_answer_prompt
    prompt = revision["answer_prompt"]
    embedding_override = {}
    base_profile = PROFILE
    target = revision.get("unit_kind") == "structural_child"
    if target:
        base_profile = dict(
            PROFILE,
            pipeline="pdf-structure-e5-child-v1",
            unit_kind="structural_child",
            chunk_chars=960,
            bm25_scope="index_build",
            evidence_limit=96,
        )
    if revision.get("embedding_key"):
        from citeweave.embeddings import embedding_identity

        identity = embedding_identity(revision["embedding_key"])
        embedding_override = dict(
            embedding=identity["model"],
            embedding_revision=identity["revision"],
            dimension=identity["dimension"],
            embedding_identity=identity,
        )
    return dict(
        dict(
            base_profile,
            evidence_limit=revision.get("max_evidence_spans", base_profile["evidence_limit"]),
            rerank_limit=revision.get("rerank_limit", PROFILE["rerank_limit"]),
            **embedding_override,
        ),
        query_profile=profile,
        query_revision=revision,
        bm25_analyzer=ANALYZER_REVISION,
        bm25_k1=1.5,
        bm25_b=0.75,
        chunk_overlap=0,
        prompt_identity=prompt,
        prompt_sha256=hashlib.sha256((ROOT / "prompts" / (prompt + ".txt")).read_bytes()).hexdigest(),
        provider="deepseek",
        model=config.deepseek_model,
        query_deadline_seconds=60 if target else config.query_deadline_seconds,
        max_active_queries=config.max_active_queries,
        runtime_policy="provider-phases-v1",
        provider_attempts=1,
        model_attempts=config.model_attempts,
        retry_backoff_seconds=config.retry_backoff_seconds,
        breaker_threshold=config.breaker_threshold,
        breaker_cooldown_seconds=config.breaker_cooldown_seconds,
    )


def stamp():
    return datetime.now(timezone.utc).isoformat()


class RunTrace:
    def __init__(self, run_id, owner=None, fence=None):
        self.run_id, self.stages, self.calls = run_id, [], []
        self.owner, self.fence = owner, fence
        self.lock = threading.RLock()
        self.cancelled = threading.Event()

    def remaining(self):
        from citeweave.query_runtime import remaining

        if self.cancelled.is_set():
            raise RuntimeError("query_cancelled")
        return remaining(self.run_id, self.owner, self.fence)

    def persist(self):
        with self.lock, transaction() as db:
            row = db.scalar(select(QueryRunRow).where(QueryRunRow.id == self.run_id).with_for_update())
            if row.owner != self.owner or row.fence != self.fence:
                return
            row.stages, row.calls = list(self.stages), list(self.calls)
            provider_calls = [call for call in self.calls if call["upstream"] == "deepseek"]
            if provider_calls:
                row.estimated_yuan = attempt_cost(provider_calls)

    @contextmanager
    def stage(self, name, **fields):
        start = time.perf_counter()
        entry = dict(name=name, started_at=stamp(), status="RUNNING", **fields)
        with self.lock:
            self.stages.append(entry)
            self.persist()
        try:
            yield entry
            entry["status"] = "COMPLETED"
        except BaseException as exc:
            code = getattr(
                exc,
                "code",
                "client_cancelled"
                if type(exc).__name__ in {"CancelledError", "GeneratorExit"}
                else type(exc).__name__,
            )
            entry.update(status="FAILED", error_code=code, error_category=error_category(code))
            raise
        finally:
            entry.update(ended_at=stamp(), latency_ms=round((time.perf_counter() - start) * 1000, 3))
            self.persist()

    def call(self, value):
        # Adapters create this allowlisted summary; no full request/response reaches this method.
        with self.lock:
            self.calls.append(value)
            if len(self.calls) > 200:
                raise ValueError("trace_call_limit")
            self.persist()


@contextmanager
def stage(name, **fields):
    trace = current_trace.get()
    if trace:
        if trace.cancelled.is_set():
            raise RuntimeError("query_cancelled")
        with trace.stage(name, **fields) as entry:
            yield entry
    else:
        yield fields


def record_call(value):
    if trace := current_trace.get():
        trace.call(value)


def network_timeout(limit):
    """Check PG ownership before I/O; each adapter receives the remaining budget."""
    if deadline := stage_deadline.get():
        limit = min(limit, deadline - time.monotonic())
        if limit <= 0:
            raise TimeoutError("stage_deadline_exhausted")
    if trace := current_trace.get():
        return min(limit, trace.remaining())
    if guard := ingestion_guard.get():
        return min(limit, guard())
    return limit


ingestion_guard = ContextVar("ingestion_guard", default=None)

stage_deadline = ContextVar("stage_deadline", default=None)


@contextmanager
def bounded_stage(seconds):
    deadline = time.monotonic() + seconds
    if outer := stage_deadline.get():
        deadline = min(deadline, outer)
    token = stage_deadline.set(deadline)
    try:
        network_timeout(seconds)
        yield deadline
        network_timeout(seconds)
    finally:
        stage_deadline.reset(token)
