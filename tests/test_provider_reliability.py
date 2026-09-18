import asyncio

import httpx
import pytest
from pydantic import SecretStr

from citeweave import llm, model_client
from citeweave.settings import Settings


class CircuitStub:
    def __init__(self):
        self.actions = []

    def change(self, action, permit=None):
        self.actions.append(action)
        return 0


@pytest.fixture
def config(monkeypatch):
    value = Settings(deepseek_api_key=SecretStr("test"), retry_backoff_seconds=0)
    monkeypatch.setattr(llm, "settings", lambda: value)
    monkeypatch.setattr(model_client, "settings", lambda: value)
    return value


@pytest.mark.parametrize("status,count", [(429, 2), (503, 2), (401, 1), (400, 1)])
def test_retry_limits_and_failed_attempt_cost(config, status, count):
    calls, circuit = [], CircuitStub()

    def handler(request):
        calls.append(1)
        return httpx.Response(status)

    provider = llm.DeepSeekProvider(httpx.MockTransport(handler), circuit)

    async def collect():
        return [p async for p in provider.stream([])]

    with pytest.raises(llm.ProviderError, match=f"llm_http_{status}"):
        asyncio.run(collect())
    assert len(calls) == len(provider.attempts) == count
    assert all(a["estimated_yuan"] == (None if status >= 500 else 0) for a in provider.attempts)
    assert ("failure" in circuit.actions) == (status in (429, 503))


@pytest.mark.parametrize(
    "exception,count,code",
    [(httpx.ConnectTimeout, 2, "llm_connection_failed"), (httpx.ReadTimeout, 1, "llm_timeout")],
)
def test_connection_retry_vs_unknown_read_outcome(config, exception, count, code):
    def handler(request):
        raise exception("private upstream message must not escape")

    provider = llm.DeepSeekProvider(httpx.MockTransport(handler), CircuitStub())

    async def collect():
        return [p async for p in provider.stream([])]

    with pytest.raises(llm.ProviderError, match=code):
        asyncio.run(collect())
    assert len(provider.attempts) == count
    assert "private upstream" not in str(provider.attempts)


def test_client_cancellation_closes_upstream_no_retry_and_retains_usage(config):
    async def scenario():
        waiting, closed = asyncio.Event(), asyncio.Event()

        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":1}}\n\n'
                waiting.set()
                await asyncio.Event().wait()

            async def aclose(self):
                closed.set()

        provider = llm.DeepSeekProvider(
            httpx.MockTransport(lambda req: httpx.Response(200, stream=Body())), CircuitStub()
        )

        async def consume():
            return [p async for p in provider.stream([])]

        task = asyncio.create_task(consume())
        await asyncio.wait_for(waiting.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed.is_set()
        assert len(provider.attempts) == 1
        assert provider.attempts[0]["status"] == "CANCELLED"
        assert provider.attempts[0]["usage"]["completion_tokens"] == 1

    asyncio.run(scenario())


def test_model_gateway_retries_capacity_and_rejects_nonfinite_output(config):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, json={"scores": [1.2]})

    client = model_client.ModelGateway(httpx.MockTransport(handler), CircuitStub())
    assert client.rerank("question", ["text"]) == [1.2]
    assert len(calls) == 2
    bad = model_client.ModelGateway(
        httpx.MockTransport(lambda req: httpx.Response(200, text='{"scores":[NaN]}')), CircuitStub()
    )
    with pytest.raises(ValueError):
        bad.rerank("question", ["text"])
