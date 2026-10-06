from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from citeweave.api import create_app
from citeweave.runtime_operations import CollectionObservation, observe_collections, observe_model


def collection(name):
    return CollectionObservation(
        collection=name,
        document_id=uuid4(),
        document_version_id=uuid4(),
        filename="original.pdf",
        version_sequence=1,
        durable_status="READY",
        current_version=True,
    )


def test_qdrant_inspection_only_reads_supplied_durable_collection(monkeypatch):
    from citeweave import runtime_operations

    paths = []

    def respond(request):
        paths.append(request.url.path)
        if request.url.path == "/collections":
            return httpx.Response(
                200, json={"result": {"collections": [{"name": "owner"}, {"name": "other"}]}}
            )
        assert request.url.path == "/collections/owner"
        return httpx.Response(
            200, json={"result": {"status": "green", "points_count": 7, "indexed_vectors_count": 0}}
        )

    original = httpx.Client
    monkeypatch.setattr(
        runtime_operations.httpx,
        "Client",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(respond)),
    )
    rows = [collection("owner"), collection("missing")]
    value = observe_collections(SimpleNamespace(qdrant_url="http://local"), rows)
    assert value.status == "available"
    assert paths == ["/collections", "/collections/owner"]
    assert rows[0].observed and rows[0].points_count == 7 and rows[0].indexed_vectors_count == 0
    assert not rows[1].observed and rows[1].points_count is None


def test_failed_service_probe_never_exposes_upstream_body(monkeypatch):
    from citeweave import runtime_operations

    monkeypatch.setattr(
        runtime_operations.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            503, request=httpx.Request("GET", "http://local"), text="secret upstream error"
        ),
    )
    value = observe_model(SimpleNamespace(model_url="http://local"))
    assert value.status == "unavailable"
    assert "secret" not in value.model_dump_json()


def test_malformed_gateway_health_is_unavailable(monkeypatch):
    from citeweave import runtime_operations

    monkeypatch.setattr(
        runtime_operations.httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200, request=httpx.Request("GET", "http://local"), json=["unexpected"]
        ),
    )
    value = observe_model(SimpleNamespace(model_url="http://local"))
    assert value.status == "unavailable"


def test_worker_ping_connection_error_is_explicit_unavailable(monkeypatch):
    from kombu.exceptions import OperationalError

    from citeweave.celery_app import app
    from citeweave.runtime_operations import observe_workers

    def unavailable(*args, **kwargs):
        raise OperationalError("secret broker URL must not appear")

    monkeypatch.setattr(app.control, "inspect", unavailable)
    value, workers = observe_workers()
    assert value.status == "unavailable" and workers == []
    assert "secret" not in value.model_dump_json()


def test_operations_requires_authentication_before_observing(monkeypatch):
    from citeweave import runtime_operations

    def forbidden(*args):
        raise AssertionError("Unauthenticated callers must not probe services")

    monkeypatch.setattr(runtime_operations, "snapshot", forbidden)
    client = TestClient(create_app(admin_token="local-test-token-only-operations"))
    assert client.get("/v1/runtime/operations").status_code == 401
