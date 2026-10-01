"""Finite evaluation-only request/output contracts; production DTOs unchanged."""

import hashlib
import json

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationDraft
from citeweave.evaluation.dev_paid_readiness import build_readiness
from citeweave.llm import completion_payload


def reserves(root, accounting):
    packet = build_readiness(root, accounting)
    interpretation = [s for s in packet["specimens"] if s["purpose"] == "interpretation"]
    generation = [s for s in packet["specimens"] if s["purpose"] == "generation"]
    # One-byte-per-token worst segmentation of the COMPLETE indented reference
    # JSON, including defaults. This is a finite safety policy, not a promise of
    # completeness for every permissible model answer. No arbitrary multiplier.
    oi = max(
        len(json.dumps(json.loads(s["reference_output"]), ensure_ascii=False, indent=2).encode())
        for s in interpretation
    )
    # Existing accepted answer guard is 8192 Unicode codepoints, including
    # citation labels. UTF8 needs at most four bytes/codepoint; ByteLevel can
    # spend at most one ordinary token/byte. Covers the whole guard, while the
    # frozen concise references justify no larger reserve or extra repair call.
    og = 8192 * 4
    return dict(
        interpretation=oi,
        generation=og,
        rationale="I: complete-reference UTF8 singleton segmentation, indent=2; G: 8192 codepoints*4 bytes",
        observed_interpretation_max=max(s["reference_output_tokens"] for s in interpretation),
        observed_generation_max=max(s["reference_output_tokens"] for s in generation),
    )


def tokenizer_certificate(path, accounting):
    value = json.loads(path.read_bytes())
    if value["model"]["type"] != "BPE" or value["decoder"]["type"] != "ByteLevel":
        raise ValueError("dev_byte_tokenizer_proof_unsupported")
    if value["normalizer"] != {"type": "Sequence", "normalizers": []}:
        raise ValueError("dev_byte_tokenizer_normalization_unsupported")
    if value["pre_tokenizer"]["pretokenizers"][-1] != {
        "type": "ByteLevel",
        "add_prefix_space": False,
        "trim_offsets": True,
        "use_regex": False,
    }:
        raise ValueError("dev_byte_tokenizer_prefix_unsupported")
    vocabulary = accounting.tokenizer.get_vocab()
    max_decoded_bytes = max(
        len(accounting.tokenizer.decode([i], skip_special_tokens=False).encode())
        for token, i in vocabulary.items()
        if token not in accounting.reserved
    )
    # Official ByteLevel vocabulary merges only concatenate initial byte units.
    # Decoding adjoining tokens cannot increase replacement-UTF8 bytes above
    # separately decoded units; special literals are rejected independently.
    return dict(
        max_decoded_utf8_bytes_per_output_token=max_decoded_bytes,
        vocabulary_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        input_tokens_per_utf8_byte_upper_bound=1,
        framing_tokens=5,
    )


def request_contract(purpose, messages, input_cap, output_cap, accounting):
    body = completion_payload(messages, "deepseek-flash", output_cap)
    measurement = accounting.measure(body)
    if measurement["input_tokens"] > input_cap:
        raise CoreConflict("dev_request_bound_exceeded")
    return body, measurement


def decode_output(purpose, raw, *, finish_reason, reserve, accounting):
    if finish_reason != "stop":
        raise CoreConflict("dev_output_truncated_or_incomplete")
    if any(t in raw for t in accounting.reserved):
        raise CoreConflict("dev_output_special_token")
    if len(accounting.tokenizer.encode(raw, add_special_tokens=False).ids) > reserve:
        raise CoreConflict("dev_output_reserve_exceeded")
    if purpose == "interpretation":
        try:
            return InterpretationDraft.model_validate_json(raw)
        except ValueError as exc:
            raise CoreConflict("dev_interpretation_invalid_json_or_schema") from exc
    if not 0 < len(raw) <= 8192:
        raise CoreConflict("dev_answer_length_invalid")
    return raw


def generation_input_bound(context, prompt, oi, certificate):
    """Certified cap for every dispatchable future validated interpretation.

    NOT a sum of independently tokenized strings. Bound the complete serializer's
    UTF8 bytes, then prove ByteLevel count <= bytes+five special framing tokens.
    Every actual body is subsequently serialized/tokenized at prepare AND dispatch.
    """
    from types import SimpleNamespace

    from citeweave.conversation_evidence import IntentHistory
    from citeweave.conversation_runtime import generation_messages

    history = tuple(
        IntentHistory(source=s.ref, original_question=s.request.question, relations=s.relations)
        for g in context.history.selected
        for s in g.sources
    )
    state = context.history.state_projection
    # All documentary bytes are frozen original ASCII. Pack requires <=6400
    # serialized chars. No E5/BGE token count is used for this provider bound.
    strings = [
        context.request.question,
        *(h.original_question for h in history),
        *(s.item.value for s in state),
    ]
    if any(not s.isascii() for s in strings):
        raise ValueError("dev_frozen_ascii_bound_inapplicable")
    empty = SimpleNamespace(
        original_question=context.request.question,
        retrieval_query="",
        interpretation=SimpleNamespace(mode="USE_ORIGINAL", topic_relation="continue", facts=[]),
        history=history,
        working_state=state,
        evidence=SimpleNamespace(pack=SimpleNamespace(prompt_json="")),
    )
    body = completion_payload(generation_messages(empty, prompt), "deepseek-flash", 1)
    fixed_bytes = sum(len(m["content"].encode()) for m in body["messages"])
    # Every validated fact value is a current ASCII substring, selected signal,
    # or a frozen State value; UUIDs/enums are ASCII. Compact serialization adds
    # at most 35 bytes of omitted nullable defaults to a >=51-byte input fact.
    # Facts from references/ambiguities are already paid raw JSON bytes, deduped.
    # Thus serialized unique facts <= 2*complete interpretation response bytes.
    facts_bound = 2 * oi * certificate["max_decoded_utf8_bytes_per_output_token"]
    # Structural retrieval hard query guard is 512 Unicode codepoints; admitted
    # intent only uses frozen ASCII values. Escape bound six bytes per character
    # includes quotes, slash and control chars; pack is already exact JSON text.
    query_bound = 512 * 6
    pack_bound = 6400  # All seven frozen corpus strings/UUID filenames are ASCII.
    byte_cap = fixed_bytes + facts_bound + query_bound + pack_bound
    return dict(
        input_tokens=byte_cap + 5,
        fixed_serialized_utf8_bytes=fixed_bytes,
        interpretation_insertion_bytes=facts_bound,
        escaped_query_bytes=query_bound,
        current_evidence_pack_bytes=pack_bound,
        proof="full serialized UTF8 upper envelope; pinned ByteLevel tokens<=bytes+5",
        exact_future_request_known=False,
    )


def no_interpretation(view):
    # Fixed reviewed self-contained views only; no heuristic/model skip decision.
    return view.id in {"D2.V1", "D2.V2", "D6.V1", "D6.V2"}


def slots_for_view(view, arm):
    # An absent phase has no budget: even an unexpected runtime branch cannot
    # dispatch it. The correction group guard remains separately verified.
    if view.id == "D3.V2" and arm == "cp-a-v1":
        return ()
    return ("generation",) if no_interpretation(view) else ("interpretation", "generation")
