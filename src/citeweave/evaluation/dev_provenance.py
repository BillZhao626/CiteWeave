"""DEV-only alpha-equivalence and certified UUID replacement envelope.

Never rewrites a provider body. Scope/document/citation IDs are never variable.
"""

import copy
import json
import re
import string
from uuid import UUID

from citeweave.conversation_contract import CoreConflict
from citeweave.evaluation.dev_dataset import digest
from citeweave.provider_accounting import TOKENIZER_SHA256, validate_request

REVISION = "dev-campaign-provenance-v1"
# Exact JSON value paths; * means one array index, not a recursive wildcard.
REFS = ("acceptance_id", "turn_id")
ALLOWLIST = {
    **{f"history.*.source.{k}": k for k in REFS},
    **{f"history.*.relations.*.target.{k}": k for k in REFS},
    "history.*.relations.*.state_item_ids.*": "state_id",
    "working_state.*.item.id": "state_id",
    "working_state.*.item.replaces.*": "state_id",
    **{f"working_state.*.{r}.{k}": k for r in ("introduced_by", "changed_by") for k in REFS},
    **{f"interpretation.facts.*.source.{k}": k for k in REFS},
    "interpretation.facts.*.state_item_id": "state_id",
}
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")


def user_value(body, purpose):
    validate_request(body)
    raw = body["messages"][1]["content"]
    head, sep, pack = raw.partition("\n") if purpose == "generation" else (raw, "", "")
    value = json.loads(head)
    if not isinstance(value, dict) or json.dumps(value, ensure_ascii=False, separators=(",", ":")) != head:
        raise CoreConflict("dev_semantic_serialization_unsupported")
    return value, head, sep + pack


def fields(value):
    """Walk values only: no normalization of schema/property names or arbitrary UUIDs."""
    found = []

    def visit(v, path):
        pattern = ".".join("*" if isinstance(k, int) else k for k in path)
        if pattern in ALLOWLIST and v is not None:
            if not isinstance(v, str) or not UUID_PATTERN.fullmatch(v) or str(UUID(v)) != v:
                raise CoreConflict("dev_semantic_provenance_not_canonical_uuid")
            found.append((path, ALLOWLIST[pattern], v))
        elif isinstance(v, dict):
            for k, child in v.items():
                visit(child, path + (k,))
        elif isinstance(v, list):
            for i, child in enumerate(v):
                visit(child, path + (i,))

    visit(value, ())
    return found


def canonical_value(value):
    clone, labels, kinds, bindings = copy.deepcopy(value), {}, {}, []
    for path, kind, uid in fields(value):
        if uid in kinds and kinds[uid] != kind:
            raise CoreConflict("dev_semantic_provenance_kind_alias")
        kinds[uid] = kind
        if uid not in labels:
            labels[uid] = kind + ":" + str(sum(v == kind for v in kinds.values()) - 1)
        parent = clone
        for k in path[:-1]:
            parent = parent[k]
        parent[path[-1]] = {"execution_provenance": labels[uid]}
        bindings.append(dict(path=list(path), kind=kind, uuid=uid, label=labels[uid]))
    return clone, bindings


def canonical_request(body, purpose):
    value, _, tail = user_value(body, purpose)
    normalized, bindings = canonical_value(value)
    clone = copy.deepcopy(body)
    clone["messages"][1]["content"] = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + tail
    return clone, bindings


def static_projection(body, purpose):
    value, _, _ = user_value(body, purpose)
    return canonical_value(
        dict(
            authority=value["authority"],
            question=value["question"] if purpose == "interpretation" else value["original_question"],
            history=value["history"],
            working_state=value["working_state"],
        )
    )[0]


def request_evidence(
    body, purpose, probe, accounting, campaign_id, *, approved_shell=None, execution_context=None
):
    """Interpretation/exact G match entirely; dynamic G matches its frozen shell.

    Generation model decisions/pack remain subject to existing typed validators;
    their actual canonical content is retained, not equated to a fake answer.
    """
    frozen = probe.get(purpose + "_request")
    normalized, bindings = canonical_request(body, purpose)
    if frozen:
        if normalized != canonical_request(frozen, purpose)[0]:
            raise CoreConflict("dev_semantic_request_drift")
        semantic = digest(normalized)
    else:
        baseline = probe["generation_shell"]
        if (
            approved_shell is None
            or canonical_request(approved_shell, purpose)[0] != canonical_request(baseline, purpose)[0]
        ):
            raise CoreConflict("dev_semantic_generation_context_drift")
        actual, _, _ = user_value(body, purpose)
        approved, _, _ = user_value(approved_shell, purpose)

        def subsequence(values, population):
            remaining = iter(population)
            return all(any(candidate == item for candidate in remaining) for item in values)

        registry = {(kind, uid) for _, kind, uid in fields(approved)}
        if (
            set(actual) != set(approved)
            or set(actual["interpretation"]) != set(approved["interpretation"])
            or actual["original_question"] != approved["original_question"]
            or actual["authority"] != approved["authority"]
            or not subsequence(actual["history"], approved["history"])
            or not subsequence(actual["working_state"], approved["working_state"])
            or any((kind, uid) not in registry for _, kind, uid in fields(actual))
            or body["messages"][0] != baseline["messages"][0]
            or {k: v for k, v in body.items() if k != "messages"}
            != {k: v for k, v in baseline.items() if k != "messages"}
        ):
            raise CoreConflict("dev_semantic_generation_shell_drift")
        semantic = digest(normalized)
    measurement = accounting.measure(body)
    return dict(
        revision=REVISION,
        campaign_id=str(campaign_id),
        semantic_request_sha256=semantic,
        execution_provenance_sha256=digest(bindings),
        execution_provenance=bindings,
        measurement=measurement,
        provider="https://api.deepseek.com/chat/completions:deepseek-flash:non-thinking:one-send",
        semantic_contract_sha256=probe["semantic_contract_sha256"],
        execution_context=execution_context,
        execution_context_sha256=digest(execution_context),
    )


def generation_shell(context, prompt, output_tokens):
    from types import SimpleNamespace

    from citeweave.conversation_evidence import IntentHistory
    from citeweave.conversation_runtime import generation_messages
    from citeweave.llm import completion_payload

    empty = SimpleNamespace(
        original_question=context.request.question,
        retrieval_query="",
        interpretation=SimpleNamespace(mode="USE_ORIGINAL", topic_relation="continue", facts=[]),
        history=tuple(
            IntentHistory(source=s.ref, original_question=s.request.question, relations=s.relations)
            for g in context.history.selected
            for s in g.sources
        ),
        working_state=context.history.state_projection,
        evidence=SimpleNamespace(pack=SimpleNamespace(prompt_json="")),
    )
    return completion_payload(generation_messages(empty, prompt), "deepseek-flash", output_tokens)


def prefix_roles(acceptances):
    return {str(v.id): dict(role=k, turn_id=str(v.turn_id)) for k, v in acceptances.items()}


def align_wire_order(body, purpose, probe, roles):
    """Restore frozen enumeration without changing selection/ranking/Context/IDs.

    Core group members enumerate by random acceptance UUID. Wire order instead
    uses already-frozen semantic prefix roles. Canonical comparison still checks
    arrays in order; it never sorts away arbitrary semantic differences.
    """
    clone = copy.deepcopy(body)
    value, _, tail = user_value(clone, purpose)

    def role(ref):
        known = roles.get(ref["acceptance_id"])
        if not known or known["turn_id"] != ref["turn_id"]:
            raise CoreConflict("dev_semantic_wire_source_not_campaign_prefix")
        return known["role"]

    ranks = probe["wire_order"]
    history_rank = {key: i for i, key in enumerate(ranks["history"])}
    state_rank = {tuple(key): i for i, key in enumerate(ranks["working_state"])}
    try:
        value["history"].sort(key=lambda h: history_rank[role(h["source"])])
        value["working_state"].sort(key=lambda s: state_rank[(role(s["introduced_by"]), s["item"]["key"])])
    except KeyError as exc:
        raise CoreConflict("dev_semantic_wire_membership_drift") from exc
    clone["messages"][1]["content"] = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + tail
    return clone


def uuid_input_bound(body, purpose, accounting):
    """Pinned pretokenizer locality proof, not a sample maximum or padding.

    A canonical UUID is36 ASCII bytes. Extend its left edge across preceding
    ASCII punctuation. Both outer edges are letter/number -> punctuation cuts:
    the pinned numeric-isolation and regex letter/punctuation splits cannot
    cross them for any hex/hyphen UUID. All unaffected pretokenizer pieces are
    identical. BPE never merges across pieces and needs <=one token/UTF8 byte.
    Replace affected islands' exact old count with their invariant byte length.
    """
    spec = json.loads(accounting.tokenizer.to_str())
    if (
        accounting.measure(body)["tokenizer_sha256"] != TOKENIZER_SHA256
        or spec["normalizer"] != {"type": "Sequence", "normalizers": []}
        or spec["model"]["type"] != "BPE"
        or spec["model"]["dropout"] is not None
        or spec["decoder"]["type"] != "ByteLevel"
    ):
        raise CoreConflict("dev_provenance_tokenizer_certificate_invalid")
    value, head, _ = user_value(body, purpose)
    variable = {path for path, _, _ in fields(value)}
    chunks, spans, length = [], [], 0

    def emit(s):
        nonlocal length
        chunks.append(s)
        length += len(s)

    def render(v, path):
        if isinstance(v, dict):
            emit("{")
            for i, (k, child) in enumerate(v.items()):
                if i:
                    emit(",")
                emit(json.dumps(k, ensure_ascii=False) + ":")
                render(child, path + (k,))
            emit("}")
        elif isinstance(v, list):
            emit("[")
            for i, child in enumerate(v):
                if i:
                    emit(",")
                render(child, path + (i,))
            emit("]")
        else:
            start = length
            emit(json.dumps(v, ensure_ascii=False, separators=(",", ":")))
            if path in variable:
                spans.append((start + 1, length - 1))  # UUID bytes inside quotes

    render(value, ())
    assert "".join(chunks) == head
    islands = []
    for start, end in spans:
        while start and head[start - 1] in string.punctuation:
            start -= 1
        if not start or not head[start - 1].isascii() or not head[start - 1].isalnum():
            raise CoreConflict("dev_provenance_locality_boundary_unsupported")
        if head[end] != '"' or not head[end - 1].isalnum():
            raise CoreConflict("dev_provenance_locality_boundary_unsupported")
        if islands and start <= islands[-1][1]:
            islands[-1] = (islands[-1][0], end)
        else:
            islands.append((start, end))
    pieces = accounting.tokenizer.pre_tokenizer.pre_tokenize_str(head)
    edges = {i for _, (a, b) in pieces for i in (a, b)}
    if any(a not in edges or b not in edges for a, b in islands):
        raise CoreConflict("dev_provenance_locality_boundary_unproven")
    proof = []
    for a, b in islands:
        text = head[a:b]
        old_tokens = len(accounting.tokenizer.encode(text, add_special_tokens=False).ids)
        proof.append(dict(start=a, end=b, fixed_length_bytes=len(text.encode()), old_tokens=old_tokens))
    overhead = sum(p["fixed_length_bytes"] - p["old_tokens"] for p in proof)
    measured = accounting.measure(body)
    return dict(
        input_tokens=measured["input_tokens"] + overhead,
        baseline_input_tokens=measured["input_tokens"],
        provenance_overhead_tokens=overhead,
        uuid_occurrences=len(spans),
        islands=proof,
        proof="pinned UUID36 ASCII replacement islands; invariant pretokenizer pieces; BPE tokens<=bytes",
    )


def refreeze(packet, accounting, root):
    """Reuse accepted specimens; re-derive only concrete UUID token overhead."""
    from decimal import Decimal

    from citeweave.conversation_interpretation import InterpretationInput
    from citeweave.costs import maximum_cost
    from citeweave.evaluation.dev_dispatch import generation_input_bound
    from citeweave.llm import completion_payload

    value = copy.deepcopy(packet)
    prompt = (root / "prompts/answer-telecom-v1.txt").read_text(encoding="utf-8")
    for probe in value["probes"]:
        if not probe["dispatch_slots"]:
            continue
        ids = {}
        for purpose in probe["dispatch_slots"]:
            name = purpose + "_request"
            slot = next(
                s
                for s in value["slots"]
                if s["case"] == probe["view"] + ":" + probe["arm"] and s["purpose"] == purpose
            )
            if name in probe:
                saved = probe[name]
                body = completion_payload(
                    [{"role": m["role"], "content": m["content"]} for m in saved["messages"]],
                    saved["model"],
                    saved["max_tokens"],
                )
                if accounting.measure(body) != probe[purpose + "_measurement"]:
                    raise CoreConflict("dev_frozen_specimen_measurement_drift")
                probe[name] = body  # Restore production dictionary order, never archive order.
                bound = uuid_input_bound(body, purpose, accounting)
                probe[purpose + "_provenance_bound"] = bound
                slot["input_tokens"] = bound["input_tokens"]
                ids[purpose] = digest(canonical_request(body, purpose)[0])
            else:
                # The accepted symbolic G bound already counts all UUID bytes.
                # Their lengths/occurrences do not change; BPE variation is already
                # covered by tokens<=whole serialized bytes. No extra allowance.
                context = InterpretationInput.model_validate(probe["context"])
                bound = generation_input_bound(
                    context, prompt, value["reserves"]["interpretation"], value["tokenizer_certificate"]
                )
                if bound != probe["generation_bound"]:
                    raise CoreConflict("dev_symbolic_generation_bound_drift")
                shell = generation_shell(context, prompt, slot["output_tokens"])
                probe["generation_shell"] = shell
                probe["generation_provenance_bound"] = dict(
                    input_tokens=slot["input_tokens"],
                    provenance_overhead_tokens=0,
                    proof="accepted whole-UTF8 symbolic envelope already covers UUID36 fixed lengths and facts insertion",
                )
                ids[purpose] = digest(canonical_request(shell, purpose)[0])
        frozen_body = probe.get("interpretation_request", probe.get("generation_request"))
        frozen_purpose = "interpretation" if "interpretation_request" in probe else "generation"
        frozen_value, _, _ = user_value(frozen_body, frozen_purpose)
        prefix_by_acceptance = {v: k for k, v in probe["prefix_ids"].items()}
        wire_order = dict(
            history=[prefix_by_acceptance[h["source"]["acceptance_id"]] for h in frozen_value["history"]],
            working_state=[
                [prefix_by_acceptance[s["introduced_by"]["acceptance_id"]], s["item"]["key"]]
                for s in frozen_value["working_state"]
            ],
        )
        probe["wire_order"] = wire_order
        probe["semantic_contract_sha256"] = digest(
            dict(revision=REVISION, allowlist=ALLOWLIST, wire_order=wire_order, requests=ids)
        )
    inputs = sum(s["input_tokens"] for s in value["slots"])
    outputs = sum(s["output_tokens"] for s in value["slots"])
    amount = maximum_cost(inputs, outputs)
    if len(value["slots"]) != 38 or outputs != 777079 or amount > Decimal("18.70"):
        raise CoreConflict("dev_provenance_refreeze_human_ceiling_exceeded")
    value.update(
        revision=REVISION,
        provenance_allowlist=ALLOWLIST,
        input_tokens=inputs,
        output_tokens=outputs,
        total_tokens=inputs + outputs,
        maximum_yuan="18.70",
        derived_worst_case_yuan=str(amount),
        provenance_overhead_tokens=inputs - packet["input_tokens"],
        historical_unresolved_exposure_max_cny="0.016110",
        cumulative_hard_ceiling_cny="18.716110",
        authority="HUMAN_DYNAMIC_PROVENANCE_REFREEZE_2026_10_02",
        semantic_contract_sha256=digest(
            dict(
                revision=REVISION,
                allowlist=ALLOWLIST,
                slots=value["slots"],
                probes=[
                    (p["view"], p["arm"], p.get("semantic_contract_sha256", p.get("guard")))
                    for p in value["probes"]
                ],
            )
        ),
    )
    value["stage_input_max"] = {
        purpose: max(s["input_tokens"] for s in value["slots"] if s["purpose"] == purpose)
        for purpose in ("interpretation", "generation")
    }
    expected_slots = [
        s for s in value["slots"] if not (s["case"].startswith("D4.V1:") and s["purpose"] == "generation")
    ]
    value["expected_path_yuan_upper_bound"] = str(
        maximum_cost(
            sum(s["input_tokens"] for s in expected_slots), sum(s["output_tokens"] for s in expected_slots)
        )
    )
    return value
