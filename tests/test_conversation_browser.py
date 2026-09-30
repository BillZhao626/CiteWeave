"""Opt-in Chromium E2E against real HTTP/PG with the existing injected seam only.

Build web first, install Playwright Chromium, then:
CW_RUN_INTEGRATION=1 pytest -q -s tests/test_conversation_browser.py
Never starts a provider, broker, worker or index; no test HTTP routes/config mode.
"""

import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from io import BytesIO
from threading import Thread

import test_conversation_postgres as pg
import uvicorn
from conversation_evidence_fixtures import Fixture, require_isolated_database
from pydantic import SecretStr
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select
from test_conversation_api_postgres import Runtime

from citeweave import conversations as core
from citeweave.api import create_app
from citeweave.blobs import LocalBlobStore
from citeweave.conversation_interpretation import InterpretationDraft, StateCorrection, TextSpan
from citeweave.conversation_models import (
    ConversationAcceptanceRow,
    ConversationRow,
    ConversationRunRow,
    ConversationTurnRow,
)
from citeweave.db import engine, transaction
from citeweave.domain import IngestionJobRow, VersionRow
from citeweave.settings import ROOT, settings

isolated_pg = pg.isolated_pg
pytestmark = pg.pytestmark


class BrowserRuntime(Runtime):
    def execute(self, workspace, run):
        body, previous = core.execution_input(workspace, run)
        # Synthetic inputs select deterministic test scenarios only in this harness.
        self.kind = {
            "Clarify receiver": "clarification",
            "No matching evidence": "evidence_insufficient",
            "Lose receipt after commit": "lost_receipt",
        }.get(body.question, "documentary_answer")
        self.draft, self.explicit = None, ()
        if self.kind == "evidence_insufficient" and previous:
            self.explicit = (previous.state.source,)
            self.draft = InterpretationDraft(
                topic_relation="continue",
                dependency="none",
                corrections=tuple(
                    StateCorrection(item_id=entry.item.id, mention=TextSpan(start=0, end=len(body.question)))
                    for entry in previous.state.entries
                    if entry.active and entry.item.kind == "ambiguity"
                ),
            )
        super().execute(workspace, run)


@contextmanager
def serve(app):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            limit = time.monotonic() + 15
            while not server.started and thread.is_alive() and time.monotonic() < limit:
                time.sleep(0.05)
            assert server.started, "isolated_browser_server_start_failed"
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            assert not thread.is_alive(), "isolated_browser_server_shutdown_failed"


def test_browser_conversation_workflow(tmp_path, monkeypatch):
    with engine().connect() as connection:
        require_isolated_database(connection)
    config = settings()
    monkeypatch.setattr(config, "blob_root", tmp_path / "blobs")
    monkeypatch.setattr(config, "deepseek_api_key", SecretStr(""))
    monkeypatch.setattr(config, "model_token", SecretStr(""))

    def deny_external_http(*args, **kwargs):
        raise AssertionError("browser_fixture_must_not_call_external_adapters")

    monkeypatch.setattr("httpx.Client.send", deny_external_http)
    monkeypatch.setattr("httpx.AsyncClient.send", deny_external_http)
    assert (config.web_root / "index.html").is_file(), "build_frontend_before_browser_e2e"
    workspace, scope = pg.metadata()
    buffer = BytesIO()
    pdf = Canvas(buffer, pagesize=(600, 800), invariant=True)
    pdf.drawString(60, 680, "The receiver discards the damaged message.")
    pdf.save()
    key = LocalBlobStore(config.blob_root).put(buffer.getvalue())
    with transaction() as db:
        version = db.get(VersionRow, scope.version_ids[0])
        version.blob_key = version.source_sha256 = key
        version.page_count = version.chunk_count = 1
        document = version.document_id
        db.add(
            IngestionJobRow(
                document_version_id=version.id, status="READY", pipeline_version="synthetic-browser-only"
            )
        )
    fixture = Fixture(workspace, scope, document, source_sha256=key)
    fixture.persist()
    runtime = BrowserRuntime(fixture)
    token = "synthetic-browser-token-not-a-secret"
    # Serve the production build and unchanged public API from both applications.
    with serve(create_app(token, workspace, conversation_runtime=runtime)) as url:
        with serve(create_app(token, workspace)) as default_url:
            env = {k: v for k, v in os.environ.items() if not k.startswith("CW_")}
            env.update(
                CW_BROWSER_TEST_URL=url,
                CW_BROWSER_DEFAULT_URL=default_url,
                CW_BROWSER_KB=str(scope.kb_id),
                CW_BROWSER_VERSION=str(fixture.version),
                DEEPSEEK_API_KEY="",
                HF_HUB_OFFLINE="1",
                TRANSFORMERS_OFFLINE="1",
            )
            subprocess.run(
                [shutil.which("node"), "node_modules/@playwright/test/cli.js", "test"],
                cwd=ROOT / "apps/web",
                env=env,
                check=True,
                timeout=180,
            )
    with transaction() as db:
        # Three intentional turns plus one lost-receipt turn. Replays/default 503s
        # create no extra identities; assert PG truth, not browser request counts alone.
        for model in (ConversationTurnRow, ConversationRunRow, ConversationAcceptanceRow):
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(model)
                    .join(ConversationRow, model.conversation_id == ConversationRow.id)
                    .where(ConversationRow.workspace_id == workspace)
                )
                == 4
            )
    assert runtime.calls == 4
