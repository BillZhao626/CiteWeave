"""Actual stream protocol through a mock HTTP transport; no network or grant."""

import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from citeweave import llm
from citeweave.conversation_provider import Observation
from citeweave.settings import Settings


def test_stream_keys_reproduce_old_dev_observation_incompatibility(monkeypatch):
    config = Settings(deepseek_api_key=SecretStr("synthetic-not-a-credential"))
    monkeypatch.setattr(llm, "settings", lambda: config)

    class Circuit:
        def change(self, *args):
            return 0

    usage = dict(prompt_tokens=10, completion_tokens=2, total_tokens=12)
    events = [
        dict(id="synthetic-response-id", choices=[dict(delta=dict(content="answer"))]),
        dict(choices=[dict(delta={}, finish_reason="stop")]),
        dict(id="synthetic-response-id", model="served-alias", usage=usage, choices=[]),
    ]
    body = "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
    sends = []

    def respond(request):
        sends.append(request)
        return httpx.Response(200, text=body)

    provider = llm.DeepSeekProvider(httpx.MockTransport(respond), Circuit())
    provider.max_attempts = 1
    request = llm.completion_payload(
        [dict(role="system", content="synthetic"), dict(role="user", content="question")],
        "deepseek-flash",
        100,
    )
    boundaries = []

    async def collect():
        return [
            part async for part in provider.stream_request(request, before_send=lambda: boundaries.append(1))
        ]

    parts = asyncio.run(collect())
    assert len(sends) == len(boundaries) == len(provider.attempts) == 1
    assert {k for p in parts for k in p} == {"provider_id", "text", "usage", "model", "uncertain_retry"}
    assert "".join(p.get("text", "") for p in parts) == "answer"
    old = {}
    for part in parts:
        for key in ("usage", "model", "provider_id"):
            if part.get(key) is not None:
                old[key if key != "model" else "observed_model"] = part[key]
    with pytest.raises(ValidationError) as error:
        Observation.model_validate(old)
    assert {(e["loc"][0], e["type"]) for e in error.value.errors()} == {
        ("provider_id", "extra_forbidden"),
        ("observed_model", "extra_forbidden"),
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"provider_id": "not translated"},
        {"observed_model": "not a receipt field"},
        {"request_id": ""},
        {"request_id": "x" * 201},
        {"usage": {"prompt_tokens": -1}},
        {"usage": {"completion_tokens": "1"}},
        {"usage": {"unsupported": 1}},
        {"result_hash": "invalid"},
    ],
)
def test_shared_observation_still_rejects_unsupported_or_malformed_receipts(payload):
    with pytest.raises(ValidationError):
        Observation.model_validate(payload)
