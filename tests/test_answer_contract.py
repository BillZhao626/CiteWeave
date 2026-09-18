import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from citeweave.answering import REFUSAL, estimated_cost, validate_citations
from citeweave.catalog import fingerprint
from citeweave.llm import DeepSeekProvider, ProviderError


@pytest.fixture(autouse=True)
def isolated_circuit(monkeypatch):
    from citeweave import llm

    monkeypatch.setattr(llm, "Circuit", lambda name: SimpleNamespace(change=lambda *args: 0))


def test_citation_formatter_rejects_invented_missing_and_accepts_refusal():
    citation = SimpleNamespace(label="E1")
    assert validate_citations("结论 [E1]。重复 [E1]", [citation]) == [citation]
    for answer in ("无引用的结论", "结论 [E2]", "结论 [E1] 和 [fake]"):
        with pytest.raises(ValueError):
            validate_citations(answer, [citation])
    assert validate_citations(REFUSAL, [citation]) == []
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})


def test_conservative_ratecard_and_unknown_usage():
    usage = {"prompt_tokens": 1000, "completion_tokens": 100, "prompt_cache_hit_tokens": 500}
    peak = datetime(2026, 9, 14, 2, tzinfo=timezone.utc)
    offpeak = datetime(2026, 9, 13, 2, tzinfo=timezone.utc)
    assert float(estimated_cost(usage, peak)) == pytest.approx(0.00182)
    assert estimated_cost(usage, offpeak) * 2 == estimated_cost(usage, peak)
    assert estimated_cost(None) is None
    assert estimated_cost(dict(usage, uncertain_retry=True), peak) is None


def test_provider_retries_http_only_before_content_and_records_usage(monkeypatch):
    from pydantic import SecretStr

    from citeweave import llm

    monkeypatch.setattr(
        llm,
        "settings",
        lambda: SimpleNamespace(
            deepseek_api_key=SecretStr("test"),
            deepseek_model="test",
            provider_attempts=2,
            retry_backoff_seconds=0,
        ),
    )
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(503)
        lines = [
            json.dumps({"choices": [{"delta": {"content": "答案 [E1]"}, "finish_reason": None}]}),
            json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
            json.dumps({"choices": [], "usage": {"prompt_tokens": 20, "completion_tokens": 4}}),
            "[DONE]",
        ]
        return httpx.Response(200, text="".join("data: " + s + "\n\n" for s in lines))

    async def collect():
        return [p async for p in DeepSeekProvider(httpx.MockTransport(handler)).stream([])]

    result = asyncio.run(collect())
    assert len(calls) == 2 and calls[0]["thinking"]["type"] == "disabled"
    assert result[0]["text"] == "答案 [E1]" and result[1]["usage"]["completion_tokens"] == 4
    assert result[1]["uncertain_retry"] is True


def test_truncated_stream_is_failure_no_retry(monkeypatch):
    from pydantic import SecretStr

    from citeweave import llm

    monkeypatch.setattr(
        llm,
        "settings",
        lambda: SimpleNamespace(
            deepseek_api_key=SecretStr("test"),
            deepseek_model="test",
            provider_attempts=2,
            retry_backoff_seconds=0,
        ),
    )
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n')

    async def collect():
        return [p async for p in DeepSeekProvider(httpx.MockTransport(handler)).stream([])]

    with pytest.raises(ProviderError, match="llm_stream_incomplete"):
        asyncio.run(collect())
    assert len(calls) == 1
