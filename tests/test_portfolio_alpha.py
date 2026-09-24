"""Release selection must preserve historical defaults and retrieval parameters."""

from citeweave.settings import Settings
from citeweave.trace import runtime_config


def test_launcher_binds_existing_database_workspace_and_blobs(monkeypatch, tmp_path):
    import importlib.util
    from uuid import UUID

    from sqlalchemy import make_url

    from citeweave.settings import ROOT, settings

    spec = importlib.util.spec_from_file_location("portfolio_alpha", ROOT / "scripts/portfolio_alpha.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setenv("CW_DATABASE_URL", "postgresql://fixture:fixture@localhost:15432/old")
    for key in (
        "CW_WORKSPACE_ID",
        "CW_BLOB_ROOT",
        "CW_RELEASE_IDENTITY",
        "CW_TELECOM_ANSWER_PROMPT",
        "CW_PROVIDER_ATTEMPTS",
    ):
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)
    settings.cache_clear()
    try:
        launcher.configure("existing_public_corpus", UUID(int=123), tmp_path)
        selected = settings()
        url = make_url(selected.db_url())
        assert url.database == "existing_public_corpus" and url.port == 15432
        assert selected.workspace_id == UUID(int=123)
        assert selected.blob_root == tmp_path.resolve()
        assert selected.release_identity == launcher.IDENTITY
        assert selected.telecom_answer_prompt == launcher.PROMPT
        assert selected.provider_attempts == 1
    finally:
        settings.cache_clear()


def test_portfolio_identity_is_explicit_and_preserves_historical_profile(monkeypatch):
    from citeweave import trace

    historical = Settings(_env_file=None, release_identity=None, telecom_answer_prompt="answer-telecom-v1")
    monkeypatch.setattr(trace, "settings", lambda: historical)
    before = runtime_config("telecom-structural-v1")
    assert "release_identity" not in before
    selected = historical.model_copy(
        update={
            "release_identity": "citeweave-portfolio-alpha-e0",
            "telecom_answer_prompt": "answer-telecom-consistency-v1",
        }
    )
    monkeypatch.setattr(trace, "settings", lambda: selected)
    after = runtime_config("telecom-structural-v1")
    assert after.pop("release_identity") == "citeweave-portfolio-alpha-e0"
    assert after.pop("prompt_sha256") == "00877db7c61eb4f5aea05ee8fba6c05253c41e2a9fe9d855c5f5974e2c3497d4"
    before.pop("prompt_sha256")
    assert after.pop("prompt_identity") == "answer-telecom-consistency-v1"
    assert before.pop("prompt_identity") == "answer-telecom-v1"
    after["query_revision"].pop("answer_prompt")
    before["query_revision"].pop("answer_prompt")
    assert after == before


def test_ingestion_worker_keeps_outbox_dispatch_without_evaluation(monkeypatch):
    from citeweave import worker_runtime as worker

    events = []

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

        def wait(self, seconds):
            self.set()

    class Child:
        def poll(self):
            return None

        def terminate(self):
            events.append("terminate")

        def wait(self, timeout):
            events.append("wait")

    def launch(args):
        assert "--queues=cw-ingestion" in args
        assert "--pool=solo" in args
        return Child()

    monkeypatch.setattr(worker.sys, "platform", "win32")
    monkeypatch.setattr(worker.threading, "Event", Stop)
    monkeypatch.setattr(worker.signal, "signal", lambda *args: None)
    monkeypatch.setattr(worker.subprocess, "Popen", launch)
    monkeypatch.setattr(worker, "reconcile", lambda send: send("original-fixture-job"))
    monkeypatch.setattr(worker.ingest, "apply_async", lambda **kwargs: events.append(kwargs))

    def forbidden(*args):
        raise AssertionError("portfolio worker must not dispatch evaluation")

    monkeypatch.setattr(worker, "reconcile_evaluations", forbidden)
    worker.main(ingestion_only=True)
    assert events == [{"args": ["original-fixture-job"], "retry": False}, "terminate", "wait"]
