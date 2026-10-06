"""Provider-free inspection API contract and execution separation."""

from fastapi.testclient import TestClient

from citeweave.api import create_app


def test_catalog_reads_never_prepare_or_execute_runtime(monkeypatch):
    from citeweave import runtime_inspection

    class ForbiddenRuntime:
        def prepare(self):
            raise AssertionError("Read must not prepare execution")

        def execute(self, *args):
            raise AssertionError("Read must not dispatch")

    seen = []
    monkeypatch.setattr(
        runtime_inspection, "list_runs", lambda workspace, limit, offset: seen.append((limit, offset)) or ()
    )
    token = "synthetic-inspection-public-contract-token"
    client = TestClient(create_app(token, conversation_runtime=ForbiddenRuntime()))
    assert client.get("/v1/runtime/conversation-runs").status_code == 401
    assert not seen
    assert (
        client.get(
            "/v1/runtime/conversation-runs?limit=2&offset=3", headers={"Authorization": "Bearer " + token}
        ).json()
        == []
    )
    assert seen == [(2, 3)]
    schema = client.app.openapi()
    assert set(schema["paths"]["/v1/runtime/conversation-runs"]) == {"get"}
    fields = schema["components"]["schemas"]["PublishedStateSummary"]["properties"]
    assert not {"prompt", "raw_provider", "authorization", "owner"} & fields.keys()
