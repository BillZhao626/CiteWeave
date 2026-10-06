"""Provider text is diagnostic input, never accepted state or a semantic repair."""

import hashlib
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_conversation_evidence import context as context

import citeweave.interpretation_response as response
from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationDraft, interpret


def test_valid_response_still_requires_domain_schema(context):
    draft = response.parse_interpretation_response(
        '{"topic_relation":"continue","dependency":"none"}', context=context, run_id=uuid4()
    )
    assert draft.facts == () and draft.rewrite is None


@pytest.mark.parametrize("raw", ['{"broken":', '{"topic_relation":"continue"}'])
def test_diagnostics_opt_in_exact_raw_and_no_state(tmp_path, monkeypatch, raw, context):
    monkeypatch.setattr(response, "ROOT", tmp_path)
    monkeypatch.setenv("CW_INTERPRETATION_DIAGNOSTICS", "1")
    run = uuid4()
    with pytest.raises(CoreConflict):
        response.parse_interpretation_response(raw, context=context, run_id=run)
    folder = tmp_path / ".runtime" / "interpretation-diagnostics" / str(run)
    assert (folder / "provider-output.txt").read_bytes() == raw.encode()
    record = json.loads((folder / "validation.json").read_text())
    assert record["sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert all("input" not in e for e in record["errors"])
    assert record["kind"] == "raw_provider_output_not_application_state"


def test_diagnostics_disabled_by_default(tmp_path, monkeypatch, context):
    monkeypatch.setattr(response, "ROOT", tmp_path)
    monkeypatch.delenv("CW_INTERPRETATION_DIAGNOSTICS", raising=False)
    with pytest.raises(CoreConflict):
        response.parse_interpretation_response("invalid", context=context, run_id=uuid4())
    assert not list(tmp_path.iterdir())


def test_observed_originless_scope_facts_reproduce_validation_failure(context):
    # Exact observed failure shape with synthetic IDs; original provider bytes
    # remain in the ignored local diagnostic, not a tracked product fixture.
    raw = json.dumps(
        {
            "topic_relation": "continue",
            "dependency": "none",
            "facts": [
                {"kind": "topic", "value": "paraphrased topic", "span": {"start": 0, "end": 16}},
                {"kind": "task", "value": "paraphrased task", "span": {"start": 0, "end": 43}},
                {"kind": "document", "value": str(context.request.scope.kb_id)},
                {"kind": "version", "value": str(context.request.scope.version_ids[0])},
            ],
        }
    )
    with pytest.raises(ValidationError) as error:
        InterpretationDraft.model_validate_json(raw)
    assert [e["loc"] for e in error.value.errors()] == [("facts", 2), ("facts", 3)]
    assert all("exactly_one_intent_origin_required" in e["msg"] for e in error.value.errors())
    # The fix never repairs these unsupported facts by inventing their origins.
    with pytest.raises(CoreConflict, match="interpretation_format_schema"):
        response.parse_interpretation_response(raw, context=context, run_id=uuid4())


def test_current_literal_origin_converts_to_exact_span(context):
    raw = json.dumps(
        {
            "topic_relation": "continue",
            "dependency": "none",
            "facts": [{"kind": "negation", "value": "not X", "origin": {"type": "current", "occurrence": 0}}],
        }
    )
    draft = response.parse_interpretation_response(raw, context=context, run_id=uuid4())
    fact = draft.facts[0]
    assert context.request.question[fact.span.start : fact.span.end] == "not X"
    assert interpret(context, draft=draft).selected_query == context.request.question


@pytest.mark.parametrize("value", ["paraphrased topic", "scope UUID is not a question literal"])
def test_current_fact_cannot_paraphrase_or_borrow_scope(value, context):
    raw = json.dumps(
        {
            "topic_relation": "continue",
            "dependency": "none",
            "facts": [{"kind": "topic", "value": value, "origin": {"type": "current", "occurrence": 0}}],
        }
    )
    with pytest.raises(CoreConflict, match="interpretation_format_quote_occurrence"):
        response.parse_interpretation_response(raw, context=context, run_id=uuid4())


@pytest.mark.parametrize(
    "body",
    [
        {"dependency": "none"},
        {"topic_relation": "continue"},
        {"topic_relation": "continue", "dependency": "none", "facts": [{"kind": "topic", "value": "X"}]},
        {"topic_relation": "continue", "dependency": "none", "facts": None},
        {"topic_relation": "continue", "dependency": "none", "rewrite": {"text": "invented"}},
    ],
)
def test_required_fields_origins_and_extra_fields_remain_strict(body, context):
    with pytest.raises(CoreConflict, match="interpretation_format_schema"):
        response.parse_interpretation_response(json.dumps(body), context=context, run_id=uuid4())


@pytest.mark.parametrize(
    "raw",
    [
        '{"topic_relation":',
        '```json\n{"topic_relation":"continue","dependency":"none"}\n```',
        '{"result":{"topic_relation":"continue","dependency":"none"}}',
    ],
)
def test_malformed_or_uncontracted_wrappers_are_not_silently_extracted(raw, context):
    with pytest.raises(CoreConflict, match="interpretation_format_schema"):
        response.parse_interpretation_response(raw, context=context, run_id=uuid4())


def test_production_wire_schema_and_prompt_do_not_import_evaluation_policy(context):
    from citeweave.conversation_runtime import interpretation_messages
    from citeweave.interpretation_format import FormatDraft

    legacy = interpretation_messages(context)
    current = response.production_interpretation_messages(context)
    before, after = [json.loads(m[1]["content"]) for m in [legacy, current]]
    assert after.pop("output_schema") == FormatDraft.model_json_schema()
    before.pop("output_schema")
    assert before == after
    assert "Evaluation origin clarification" not in current[0]["content"]
    assert "selected history sources" in current[0]["content"]
    assert "exactly one tagged origin" in current[0]["content"]


def test_diagnostic_io_failure_keeps_original_error(tmp_path, monkeypatch, context):
    monkeypatch.setattr(response, "ROOT", tmp_path)
    monkeypatch.setenv("CW_INTERPRETATION_DIAGNOSTICS", "1")
    (tmp_path / ".runtime").write_text("blocked directory")
    with pytest.raises(CoreConflict, match="interpretation_format_schema"):
        response.parse_interpretation_response("invalid", context=context, run_id=uuid4())


def test_domain_guard_diagnostics_do_not_include_parsed_state(tmp_path, monkeypatch):
    monkeypatch.setattr(response, "ROOT", tmp_path)
    monkeypatch.setenv("CW_INTERPRETATION_DIAGNOSTICS", "1")
    run = uuid4()
    response.record_interpretation_failure(
        "exact provider text", run_id=run, exc=CoreConflict("rewrite_required")
    )
    folder = tmp_path / ".runtime" / "interpretation-diagnostics" / str(run)
    report = json.loads((folder / "validation.json").read_text())
    assert report["errors"] == [{"code": "rewrite_required"}]
    assert "parsed_state" not in report
    assert (folder / "provider-output.txt").read_text() == "exact provider text"
