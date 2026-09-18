"""Pure resident-gateway protocol; no application or model imports."""

import math

from citeweave.tokenization import TOKENIZERS

QUERY_CONTRACT = "structural-query-v1"
PROXY = "context-bge-token-proxy-v1"


def query_counts(question, e5, bge):
    if not isinstance(question, str) or not 0 < len(question) <= 512:
        raise ValueError("question_limit")
    counts = {
        "e5_input": len(e5("query: " + question, truncation=False)["input_ids"]),
        "bge_query": len(bge(question, add_special_tokens=False, truncation=False)["input_ids"]),
    }
    validate_query_counts(counts)
    return counts


def validate_query_counts(counts):
    if any(
        type(counts.get(k)) is not int or not 0 < counts[k] <= cap
        for k, cap in (("e5_input", 256), ("bge_query", 128))
    ):
        raise ValueError("query_token_limit")


def pair_counts(question, texts, e5, bge):
    counts = query_counts(question, e5, bge)
    if (
        not isinstance(texts, list)
        or not 0 < len(texts) <= 20
        or any(not isinstance(t, str) or not 0 < len(t) <= 1600 for t in texts)
    ):
        raise ValueError("structural_text_limit")
    counts["body_tokens"] = [
        len(bge(t, add_special_tokens=False, truncation=False)["input_ids"]) for t in texts
    ]
    counts["pair_tokens"] = [len(bge(question, t, truncation=False)["input_ids"]) for t in texts]
    if any(n > 320 for n in counts["body_tokens"]) or any(n > 512 for n in counts["pair_tokens"]):
        raise ValueError("reranker_token_limit")
    return counts


def validate_rerank(response, count):
    if (
        not isinstance(response, dict)
        or response.get("contract") != QUERY_CONTRACT
        or response.get("tokenizers") != TOKENIZERS
    ):
        raise ValueError("reranker_identity_mismatch")
    try:
        validate_query_counts(response)
        for key, cap in (("body_tokens", 320), ("pair_tokens", 512)):
            values = response[key]
            if len(values) != count or any(type(v) is not int or not 0 < v <= cap for v in values):
                raise ValueError("reranker_token_accounting")
        for body, pair in zip(response["body_tokens"], response["pair_tokens"], strict=True):
            if not body + response["bge_query"] <= pair <= body + response["bge_query"] + 8:
                raise ValueError("reranker_token_accounting")
        if len(response["scores"]) != count:
            raise ValueError("reranker_count_mismatch")
        for value in [*response["scores"], response["queue_ms"], response["inference_ms"]]:
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError("reranker_invalid_score")
        if min(response["queue_ms"], response["inference_ms"]) < 0:
            raise ValueError("reranker_protocol_error")
    except (KeyError, TypeError):
        raise ValueError("reranker_protocol_error") from None
    return response
