"""Public allowlists and fail-closed HTTP contracts; no services/models."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from citeweave.api import create_app
from citeweave.conversation_contract import CoreConflict

TOKEN = "synthetic-public-api-token-not-a-secret"


def client(workspace=None, runtime=None):
    return TestClient(
        create_app(TOKEN, workspace or uuid4(), conversation_runtime=runtime),
        headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "operation"},
    )


def test_public_routes_require_authentication():
    app = TestClient(create_app(TOKEN))
    root = f"/v1/conversations/{uuid4()}"
    for path in (root, root + f"/runs/{uuid4()}", root + f"/runs/{uuid4()}/trace"):
        assert app.get(path).status_code == 401


def test_public_contract_excludes_execution_and_private_payloads():
    schema = client().app.openapi()
    assert "/v1/conversations/{conversation_id}/turns" in schema["paths"]
    definitions = schema["components"]["schemas"]
    assert set(definitions["TurnSubmit"]["properties"]) == {"question", "scope", "expected_head"}
    assert definitions["ConversationTrace"]["additionalProperties"] is False
    assert not {"owner", "fence", "prompt", "usage", "raw_provider", "reasoning"} & set(
        definitions["ConversationTrace"]["properties"]
    )
    assert "workspace_id" in definitions["Scope"]["properties"]  # Existing evidence Scope is stable.
    assert "202" in schema["paths"]["/v1/conversations/{conversation_id}/turns"]["post"]["responses"]
    assert "ConversationEvent" in definitions


@pytest.mark.parametrize("code", ["head_conflict", "idempotency_conflict", "conversation_busy"])
def test_core_conflicts_use_existing_error_envelope(monkeypatch, code):
    from citeweave import conversations

    def fail(*args):
        raise CoreConflict(code)

    monkeypatch.setattr(conversations, "create", fail)
    response = client().post("/v1/conversations")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize("field", ["owner", "deadline", "profile", "workspace_id", "permit"])
def test_client_cannot_supply_execution_authority(field):
    response = client().post(
        f"/v1/conversations/{uuid4()}/turns",
        json={
            "question": "Original question",
            "scope": {"kb_id": str(uuid4()), "version_ids": [str(uuid4())]},
            "expected_head": None,
            field: "forged",
        },
    )
    assert response.status_code == 422
