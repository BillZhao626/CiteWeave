"""Benchmark-only injection into the real API. Never loaded by create_app by default."""

import asyncio
import json
import logging
import sys
import time
from contextvars import ContextVar
from decimal import Decimal
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from uuid import UUID, uuid5

import httpx
import uvicorn
from pydantic import SecretStr
from sqlalchemy import event

from citeweave import conversations as core
from citeweave import operational_trace
from citeweave.api import create_app
from citeweave.conversation_contract import Execution
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_history import HistoryQuery
from citeweave.conversation_interpretation import IntentFact, InterpretationDraft, RetrievalRewrite, TextSpan
from citeweave.conversation_runtime import PhasePlan, ProductionRuntime, RuntimePolicy
from citeweave.db import engine
from citeweave.llm import DeepSeekProvider
from citeweave.provider_accounting import request_hash
from citeweave.settings import ROOT, settings

TOKEN = "original-synthetic-m3-loopback-token"
METRIC = ContextVar("m3_metric", default=None)


class Accounting:
    identity = "M3-SYNTHETIC-NOT-TOKEN-EVIDENCE"

    def measure(self, body):
        return {"input_tokens": 73, "request_hash": request_hash(body)}


class Metric:
    def __init__(self):
        self.lock = Lock()
        self.values = {
            "sql_count": 0,
            "sql_ms": 0.0,
            "scope_sql_ms": 0.0,
            "event_insert_ms": 0.0,
            "pool_acquisition_ms": 0.0,
            "record_ms": 0.0,
            "record_count": 0,
            "synthetic_sends": 0,
        }

    def add(self, **values):
        with self.lock:
            for key, value in values.items():
                self.values[key] += value


def fixture_for(workspace, scope, document, namespace):
    # Reuse only this project's original/licensed synthetic structure fixture.
    from unittest.mock import patch

    sys.path.insert(0, str(ROOT / "tests"))
    import conversation_evidence_fixtures as original

    counter = iter(range(100))
    with patch.object(original, "uuid4", lambda: uuid5(namespace, f"fixture-{next(counter)}")):
        return original.Fixture(workspace, scope, document)


class Runtime:
    def __init__(self, config, fixture):
        self.config, self.fixture = config, fixture

    def prepare(self):
        from datetime import datetime, timedelta, timezone
        from uuid import uuid4

        return Execution(owner=uuid4(), deadline=datetime.now(timezone.utc) + timedelta(seconds=60))

    def execute(self, workspace, run):
        from conversation_evidence_fixtures import FakeModel

        body, previous = core.execution_input(workspace, run)
        entity = "the receiver"
        if previous is None:
            start = body.question.index(entity)
            draft = InterpretationDraft(
                topic_relation="continue",
                dependency="none",
                facts=(
                    IntentFact(
                        kind="entity", value=entity, span=TextSpan(start=start, end=start + len(entity))
                    ),
                ),
            )
        else:
            draft = InterpretationDraft(
                topic_relation="continue",
                dependency="required",
                facts=(IntentFact(kind="entity", value=entity, source=previous.state.source),),
                rewrite=RetrievalRewrite(text=body.question + "\n" + entity, scope=body.scope),
            )
        policy = RuntimePolicy(
            workspace_id=workspace,
            conversation_id=run.conversation_id,
            request=body,
            execution_deadline=run.deadline,
            authorization_id=uuid5(run.id, "m3-synthetic"),
            authorization_deadline=run.deadline,
            max_calls=1,
            max_input_tokens=300,
            max_output_tokens=300,
            max_yuan=Decimal("0.008"),
            phases=(PhasePlan(purpose="generation", input_tokens=300, output_tokens=300),),
            history_scan_limit=512,
            history_statement_ms=1000,
            context_max_bytes=131072,
            reviewed_interpretation=draft,
            history_query=HistoryQuery(
                scope=body.scope,
                expected_head=body.expected_head,
                explicit=(previous.state.source,) if previous else (),
            ),
        )

        async def response(request):
            # A MockTransport supplied explicitly; no socket to a provider/model.
            await asyncio.sleep(0)
            metric = METRIC.get()
            if metric:
                metric.add(synthetic_sends=1)
            content = self.fixture.atom.text + " [E1]"
            chunks = [
                dict(id="synthetic-m3", choices=[dict(delta={"content": content}, finish_reason="stop")]),
                dict(choices=[], usage={"prompt_tokens": 73, "completion_tokens": 20}),
            ]
            return httpx.Response(
                200, text="".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
            )

        runtime = ProductionRuntime(
            policy,
            Accounting(),
            model=FakeModel(),
            provider_factory=lambda: DeepSeekProvider(
                transport=httpx.MockTransport(response), circuit=SimpleNamespace(change=lambda *args: None)
            ),
        )
        if self.config["profile"] == "A":
            runtime.retriever = StructuralEvidenceRetriever(
                model=FakeModel(), branch_query=self.fixture.branch
            )
        try:
            runtime.execute(workspace, run)
        except Exception as exc:
            logging.error("m3_runtime_code=%s", operational_trace.safe_error_code(exc))
            raise


def instrument(db_engine):
    @event.listens_for(db_engine, "before_cursor_execute")
    def before(connection, cursor, statement, parameters, context, executemany):
        context.m3_start = time.perf_counter()

    @event.listens_for(db_engine, "after_cursor_execute")
    def after(connection, cursor, statement, parameters, context, executemany):
        metric = METRIC.get()
        if metric:
            elapsed = (time.perf_counter() - context.m3_start) * 1000
            values = dict(sql_ms=elapsed, sql_count=1)
            if "FOR UPDATE" in statement and (
                "knowledge_bases" in statement or "document_versions" in statement
            ):
                values["scope_sql_ms"] = elapsed
            if statement.startswith("INSERT INTO cw5_run_events"):
                values["event_insert_ms"] = elapsed
            metric.add(**values)

    get = db_engine.pool._do_get

    def acquire():
        started = time.perf_counter()
        try:
            return get()
        finally:
            if (metric := METRIC.get()) is not None:
                metric.add(pool_acquisition_ms=(time.perf_counter() - started) * 1000)

    db_engine.pool._do_get = acquire
    record = operational_trace._record

    def timed_record(*args, **kwargs):
        started = time.perf_counter()
        try:
            return record(*args, **kwargs)
        finally:
            if (metric := METRIC.get()) is not None:
                metric.add(record_ms=(time.perf_counter() - started) * 1000, record_count=1)

    operational_trace._record = timed_record


def main():
    from citeweave.conversation_contract import Scope

    config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    # The launcher validates UUID disposable database ownership before starting us.
    workspace, document, namespace = (UUID(config[k]) for k in ("workspace", "document", "namespace"))
    fixture = fixture_for(workspace, Scope.model_validate(config["scope"]), document, namespace)
    from conversation_evidence_fixtures import require_isolated_database

    if engine().url.host not in {"127.0.0.1", "localhost", "::1"} or config["profile"] not in {"A", "B"}:
        raise ValueError("isolated_loopback_benchmark_required")
    with engine().connect() as connection:
        require_isolated_database(connection)
    settings().deepseek_api_key = SecretStr("synthetic-not-sent-m3")
    settings().conversation_runtime_policy = None
    settings().conversation_tokenizer = None
    app = create_app(TOKEN, workspace, conversation_runtime=Runtime(config, fixture))
    instrument(engine())
    metrics, lock = {}, Lock()

    @app.middleware("http")
    async def collect(request, call_next):
        identity = request.headers.get("x-m3-operation")
        value = Metric() if identity else None
        token = METRIC.set(value)
        try:
            return await call_next(request)
        finally:
            METRIC.reset(token)
            if identity:
                with lock:
                    metrics.setdefault(identity, []).append(value.values)

    @app.get("/__m3_metrics", dependencies=[])
    def read_metrics():
        # Test-only loopback listener, synthetic fixture/auth, never deployed.
        with lock:
            result = dict(metrics)
            metrics.clear()
            return result

    # create_app mounts the frontend at '/', so this test-only route must precede it.
    app.router.routes.insert(0, app.router.routes.pop())
    uvicorn.run(app, host="127.0.0.1", port=config["port"], access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
