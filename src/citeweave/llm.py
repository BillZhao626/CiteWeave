"""Bounded provider attempts, durable circuit, cancellable stream and per-attempt accounting."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Protocol

import httpx

from citeweave.circuit import Circuit
from citeweave.costs import breakdown
from citeweave.reliability import CircuitOpen, error_category
from citeweave.settings import settings
from citeweave.trace import network_timeout, record_call


class ProviderError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class LLMProvider(Protocol):
    def stream(self, messages: list[dict]) -> AsyncIterator[dict]: ...


class DeepSeekProvider:
    def __init__(self, transport=None, circuit=None):
        self.transport = transport
        self.circuit = circuit or Circuit("deepseek")
        self.attempts = []
        self.max_attempts = None  # DurableProvider sets one actual send per ledger attempt.

    async def stream(self, messages):
        config = settings()
        attempts = self.max_attempts or config.provider_attempts
        key = config.deepseek_api_key.get_secret_value()
        if not key:
            raise ProviderError("llm_key_missing")
        try:
            permit = await asyncio.to_thread(self.circuit.change, "acquire")
        except CircuitOpen:
            raise ProviderError("circuit_open") from None
        body = dict(
            model=config.deepseek_model,
            messages=messages,
            thinking={"type": "disabled"},
            max_tokens=1024,
            stream=True,
            stream_options={"include_usage": True},
        )
        succeeded = False
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=httpx.Timeout(25, connect=5)
            ) as client:
                uncertain_retry = False
                for attempt in range(attempts):
                    start, when = time.perf_counter(), datetime.now(timezone.utc)
                    item = dict(
                        upstream="deepseek",
                        operation="completion",
                        attempt=attempt + 1,
                        started_at=when.isoformat(),
                        status="RUNNING",
                        usage=None,
                        estimated_yuan=None,
                        outcome="unknown",
                        actual_charge="unavailable",
                    )
                    started = False
                    try:
                        async with client.stream(
                            "POST",
                            "https://api.deepseek.com/chat/completions",
                            json=body,
                            timeout=httpx.Timeout(
                                await asyncio.to_thread(network_timeout, 25),
                                connect=min(5, await asyncio.to_thread(network_timeout, 25)),
                            ),
                            headers={"Authorization": "Bearer " + key},
                        ) as response:
                            item["http_status"] = response.status_code
                            if response.status_code != 200:
                                code = "llm_http_" + str(response.status_code)
                                item.update(
                                    status="FAILED",
                                    error_code=code,
                                    error_category=error_category(code),
                                    estimated_yuan=0 if response.status_code < 500 else None,
                                    outcome="rejected" if response.status_code < 500 else "unknown",
                                )
                                if (
                                    response.status_code in (429, 500, 502, 503, 504)
                                    and attempt + 1 < attempts
                                ):
                                    uncertain_retry |= response.status_code >= 500
                                    await asyncio.sleep(config.retry_backoff_seconds * (attempt + 1))
                                    continue
                                raise ProviderError(code)
                            finished = False
                            async for line in response.aiter_lines():
                                if not line.startswith("data:"):
                                    continue
                                raw = line[5:].strip()
                                if raw == "[DONE]":
                                    if not finished:
                                        raise ProviderError("llm_stream_incomplete")
                                    item.update(status="COMPLETED", outcome="complete")
                                    succeeded = True
                                    return
                                if len(raw) > 65536:
                                    raise ProviderError("llm_event_limit")
                                value = json.loads(raw)
                                if value.get("usage"):
                                    usage = {
                                        k: v
                                        for k, v in value["usage"].items()
                                        if k
                                        in (
                                            "prompt_tokens",
                                            "completion_tokens",
                                            "total_tokens",
                                            "prompt_cache_hit_tokens",
                                            "prompt_cache_miss_tokens",
                                        )
                                        and type(v) is int
                                        and v >= 0
                                    }
                                    item["usage"] = usage
                                    if cost := breakdown(usage, when):
                                        item.update(cost)
                                    yield dict(
                                        usage=usage,
                                        model=value.get("model"),
                                        provider_id=value.get("id"),
                                        uncertain_retry=uncertain_retry,
                                    )
                                for choice in value.get("choices", []):
                                    if choice.get("finish_reason"):
                                        if choice["finish_reason"] != "stop":
                                            raise ProviderError("llm_output_" + str(choice["finish_reason"]))
                                        finished = True
                                    content = choice.get("delta", {}).get("content")
                                    if content:
                                        if not isinstance(content, str):
                                            raise ProviderError("llm_protocol_error")
                                        started = True
                                        yield {"text": content}
                            raise ProviderError("llm_stream_incomplete")
                    except (httpx.ConnectError, httpx.ConnectTimeout):
                        item.update(
                            status="FAILED",
                            error_code="llm_connection_failed",
                            error_category="retryable",
                            estimated_yuan=0,
                            outcome="not_connected",
                        )
                        if attempt + 1 < attempts and not started:
                            await asyncio.sleep(config.retry_backoff_seconds * (attempt + 1))
                            continue
                        raise ProviderError("llm_connection_failed") from None
                    except httpx.TimeoutException:
                        item.update(error_code="llm_timeout", error_category="unknown_outcome")
                        raise ProviderError("llm_timeout") from None
                    except (httpx.HTTPError, ValueError, KeyError, TypeError):
                        item.update(error_code="llm_protocol_error", error_category="unknown_outcome")
                        raise ProviderError("llm_protocol_error") from None
                    except ProviderError as exc:
                        item.update(error_code=exc.code, error_category=error_category(exc.code))
                        raise
                    except (asyncio.CancelledError, GeneratorExit):
                        item.update(
                            status="CANCELLED", error_code="client_cancelled", error_category="cancelled"
                        )
                        raise
                    finally:
                        if item["status"] == "RUNNING":
                            item["status"] = "FAILED"
                        item.update(
                            content_started=started,
                            ended_at=datetime.now(timezone.utc).isoformat(),
                            latency_ms=round((time.perf_counter() - start) * 1000, 3),
                        )
                        self.attempts.append(item)
                        record_call(item)
        except ProviderError as exc:
            action = "failure" if error_category(exc.code) in {"retryable", "unknown_outcome"} else "success"
            await asyncio.to_thread(self.circuit.change, action, permit)
            raise
        finally:
            await asyncio.shield(
                asyncio.to_thread(self.circuit.change, "success" if succeeded else "abandon", permit)
            )
