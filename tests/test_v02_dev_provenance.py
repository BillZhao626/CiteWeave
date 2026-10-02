"""Frozen semantics, UUID alpha-equivalence and tokenizer locality; no transport."""

import copy
import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from citeweave.conversation_contract import CoreConflict
from citeweave.costs import maximum_cost
from citeweave.evaluation.dev_provenance import (
    align_wire_order,
    canonical_request,
    fields,
    refreeze,
    request_evidence,
    user_value,
    uuid_input_bound,
)
from citeweave.provider_accounting import DeepSeekAccounting

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def artifacts():
    tokenizer = ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    packet = ROOT / ".runtime/evaluation/0012-accepted-runtime/contracts.json"
    if not tokenizer.is_file() or not packet.is_file():
        pytest.skip("accepted local frozen specimens/pinned tokenizer absent")
    accounting = DeepSeekAccounting(tokenizer)
    original = json.loads(packet.read_bytes())
    return accounting, original, refreeze(original, accounting, ROOT)


def change_ids(body, purpose, seed):
    clone = copy.deepcopy(body)
    value, _, tail = user_value(clone, purpose)
    mapping = {}
    for path, _, uid in fields(value):
        mapping.setdefault(uid, str(UUID(seed[:28] + f"{len(mapping):08x}")))
        parent = value
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = mapping[uid]
    clone["messages"][1]["content"] = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + tail
    return clone


def test_refreeze_only_certified_uuid_input_overhead(artifacts):
    accounting, old, new = artifacts
    assert old["input_tokens"] == 6196897
    assert new["input_tokens"] == 6198361
    assert new["provenance_overhead_tokens"] == 1464
    assert new["output_tokens"] == old["output_tokens"] == 777079
    assert new["total_tokens"] == 6975440
    assert maximum_cost(new["input_tokens"], new["output_tokens"]) == Decimal("18.613354")
    assert new["maximum_yuan"] == "18.70"
    assert len(new["slots"]) == 38
    assert new["environment"] == old["environment"]
    assert new["reserves"] == old["reserves"]
    assert sum(s["input_tokens"] for s in new["slots"]) == new["input_tokens"]
    for a, b in zip(old["slots"], new["slots"]):
        assert (
            a["case"] == b["case"]
            and a["purpose"] == b["purpose"]
            and a["output_tokens"] == b["output_tokens"]
        )
        assert b["input_tokens"] >= a["input_tokens"]
    assert accounting.identity


@pytest.mark.parametrize("alphabet", ["0" * 36, "f" * 36, "1a" * 18, "a1" * 18, "abcdef012345" * 3])
def test_all_concrete_islands_cover_uuid_digit_letter_segmentation(artifacts, alphabet):
    accounting, _, packet = artifacts
    # Canonical dash positions and distinct suffixes; branch patterns cover numeric
    # isolation, punctuation-prefixed letters, and repeated letter/digit transitions.
    seed = (
        alphabet[:8]
        + "-"
        + alphabet[8:12]
        + "-"
        + alphabet[12:16]
        + "-"
        + alphabet[16:20]
        + "-"
        + alphabet[20:32]
    )
    for p in packet["probes"]:
        for purpose in p["dispatch_slots"]:
            if purpose + "_request" not in p:
                continue
            body = p[purpose + "_request"]
            bound = uuid_input_bound(body, purpose, accounting)
            changed = change_ids(body, purpose, seed)
            assert canonical_request(body, purpose)[0] == canonical_request(changed, purpose)[0]
            assert accounting.measure(changed)["input_tokens"] <= bound["input_tokens"]


@pytest.mark.parametrize(
    "field", ["question", "scope", "prompt", "history_content", "ordering", "relationship", "extra"]
)
def test_non_allowlisted_drift_and_broken_alias_graph_rejected(artifacts, field):
    accounting, _, packet = artifacts
    probe = next(p for p in packet["probes"] if p["view"] == "D4.V2" and p["arm"] == "cp-ab0-v1")
    body = copy.deepcopy(probe["interpretation_request"])
    value, _, _ = user_value(body, "interpretation")
    if field == "prompt":
        body["messages"][0]["content"] += " drift"
    elif field == "question":
        value["question"] += " drift"
    elif field == "scope":
        value["scope"]["kb_id"] = str(uuid4())
    elif field == "history_content":
        value["history"][0]["question"] += " drift"
    elif field == "ordering":
        value["history"].reverse()
    elif field == "relationship":
        value["working_state"][0]["introduced_by"]["acceptance_id"] = str(uuid4())
    else:
        value["unapproved_id"] = str(uuid4())
    body["messages"][1]["content"] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    with pytest.raises(CoreConflict, match="semantic_request_drift"):
        request_evidence(body, "interpretation", probe, accounting, uuid4())


def test_dynamic_generation_permits_validated_subsets_not_foreign_sources(artifacts):
    accounting, _, packet = artifacts
    probe = next(p for p in packet["probes"] if p["view"] == "D1.V1" and p["arm"] == "cp-a-v1")
    shell = probe["generation_shell"]
    body = copy.deepcopy(shell)
    value, _, _ = user_value(body, "generation")
    value["history"] = []
    value["working_state"] = []
    value["validated_query"] = value["original_question"]
    body["messages"][1]["content"] = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n{}"
    evidence = request_evidence(body, "generation", probe, accounting, uuid4(), approved_shell=shell)
    assert evidence["measurement"]["request_hash"] and evidence["semantic_request_sha256"]
    value["working_state"] = user_value(shell, "generation")[0]["working_state"]
    value["working_state"][0]["item"]["id"] = str(uuid4())
    body["messages"][1]["content"] = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n{}"
    with pytest.raises(CoreConflict, match="generation_shell_drift"):
        request_evidence(body, "generation", probe, accounting, uuid4(), approved_shell=shell)


def test_frozen_wire_order_restores_uuid_enumeration_without_rewriting_ids(artifacts):
    _, _, packet = artifacts
    probe = next(p for p in packet["probes"] if p["view"] == "D3.V2" and p["arm"] == "cp-ab0-v1")
    original = probe["interpretation_request"]
    current = change_ids(original, "interpretation", "abcdef01-2345-6789-abcd-ef0123456789")
    value, _, _ = user_value(current, "interpretation")
    roles = {}
    for i, h in enumerate(value["history"]):
        ref = h["source"]
        roles[ref["acceptance_id"]] = dict(role=probe["wire_order"]["history"][i], turn_id=ref["turn_id"])
    value["history"].reverse()
    current["messages"][1]["content"] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    before = copy.deepcopy(current)
    aligned = align_wire_order(current, "interpretation", probe, roles)
    assert current == before
    assert canonical_request(aligned, "interpretation")[0] == canonical_request(original, "interpretation")[0]
    assert {uid for _, _, uid in fields(user_value(aligned, "interpretation")[0])} == {
        uid for _, _, uid in fields(value)
    }
    assert canonical_request(current, "interpretation")[0] != canonical_request(original, "interpretation")[0]
