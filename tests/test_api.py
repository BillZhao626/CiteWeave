import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from citeweave.api import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_DATABASE_URL"), reason="needs M0 DB"),
]
TOKEN = "test-only-not-a-real-credential-123456"


def test_kb_auth_idempotency_scope_and_durability():
    workspace = uuid4()
    headers = {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": "test-key"}
    with TestClient(create_app(TOKEN, workspace)) as client:
        assert client.get("/health/ready").status_code == 200
        assert client.get("/v1/knowledge-bases").status_code == 401
        created = client.post("/v1/knowledge-bases", headers=headers, json={"name": "原创实验库"})
        assert created.status_code == 201
        identity = created.json()["id"]
        replay = client.post("/v1/knowledge-bases", headers=headers, json={"name": "原创实验库"})
        assert replay.status_code == 200 and replay.json()["id"] == identity
        conflict = client.post("/v1/knowledge-bases", headers=headers, json={"name": "别的内容"})
        assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"
        forged = client.post(
            "/v1/knowledge-bases", headers=headers, json={"name": "越权", "workspace_id": str(uuid4())}
        )
        assert forged.status_code == 422
    # New app instance, same DB: metadata survives process lifecycle.
    with TestClient(create_app(TOKEN, workspace)) as fresh:
        assert fresh.get("/v1/knowledge-bases", headers=headers).json()[0]["id"] == identity
    with TestClient(create_app(TOKEN, uuid4())) as other:
        assert other.get("/v1/knowledge-bases", headers=headers).json() == []


def test_lab_unknown_citation_and_path_rejected(tmp_path):
    import json

    from citeweave.evidence import Block, Scope, bind_span, digest

    # Build original local evidence instead of depending on ignored M0 runtime artifacts.
    with TestClient(create_app(TOKEN, uuid4(), tmp_path)) as client:
        assert client.get("/lab/fixtures").status_code == 503
        scope = Scope(workspace_id=uuid4(), kb_id=uuid4(), revision_id=uuid4())
        block = Block(
            scope=scope,
            source_sha256=digest("original lab fixture"),
            block_id="lab-original",
            text="原创证据定位测试。",
        )
        span = bind_span(block, 2, 6, block.text[2:6])
        folder = tmp_path / ".artifacts/p01"
        folder.mkdir(parents=True)
        (folder / "fixtures.json").write_text(
            json.dumps([dict(blocks=[block.model_dump(mode="json")], spans=[span.model_dump(mode="json")])]),
            encoding="utf-8",
        )
        assert client.get(f"/lab/evidence/{uuid4()}").status_code == 404
        assert client.get("/lab/pages/8").status_code == 404
        fixtures = client.get("/lab/fixtures").json()
        identity = fixtures[0]["spans"][0]["id"]
        resolved = client.get(f"/lab/evidence/{identity}").json()
        assert resolved["span"]["quote"] == fixtures[0]["spans"][0]["quote"]
