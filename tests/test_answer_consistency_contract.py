"""Offline authored semantic expectations, NOT a natural-language consistency validator."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from citeweave.answering import validate_citations
from citeweave.profiles import query_profile
from citeweave.settings import ROOT, Settings
from citeweave.trace import runtime_config

OLD = "answer-telecom-v1"
NEW = "answer-telecom-consistency-v1"
OLD_SHA = "4229c840f98099dc4d084a5898f51f45846c644866c787e030925997ddf6a14d"
NEW_SHA = "00877db7c61eb4f5aea05ee8fba6c05253c41e2a9fe9d855c5f5974e2c3497d4"
FIXTURES = json.loads(
    (ROOT / "tests/fixtures/answer_consistency/synthetic-v1.json").read_text(encoding="utf-8")
)["cases"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("offline_contract_test_attempted_network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def test_versioned_prompt_preserves_original_and_adds_only_contract():
    old = (ROOT / "prompts" / f"{OLD}.txt").read_bytes()
    new = (ROOT / "prompts" / f"{NEW}.txt").read_bytes()
    assert hashlib.sha256(old).hexdigest() == OLD_SHA
    assert new.startswith(old)
    assert b"Before composing the response" in new[len(old) :]
    assert hashlib.sha256(new).hexdigest() == NEW_SHA != OLD_SHA
    # Runtime text hashing and receipt byte hashing must agree (including newlines).
    assert new == (ROOT / "prompts" / f"{NEW}.txt").read_text(encoding="utf-8").encode()


def test_explicit_selection_changes_only_prompt_and_keeps_default(monkeypatch):
    from citeweave import trace

    monkeypatch.delenv("CW_TELECOM_ANSWER_PROMPT", raising=False)
    baseline = Settings(_env_file=None)
    assert baseline.telecom_answer_prompt == OLD
    monkeypatch.setattr(trace, "settings", lambda: baseline)
    before = runtime_config("telecom-structural-v1")
    ordinary = runtime_config("m3-context")
    monkeypatch.setenv("CW_TELECOM_ANSWER_PROMPT", NEW)
    selected = Settings(_env_file=None)
    assert selected.telecom_answer_prompt == NEW
    monkeypatch.setattr(trace, "settings", lambda: selected)
    after = runtime_config("telecom-structural-v1")
    assert after["prompt_identity"] == NEW
    assert (
        after["prompt_sha256"] == hashlib.sha256((ROOT / "prompts" / f"{NEW}.txt").read_bytes()).hexdigest()
    )
    assert after["query_revision"].pop("answer_prompt") == NEW
    assert before["query_revision"].pop("answer_prompt") == OLD
    for key in ("prompt_identity", "prompt_sha256"):
        before.pop(key)
        after.pop(key)
    assert before == after  # Retrieval, Parent, provider, budgets and retry policy.
    assert runtime_config("m3-context") == ordinary
    assert query_profile("telecom-structural-v1")["answer_prompt"] == OLD
    with pytest.raises(ValidationError):
        Settings(_env_file=None, telecom_answer_prompt="../unversioned")


def compatible_authored_claims(case, variant):
    """Compare manually authored meanings only; never infer meaning from answer text.

    Keys identify an asked proposition WITH its condition/scope. Values include
    normative strength. Unknown is scoped uncertainty, not a global refusal.
    This oracle checks fixture annotations and cannot assess generated responses.
    """
    expected = case["propositions"]
    seen = {}
    for section in variant["sections"]:
        for proposition, conclusion in section["claims"].items():
            if proposition not in expected or conclusion != expected[proposition]:
                return False
            if proposition in seen and seen[proposition] != conclusion:
                return False
            seen[proposition] = conclusion
    return seen == expected


@pytest.mark.parametrize("case", FIXTURES, ids=lambda c: c["id"])
def test_authored_semantic_pairs_and_existing_citation_boundary(case):
    assert case["provenance"]["kind"] == "independently_authored_synthetic"
    assert not case["provenance"]["historical_reuse"]
    assert {v["expected"] for v in case["variants"]} == {True, False}
    citations = [SimpleNamespace(label=label) for label in case["evidence"]]
    for variant in case["variants"]:
        assert variant["rationale"]
        assert compatible_authored_claims(case, variant) is variant["expected"]
        answer = "\n\n".join(s["text"] for s in variant["sections"])
        # Both coherent and contradictory prose may have valid Citation identity.
        # No semantic acceptance or improvement claim follows from this check.
        result = validate_citations(answer, citations)
        assert result == ([] if answer == "证据不足，无法回答。" else citations)


def test_fixture_coverage_and_bilingual_equivalence():
    coverage = {tag for case in FIXTURES for tag in case["coverage"]}
    assert coverage >= {
        "affirmative",
        "negative",
        "negatively_phrased",
        "conditional_exception",
        "multi_part",
        "comparison",
        "table_summary",
        "english",
        "chinese",
        "insufficient_evidence",
        "scoped_refusal",
        "normative_strength",
    }
    en, zh = FIXTURES[:2]
    assert en["equivalence_group"] == zh["equivalence_group"] == "tripod-permission"
    assert en["propositions"] == zh["propositions"]
    assert len({case["id"] for case in FIXTURES}) == len(FIXTURES)
