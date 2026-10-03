"""Finite dispatch contracts, explicit zero grant and no model construction."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from citeweave.conversation_contract import CoreConflict
from citeweave.evaluation.dev_approval import load_human_gold
from citeweave.evaluation.dev_campaign import DevPolicy, Limits
from citeweave.evaluation.dev_dispatch import decode_output, reserves, slots_for_view, tokenizer_certificate
from citeweave.provider_accounting import DeepSeekAccounting

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def accounting():
    path = ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    if not path.is_file():
        pytest.skip("pinned official tokenizer absent")
    return DeepSeekAccounting(path)


def policy(mode="DISABLED", **updates):
    now = datetime.now(timezone.utc)
    value = dict(
        campaign_id=uuid4(),
        name="synthetic-no-provider-" + uuid4().hex,
        mode=mode,
        identities={
            k: "synthetic-no-io"
            for k in (
                "commit",
                "tree",
                "config",
                "prompts",
                "provider",
                "tokenizer",
                "rate",
                "index",
                "protocol",
            )
        },
        cases=[f"D{i}.V{j}:{a}" for i in range(1, 7) for j in (1, 2) for a in ("cp-a-v1", "cp-ab0-v1")],
        slots=[
            dict(case="D1.V2:cp-a-v1", purpose=p, input_tokens=200, output_tokens=100)
            for p in ("interpretation", "generation")
        ],
        proposed=dict(calls=2, input_tokens=400, output_tokens=200, total_tokens=600, yuan="0.0024"),
        grant=dict(calls=0, input_tokens=0, output_tokens=0, total_tokens=0, yuan="0"),
        expires_at=now + timedelta(minutes=10),
        deadline=now + timedelta(minutes=10),
        review_minutes=288,
    )
    value.update(updates)
    return DevPolicy.model_validate(value)


def test_policy_rejects_skipped_interpretation_and_zero_guard_slot():
    for key in ("D2.V1:cp-a-v1", "D3.V2:cp-a-v1"):
        with pytest.raises(ValueError, match="conditional_slot"):
            policy(slots=[dict(case=key, purpose="interpretation", input_tokens=1, output_tokens=1)])


def test_reserve_is_derived_not_legacy1024_or_reference_max(accounting):
    values = reserves(ROOT, accounting)
    assert values["interpretation"] == 1561
    assert values["generation"] == 32768
    assert values["interpretation"] > values["observed_interpretation_max"]
    assert values["generation"] > values["observed_generation_max"]
    proof = tokenizer_certificate(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json", accounting
    )
    assert proof["max_decoded_utf8_bytes_per_output_token"] == 128


@pytest.mark.parametrize("finish", ["length", None, "content_filter"])
def test_truncation_always_fails_no_repair(accounting, finish):
    with pytest.raises(CoreConflict, match="dev_output_truncated_or_incomplete"):
        decode_output("interpretation", "{}", finish_reason=finish, reserve=1561, accounting=accounting)


def test_invalid_or_incomplete_json_fails_closed(accounting):
    for value in ["{", "{}", '{"topic_relation":"continue"}']:
        with pytest.raises(CoreConflict, match="invalid_json_or_schema"):
            decode_output("interpretation", value, finish_reason="stop", reserve=1561, accounting=accounting)
    with pytest.raises(CoreConflict, match="reserve_exceeded"):
        decode_output("generation", "a " * 100, finish_reason="stop", reserve=84, accounting=accounting)


def test_conditional_38_is_a_hard_slot_membership_bound():
    data, _, _ = load_human_gold(ROOT)
    slots = [(v.id, a, p) for v in data.views for a in ("cp-a-v1", "cp-ab0-v1") for p in slots_for_view(v, a)]
    assert len(slots) == 38
    assert sum(p == "interpretation" for _, _, p in slots) == 15
    assert sum(p == "generation" for _, _, p in slots) == 23
    assert not any(v == "D3.V2" and a == "cp-a-v1" for v, a, _ in slots)


def test_no_positive_grant_in_disabled_or_synthetic_policy():
    for mode in ("DISABLED", "SYNTHETIC"):
        p = policy(mode)
        assert p.grant.yuan == 0 and p.grant.calls == 0
        with pytest.raises(ValueError, match="nonhuman_grant_must_be_zero"):
            DevPolicy.model_validate(
                {
                    **p.model_dump(),
                    "grant": Limits(
                        calls=1, input_tokens=1, output_tokens=1, total_tokens=2, yuan=Decimal("0.00001")
                    ),
                }
            )
    with pytest.raises(ValueError, match="human_authorization_incomplete"):
        policy("HUMAN")


def test_real_launcher_rejects_zero_authority_before_provider_or_fixture(monkeypatch):
    from citeweave.evaluation import dev_launcher

    def forbidden(*args, **kwargs):
        pytest.fail("provider/environment construction before Human grant")

    monkeypatch.setattr(dev_launcher, "DeepSeekProvider", forbidden)
    monkeypatch.setattr(dev_launcher, "bind_environment", forbidden)
    for mode in ("DISABLED", "SYNTHETIC"):
        with pytest.raises(CoreConflict, match="human_authorization_required"):
            dev_launcher.launch(policy(mode))
    assert "FixtureRepository" not in dev_launcher.launch.__code__.co_names


def test_generation_envelope_counts_full_serialization_and_escaping(accounting):
    import json
    from types import SimpleNamespace

    from citeweave.conversation_interpretation import IntentFact, InterpretationInput, TextSpan
    from citeweave.conversation_runtime import generation_messages
    from citeweave.evaluation.dev_dispatch import generation_input_bound, request_contract

    path = ROOT / ".runtime/evaluation/v02-dev-paid-remediation/contracts-head0012.json"
    if not path.exists():
        pytest.skip("real DEV context preparation absent; PG/model preparation is explicit")
    packet = json.loads(path.read_bytes())
    prompt = (ROOT / "prompts/answer-telecom-v1.txt").read_text(encoding="utf-8")
    for probe in packet["probes"]:
        if "interpretation_request" not in probe:
            continue
        context = InterpretationInput.model_validate(probe["context"])
        bound = generation_input_bound(context, prompt, 1561, packet["tokenizer_certificate"])
        # Adversarial serializer edge: nullable defaults, all short current
        # spans, escaped newline/query, longest mode, maximal ASCII pack text.
        facts = [
            IntentFact(kind="constraint", value=c, span=TextSpan(start=i, end=i + 1))
            for i, c in enumerate(context.request.question)
        ]
        assembled = SimpleNamespace(
            original_question=context.request.question,
            retrieval_query='"\\\n' * 170,
            interpretation=SimpleNamespace(mode="USE_ORIGINAL", topic_relation="continue", facts=facts),
            history=(),
            working_state=context.history.state_projection,
            evidence=SimpleNamespace(pack=SimpleNamespace(prompt_json="x" * 6400)),
        )
        _, counted = request_contract(
            "generation", generation_messages(assembled, prompt), bound["input_tokens"], 32768, accounting
        )
        assert counted["input_tokens"] < bound["input_tokens"]
