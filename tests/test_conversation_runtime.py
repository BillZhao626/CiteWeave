"""Runtime policy/serialization guards without network or real authorization."""

import pytest
from test_conversation_evidence import context as context

from citeweave.conversation_api import UnavailableRuntime
from citeweave.conversation_runtime import build_runtime, generation_messages
from citeweave.costs import maximum_cost
from citeweave.llm import completion_payload
from citeweave.provider_accounting import validate_request
from citeweave.settings import Settings


def test_default_production_runtime_stays_unavailable():
    assert isinstance(build_runtime(Settings(_env_file=None)), UnavailableRuntime)


def test_accounting_rejects_unknown_fields_and_nontext_messages():
    body = completion_payload(
        [{"role": "system", "content": "contract"}, {"role": "user", "content": "question"}], "deepseek-flash"
    )
    validate_request(body)
    for change in ({"tools": []}, {"thinking": {"type": "enabled"}}, {"max_tokens": True}):
        with pytest.raises(ValueError):
            validate_request(dict(body, **change))


def test_generation_uses_existing_prompt_and_current_pack(context):
    from uuid import uuid4

    from conversation_evidence_fixtures import Fixture

    from citeweave.conversation_evidence import assemble
    from citeweave.conversation_interpretation import InterpretationDraft, interpret

    value = context
    fixture = Fixture(uuid4(), value.request.scope)
    decision = interpret(value, draft=InterpretationDraft(topic_relation="continue", dependency="none"))
    assembled = assemble(
        fixture.workspace, uuid4(), value, decision, fixture.material(), max_input_bytes=131072
    )
    messages = generation_messages(assembled, "unchanged prompt")
    assert messages[0]["content"] == "unchanged prompt"
    assert assembled.evidence.pack.prompt_json in messages[1]["content"]
    assert "contextual_intent_not_evidence" in messages[1]["content"]


def test_valid_configuration_builds_real_runtime_and_invalid_policy_fails_closed(tmp_path, monkeypatch):
    from uuid import uuid4

    from pydantic import SecretStr
    from test_conversation_runtime_postgres import SyntheticAccounting, policy

    import citeweave.conversation_runtime as module
    from citeweave.conversation_contract import Admission, Scope
    from citeweave.conversation_runtime import ProductionRuntime

    sample = (
        uuid4(),
        uuid4(),
        Admission(
            question="Original fixture question",
            scope=Scope(kb_id=uuid4(), version_ids=(uuid4(),)),
            expected_head=None,
        ),
    )
    path = tmp_path / "policy.json"
    path.write_text(policy(sample).model_dump_json(), encoding="utf-8")
    config = Settings(
        _env_file=None,
        conversation_runtime_policy=path,
        conversation_tokenizer=tmp_path / "tokenizer.json",
        db_password=SecretStr("synthetic"),
        admin_token=SecretStr("x" * 24),
        DEEPSEEK_API_KEY="synthetic",
    )
    monkeypatch.setattr(module, "DeepSeekAccounting", lambda path: SyntheticAccounting())
    value = build_runtime(config)
    assert isinstance(value, ProductionRuntime)
    assert value.prepare().deadline == value.policy.execution_deadline
    config.deepseek_api_key = SecretStr("")
    assert isinstance(build_runtime(config), UnavailableRuntime)
    config.deepseek_api_key = SecretStr("synthetic")
    path.write_text("{}", encoding="utf-8")
    assert isinstance(build_runtime(config), UnavailableRuntime)


def test_official_accounting_rejects_unknown_tokenizer_and_special_literals(tmp_path):
    from decimal import Decimal
    from types import SimpleNamespace

    from citeweave.provider_accounting import DeepSeekAccounting, serialize_request

    path = tmp_path / "tokenizer.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="tokenizer_identity_mismatch"):
        DeepSeekAccounting(path)
    # No fabricated count: this test stops before any tokenizer method can run.
    accounting = DeepSeekAccounting.__new__(DeepSeekAccounting)
    accounting.reserved = ("<｜User｜>",)
    accounting.tokenizer = SimpleNamespace(encode=lambda *a, **kw: pytest.fail("must reject before counting"))
    body = completion_payload(
        [{"role": "system", "content": "contract"}, {"role": "user", "content": "literal <｜User｜>"}],
        "deepseek-flash",
    )
    with pytest.raises(ValueError, match="special_token_literal"):
        accounting.measure(body)
    assert maximum_cost(73, 300) == Decimal("0.002546")
    assert serialize_request(body).decode("utf-8").count("<｜User｜>") == 1
