"""Versioned tokenizer-only gateway contract, with codepoint-offset validation."""

import json

from citeweave.embeddings import E5

CONTRACT = "structural-tokenization-v1"
TOKENIZERS = {
    "e5": {"model": E5["model"], "revision": E5["revision"]},
    "bge": {"model": "BAAI/bge-reranker-v2-m3", "revision": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"},
}


def validate_texts(texts):
    if (
        not isinstance(texts, list)
        or not 1 <= len(texts) <= 20
        or any(not isinstance(t, str) or not 1 <= len(t) <= 16384 for t in texts)
    ):
        raise ValueError("tokenization_text_limit")


def tokenize_response(texts, e5, bge):
    """Called only by the resident gateway (or original test tokenizer fixtures)."""
    validate_texts(texts)
    rows = []
    for text in texts:
        row = {}
        for name, tokenizer in (("e5", e5), ("bge", bge)):
            encoded = tokenizer(text, add_special_tokens=False, truncation=False, return_offsets_mapping=True)
            row[name] = len(encoded["input_ids"])
            row[name + "_offsets"] = [list(pair) for pair in encoded["offset_mapping"]]
        row["e5_input"] = len(e5("passage: " + text, truncation=False)["input_ids"])
        row["bge_pair_special"] = bge.num_special_tokens_to_add(pair=True)
        rows.append(row)
    return {"contract": CONTRACT, "tokenizers": TOKENIZERS, "rows": rows}


def validate_response(texts, response):
    if response.get("contract") != CONTRACT or response.get("tokenizers") != TOKENIZERS:
        raise ValueError("tokenizer_identity_mismatch")
    rows = response.get("rows", [])
    if len(rows) != len(texts):
        raise ValueError("tokenizer_count_mismatch")
    for text, row in zip(texts, rows, strict=True):
        for name in ("e5", "bge"):
            offsets = row.get(name + "_offsets", [])
            if type(row.get(name)) is not int or row[name] != len(offsets):
                raise ValueError("tokenizer_count_mismatch")
            last_start = 0
            for pair in offsets:
                if len(pair) != 2 or any(type(x) is not int for x in pair):
                    raise ValueError("tokenizer_offset_mismatch")
                start, end = pair
                if not last_start <= start < end <= len(text):
                    raise ValueError("tokenizer_offset_mismatch")
                last_start = start
        if type(row.get("e5_input")) is not int or row["e5_input"] < row["e5"]:
            raise ValueError("tokenizer_count_mismatch")
        if type(row.get("bge_pair_special")) is not int or not 0 < row["bge_pair_special"] <= 8:
            raise ValueError("tokenizer_pair_contract_mismatch")
    return rows


class GatewayTokenizer:
    identity = TOKENIZERS

    def __init__(self, gateway=None):
        from citeweave.model_client import ModelGateway

        self.gateway = gateway or ModelGateway()

    def count(self, texts):
        validate_texts(texts)
        result, batch = [], []

        def flush():
            if batch:
                result.extend(
                    validate_response(
                        batch, self.gateway.call("/tokenize", {"contract": CONTRACT, "texts": batch})
                    )
                )
                batch.clear()

        for text in texts:
            proposed = {"contract": CONTRACT, "texts": [*batch, text]}
            if batch and len(json.dumps(proposed, ensure_ascii=False).encode()) > 128 * 1024:
                flush()
            batch.append(text)
        flush()
        return result


def fits(text, counts, atoms=1):
    return (
        all(
            type(counts.get(k)) is int and counts[k] >= 0
            for k in ("e5", "e5_input", "bge", "bge_pair_special")
        )
        and 0 < counts["bge_pair_special"] <= 8
        and counts["e5_input"] >= counts["e5"]
        and atoms <= 24
        and len(text) <= 960
        and counts["e5"] <= 192
        and counts["e5_input"] <= 256
        and counts["bge"] <= 320
        and counts["bge"] + 128 + counts["bge_pair_special"] <= 512
    )
