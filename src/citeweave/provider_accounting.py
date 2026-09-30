"""Offline V4.1 text accounting, pinned to DeepSeek's official recipe.

Only system + user / non-thinking / no tools or response-format extensions.
Protocol source: deepseek-ai/deepseek-recipe, MIT, commit below, encoding/src/v4.
Counts are tokenizer-derived under that protocol, NOT provider-reported usage.
Special-token literals in content fail closed (official recipe issue #5).
"""

import hashlib
import json
from pathlib import Path

RECIPE_REVISION = "8cadfede7063c896b944e7bae05daa3549ae97ea"
TOKENIZER_SHA256 = "81f64d1248a68ce3663e07ab3ee48b851e5df0e32d27cb98e4c9a268151e8d99"
ACCOUNTING_REVISION = "deepseek-v41-text-pair-v1:" + RECIPE_REVISION


def serialize_request(body):
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def request_hash(body):
    return hashlib.sha256(serialize_request(body)).hexdigest()


def validate_request(body):
    if (
        set(body) != {"model", "messages", "thinking", "max_tokens", "stream", "stream_options"}
        or body["model"] != "deepseek-flash"
        or body["thinking"] != {"type": "disabled"}
        or body["stream"] is not True
        or body["stream_options"] != {"include_usage": True}
        or type(body["max_tokens"]) is not int
        or not 0 < body["max_tokens"] <= 384000
    ):
        raise ValueError("provider_accounting_request_unsupported")
    messages = body["messages"]
    if (
        not isinstance(messages, list)
        or len(messages) != 2
        or [m.get("role") for m in messages] != ["system", "user"]
        or any(set(m) != {"role", "content"} or not isinstance(m["content"], str) for m in messages)
    ):
        raise ValueError("provider_accounting_messages_unsupported")


class DeepSeekAccounting:
    identity = ACCOUNTING_REVISION

    def __init__(self, path: Path):
        from tokenizers import Tokenizer

        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != TOKENIZER_SHA256:
            raise ValueError("provider_tokenizer_identity_mismatch")
        self.tokenizer = Tokenizer.from_str(data.decode("utf-8"))
        self.reserved = tuple(t["content"] for t in json.loads(data)["added_tokens"])

    def measure(self, body):
        validate_request(body)
        system, user = [m["content"] for m in body["messages"]]
        if any(t in content for t in self.reserved for content in (system, user)):
            raise ValueError("provider_special_token_literal")
        # Official V4.1 render_conversation/render_message, restricted text pair.
        framed = (
            "<｜begin▁of▁sentence｜><｜System｜>" + system + "<｜User｜>" + user + "<｜Assistant｜></think>"
        )

        def count(value):
            return len(self.tokenizer.encode(value, add_special_tokens=False).ids)

        total = count(framed)
        components = {"system": count(system), "user": count(user)}
        if total + body["max_tokens"] > 1000000:
            raise ValueError("provider_context_overflow")
        return dict(
            identity=self.identity,
            tokenizer_sha256=TOKENIZER_SHA256,
            request_hash=request_hash(body),
            input_tokens=total,
            output_tokens=body["max_tokens"],
            components=components,
            framing_delta=total - sum(components.values()),
            kind="official_offline_tokenizer",
        )
