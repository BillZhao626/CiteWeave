"""Projection is intent context, never a prior answer or evidence authority."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_conversation_history import source, state_step

from citeweave.conversation_contract import Acceptance, Admission, ProducedResult, Scope, StateValue
from citeweave.conversation_history import (
    MAX_BYTES,
    AcceptedHistory,
    HistoryQuery,
    HistorySource,
    project_state,
    select_history,
)
from citeweave.conversation_interpretation import InterpretationInput
from citeweave.interpretation_response import production_interpretation_messages


def case():
    scope = Scope(kb_id=uuid4(), version_ids=(uuid4(),))
    item = StateValue(id=uuid4(), kind="entity", key="subject", value="Original device")
    accepted = state_step(scope, put=(item,))
    request = Admission(question="Original request", scope=scope, expected_head=None)
    return accepted, request


def test_projection_preserves_identity_scope_and_whole_working_state():
    accepted, request = case()
    before = accepted.model_dump_json()
    projected = HistorySource(acceptance=AcceptedHistory.from_acceptance(accepted), request=request)
    assert isinstance(projected.acceptance, AcceptedHistory)
    assert projected.acceptance.state == accepted.state
    assert projected.acceptance.id == accepted.id
    assert projected.acceptance.turn_id == accepted.turn_id
    assert projected.acceptance.run_id == accepted.run_id
    assert projected.acceptance.conversation_id == accepted.conversation_id
    assert projected.request == request
    assert projected.ref == accepted.state.source
    assert accepted.model_dump_json() == before
    assert "result" not in projected.acceptance.model_dump()
    assert len(projected.model_dump_json().encode()) < MAX_BYTES


@pytest.mark.parametrize("field", ["id", "conversation_id", "turn_id", "run_id", "state", "created_at"])
def test_incomplete_projection_is_not_defaulted(field):
    accepted, _ = case()
    data = AcceptedHistory.from_acceptance(accepted).model_dump(mode="json")
    del data[field]
    with pytest.raises(ValidationError):
        AcceptedHistory.model_validate(data)


@pytest.mark.parametrize("field", ["result", "evidence_pack", "boxes", "trace", "answer"])
def test_raw_heavy_fields_are_not_silently_accepted(field):
    accepted, _ = case()
    data = AcceptedHistory.from_acceptance(accepted).model_dump(mode="json")
    data[field] = {"untrusted": "prior answer"}
    with pytest.raises(ValidationError):
        AcceptedHistory.model_validate(data)


def test_projected_selected_source_never_sends_prior_result_to_interpretation():
    accepted, request = case()
    accepted = accepted.model_copy(
        update={"result": ProducedResult(kind="clarification", text="OLD_ANSWER_NOT_AUTHORITY")}
    )
    history_source = HistorySource(acceptance=AcceptedHistory.from_acceptance(accepted), request=request)
    query = HistoryQuery(scope=request.scope, expected_head=accepted.id)
    history = select_history((history_source,), query, project_state(accepted.state, request.scope))
    context = InterpretationInput(
        conversation_id=accepted.conversation_id,
        turn_id=uuid4(),
        request=request.model_copy(update={"expected_head": accepted.id}),
        previous=accepted,
        history=history,
    )
    payload = json.loads(production_interpretation_messages(context)[1]["content"])
    assert history.selected and payload["history"][0]["source"] == history_source.ref.model_dump(mode="json")
    assert payload["working_state"] == [e.model_dump(mode="json") for e in accepted.state.entries]
    assert "OLD_ANSWER_NOT_AUTHORITY" not in json.dumps(payload)
    assert history.authority == "contextual_intent_not_evidence"


def test_legacy_typed_acceptance_and_frozen_receipts_remain_readable():
    scope = Scope(kb_id=uuid4(), version_ids=(uuid4(),))
    projection = source(scope)
    assert isinstance(projection.acceptance, Acceptance)
    assert HistorySource.model_validate_json(projection.model_dump_json()) == projection
    compact = HistorySource(
        acceptance=AcceptedHistory.from_acceptance(projection.acceptance), request=projection.request
    )
    assert '"result"' not in compact.model_dump_json()


def test_malformed_state_and_missing_request_scope_fail_closed():
    accepted, request = case()
    compact = HistorySource(acceptance=AcceptedHistory.from_acceptance(accepted), request=request)
    data = compact.model_dump(mode="json")
    del data["acceptance"]["state"]["delta"]
    with pytest.raises(ValidationError):
        HistorySource.model_validate(data)
    data = compact.model_dump(mode="json")
    del data["request"]["scope"]
    with pytest.raises(ValidationError):
        HistorySource.model_validate(data)


def test_compact_recent_history_does_not_bypass_relevance_or_source_guards():
    from citeweave.conversation_contract import CoreConflict, ResolvedSignals
    from citeweave.conversation_interpretation import IntentFact, InterpretationDraft, interpret

    scope = Scope(kb_id=uuid4(), version_ids=(uuid4(),))
    old = source(scope, signals=ResolvedSignals(topic="Prior original question"))
    previous = old.acceptance
    old = old.model_copy(update={"acceptance": AcceptedHistory.from_acceptance(previous)})
    query = HistoryQuery(scope=scope, expected_head=previous.id)
    selected = select_history((old,), query, rows=1, payload_bytes=len(old.model_dump_json().encode()))
    assert selected.failure is None and selected.a_inputs == (old.ref,)
    assert not selected.selected and selected.rejected[0].reason == "no_active_relevance"
    request = Admission(question="What about its other stream?", scope=scope, expected_head=previous.id)
    context = InterpretationInput(
        conversation_id=previous.conversation_id,
        turn_id=uuid4(),
        request=request,
        previous=previous,
        history=selected,
    )
    payload = json.loads(production_interpretation_messages(context)[1]["content"])
    assert payload["history"] == payload["working_state"] == []
    with pytest.raises(CoreConflict, match="interpretation_source_unavailable"):
        interpret(
            context,
            draft=InterpretationDraft(
                topic_relation="continue",
                dependency="required",
                facts=(IntentFact(kind="topic", value="Prior original question", source=old.ref),),
            ),
        )
