"""Bounded authenticated model adapter; no model tensors in API or Celery processes."""

import math
import time
from datetime import datetime, timezone
from typing import Protocol

import httpx

from citeweave.circuit import Circuit
from citeweave.embeddings import embedding_identity
from citeweave.reliability import CircuitOpen, error_category
from citeweave.settings import settings
from citeweave.trace import current_trace, record_call


class Embedder(Protocol):
    def embed(self, texts: list[str], query: bool = False) -> list[list[float]]: ...


class Reranker(Protocol):
    def rerank(self, question: str, texts: list[str]) -> list[float]: ...


class GatewayError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ModelGateway:
    def __init__(self, transport=None, circuit=None, embedding_key="e5-small"):
        self.transport, self.circuit = transport, circuit or Circuit("model_gateway")
        self.embedding = embedding_identity(embedding_key)

    def call(self, route, body):
        config = settings()
        try:
            permit = self.circuit.change("acquire")
        except CircuitOpen:
            raise GatewayError("circuit_open") from None
        succeeded = False
        try:
            with httpx.Client(
                transport=self.transport, timeout=httpx.Timeout(15, connect=3), trust_env=False
            ) as client:
                for attempt in range(config.model_attempts):
                    if (trace := current_trace.get()) and trace.cancelled.is_set():
                        raise GatewayError("client_cancelled")
                    start = time.perf_counter()
                    item = dict(
                        upstream="model_gateway",
                        operation=route,
                        attempt=attempt + 1,
                        started_at=datetime.now(timezone.utc).isoformat(),
                        status="FAILED",
                        estimated_yuan=0,
                    )
                    try:
                        response = client.post(
                            config.model_url + route,
                            json=body,
                            headers={"Authorization": "Bearer " + config.gateway_token()},
                        )
                        item["http_status"] = response.status_code
                        if response.status_code == 200:
                            result = response.json()
                            succeeded = True
                            item["status"] = "COMPLETED"
                            return result
                        code = "model_http_" + str(response.status_code)
                        if response.status_code == 422:
                            supplied = response.json().get("error")
                            if supplied in {
                                "embedding_token_limit",
                                "reranker_token_limit",
                                "text_limit_20_by_160",
                                "question_limit",
                                "embedding_identity_mismatch",
                            }:
                                code = supplied
                        if error_category(code) == "non_retryable":
                            self.circuit.change("success", permit)
                            raise ValueError(code)
                        raise GatewayError(code)
                    except (httpx.ConnectError, httpx.ConnectTimeout):
                        item["error_code"] = "model_connection_failed"
                    except httpx.TimeoutException:
                        item["error_code"] = "model_timeout"
                    except GatewayError as exc:
                        item["error_code"] = exc.code
                    except ValueError as exc:
                        item["error_code"] = (
                            str(exc) if str(exc).replace("_", "").isalnum() else "model_protocol_error"
                        )
                        raise ValueError(item["error_code"]) from None
                    except httpx.HTTPError:
                        item["error_code"] = "model_connection_failed"
                    finally:
                        if item.get("error_code"):
                            item["error_category"] = error_category(item["error_code"])
                        item.update(
                            ended_at=datetime.now(timezone.utc).isoformat(),
                            latency_ms=(time.perf_counter() - start) * 1000,
                        )
                        record_call(item)
                    if attempt + 1 == config.model_attempts:
                        raise GatewayError(item["error_code"])
                    if trace:
                        if trace.cancelled.wait(config.retry_backoff_seconds * (attempt + 1)):
                            raise GatewayError("client_cancelled")
                    else:
                        time.sleep(config.retry_backoff_seconds * (attempt + 1))
        except GatewayError as exc:
            self.circuit.change("abandon" if exc.code == "client_cancelled" else "failure", permit)
            raise
        finally:
            self.circuit.change("success" if succeeded else "abandon", permit)

    def embed(self, texts, query=False):
        response = self.call("/embed", {"texts": texts, "query": query, "embedding": self.embedding})
        if response.get("embedding") != self.embedding:
            raise ValueError("embedding_identity_mismatch")
        vectors = response["vectors"]
        if len(vectors) != len(texts) or any(
            len(v) != self.embedding["dimension"] or any(not math.isfinite(x) for x in v) for v in vectors
        ):
            raise ValueError("model_dimension_mismatch")
        return vectors

    def rerank(self, question, texts):
        scores = self.call("/rerank", {"question": question, "texts": texts})["scores"]
        if len(scores) != len(texts) or any(not math.isfinite(x) for x in scores):
            raise ValueError("reranker_count_mismatch")
        return scores
