import asyncio
import os
from types import SimpleNamespace

import httpx
import pytest
from test_eval_recovery import cleanup_cases as cleanup_cases
from test_eval_recovery import get, make_case, query, start

from citeweave import llm
from citeweave.provider_phases import DurableProvider

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("CW_RUN_INTEGRATION"), reason="isolated PG required"),
]


class Circuit:
    def change(self, *args):
        return "permit"


@pytest.mark.parametrize("status", [500, 429])
def test_actual_http_send_is_single_despite_legacy_retry_setting(monkeypatch, status):
    identity, _ = make_case()
    token = start(identity)
    q = query(token)
    config = SimpleNamespace(
        deepseek_api_key=SimpleNamespace(get_secret_value=lambda: "original-test-key"),
        deepseek_model="deepseek-flash",
        provider_attempts=3,
        retry_backoff_seconds=0,
    )
    monkeypatch.setattr(llm, "settings", lambda: config)
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"original_fixture": True})

    provider = llm.DeepSeekProvider(transport=httpx.MockTransport(handle), circuit=Circuit())
    wrapped = DurableProvider(provider, q.id, q.owner, q.fence, token=token)

    async def consume():
        return [p async for p in wrapped.stream([])]

    with pytest.raises(llm.ProviderError):
        asyncio.run(consume())
    assert len(calls) == 1 and provider.max_attempts == 1
    if status == 500:
        with pytest.raises(ValueError, match="unknown"):
            asyncio.run(consume())
        assert len(calls) == 1
    else:
        with pytest.raises(llm.ProviderError):
            asyncio.run(consume())
        with pytest.raises(ValueError, match="attempts_exhausted"):
            asyncio.run(consume())
        assert len(calls) == 2
    assert get(identity).execution_attempt == 1
