"""Synthetic observation regressions; no provider or semantic quality claim."""

import copy
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_conversation_history import source
from test_history_relevance import candidate_context, historical_fact, resolved, wire

from citeweave.api import create_app
from citeweave.catalog import fingerprint
from citeweave.context_inspection import verified_projection, verify_provider_binding
from citeweave.conversation_contract import ResolvedSignals, Scope, StateValue
from citeweave.conversation_evidence import intent_context
from citeweave.conversation_public import ConversationScope
from citeweave.history_relevance import candidate_messages
from citeweave.llm import completion_payload
from citeweave.provider_accounting import request_hash


def observation(*, with_state=False, with_noise=False):
    scope = Scope(kb_id=uuid4(), version_ids=(uuid4(),))
    old = source(scope, signals=ResolvedSignals(entities=("HTTP/3",)), question="Explain HTTP/3")
    if with_state:
        item = StateValue(id=uuid4(), kind="entity", key="protocol", value="HTTP/3")
        state = old.acceptance.state.model_copy(
            update={"entries": (), "delta": old.acceptance.state.delta.model_copy(update={"put": (item,)})}
        )
        from citeweave.conversation_history import reduce_state

        state = reduce_state(None, old.ref, scope, state.delta)
        old = old.model_copy(update={"acceptance": old.acceptance.model_copy(update={"state": state})})
    sources = (old,)
    if with_noise:
        sources += (
            source(scope, 2, signals=ResolvedSignals(entities=("unrelated",)), question="Other topic"),
        )
    context, candidates = candidate_context(scope, sources, previous=old.acceptance)
    item_id = old.acceptance.state.entries[0].item.id if with_state else None
    raw = wire(
        old.ref,
        references=[
            {
                "mention": {"quote": "它", "occurrence": 0},
                "candidates": [historical_fact(old, "HTTP/3", item_id=item_id)],
            }
        ],
    )
    final, draft, decision, declared = resolved(context, candidates, raw)
    history, state = intent_context(final, decision)
    messages = candidate_messages(context, candidates)
    receipt = dict(
        kind="interpretation_context_not_evidence",
        candidate_input=messages,
        candidate_input_identity=fingerprint(messages),
        resolved_history=final.history.model_dump(mode="json"),
        resolved_history_identity=fingerprint(final.history.model_dump(mode="json")),
        relevance_decision=declared.model_dump(mode="json"),
        raw_interpretation_response=raw,
        provider_response_sha256=sha256(raw.encode("utf8")).hexdigest(),
    )
    trace = SimpleNamespace(
        metadata_availability="documentary_bundle",
        original_question=context.request.question,
        scope=ConversationScope.model_validate(scope.model_dump()),
        input_head_id=context.request.expected_head,
        conversation_id=UUID(int=999),
        turn_id=context.turn_id,
        run_id=uuid4(),
        interpretation_identity=fingerprint(decision.model_dump(mode="json")),
        selected_query=decision.selected_query,
        history_sources=tuple(s.source for s in history),
        input_state_item_ids=tuple(s.item.id for s in state),
    )
    by_id = {s.acceptance.id: s for s in sources}

    def read(identity):
        s = by_id[identity]
        return SimpleNamespace(
            run=SimpleNamespace(status="ACCEPTED", conversation_id=UUID(int=999)),
            accepted=s.acceptance,
            turn=SimpleNamespace(request=s.request),
        )

    return SimpleNamespace(trace=trace), receipt, read


def test_recent_candidate_is_not_mislabeled_relevant_and_history_answers_are_excluded():
    value, receipt, read = observation(with_noise=True)
    result = verified_projection(value, receipt, read)
    assert result.availability == "VERIFIED_LOCAL_RECEIPT"
    assert len(result.relevant_sources) == 1 and len(result.recent_sources) == 2
    noise = next(s for s in result.candidates if s.question == "Other topic")
    assert noise.recent_candidate and not noise.relevant
    assert result.references[0].mention == "它" and result.references[0].values == ("HTTP/3",)
    serialized = result.model_dump_json()
    assert "Original control" not in serialized  # Old accepted answer never crosses this boundary.
    assert (
        not {"answer", "evidence", "score", "weight", "prompt", "raw_provider"}
        & type(result).model_fields.keys()
    )


@pytest.mark.parametrize("with_state", [False, True])
def test_input_working_state_empty_and_used_entries_are_observed_truthfully(with_state):
    value, receipt, read = observation(with_state=with_state)
    result = verified_projection(value, receipt, read)
    assert len(result.working_state) == int(with_state)
    assert len(result.used_state_item_ids) == int(with_state)
    if with_state:
        assert result.working_state[0].item.value == "HTTP/3"


@pytest.mark.parametrize(
    "field", ["candidate_input_identity", "resolved_history_identity", "provider_response_sha256"]
)
def test_mismatched_receipt_hashes_are_rejected(field):
    value, receipt, read = observation()
    receipt[field] = "0" * 64
    with pytest.raises(ValueError):
        verified_projection(value, receipt, read)


def test_other_run_interpretation_or_modified_source_question_is_rejected():
    value, receipt, read = observation()
    value.trace.interpretation_identity = "0" * 64
    with pytest.raises(ValueError):
        verified_projection(value, receipt, read)
    value, receipt, read = observation()
    forged = copy.deepcopy(receipt)
    forged["resolved_history"]["candidates"][0]["sources"][0]["request"]["question"] = "Fabricated question"
    forged["resolved_history_identity"] = fingerprint(forged["resolved_history"])
    with pytest.raises(ValueError):
        verified_projection(value, forged, read)


@pytest.mark.parametrize("raw", [None, 7, [], {"unexpected": "provider output"}])
def test_non_text_local_provider_response_is_unverifiable(raw):
    value, receipt, read = observation()
    receipt["raw_interpretation_response"] = raw
    # Invalid optional observations must take the explicit unavailable path,
    # rather than escape as AttributeError and fail the whole inspector request.
    with pytest.raises(ValueError, match="context_response_type"):
        verified_projection(value, receipt, read)


def test_local_input_cannot_invent_candidates_even_with_new_self_consistent_hashes():
    _, receipt, _ = observation()
    phase = SimpleNamespace(
        state="COMPLETED",
        model="synthetic-model",
        output_tokens=2048,
        request_hash=request_hash(completion_payload(receipt["candidate_input"], "synthetic-model", 2048)),
        result_hash=receipt["provider_response_sha256"],
    )
    verify_provider_binding(receipt, phase)
    receipt["candidate_input"][1]["content"] += " "
    receipt["candidate_input_identity"] = fingerprint(receipt["candidate_input"])
    with pytest.raises(ValueError, match="durable_provider_binding"):
        verify_provider_binding(receipt, phase)
    with pytest.raises(ValueError):
        verify_provider_binding(receipt, None)


def test_context_route_is_authenticated_read_only_and_has_an_allowlisted_contract(monkeypatch):
    from citeweave import context_inspection

    seen = []
    monkeypatch.setattr(
        context_inspection,
        "observe_context",
        lambda workspace, cv, run: seen.append(run) or dict(run_id=run, availability="NOT_RECORDED"),
    )
    client = TestClient(create_app("synthetic-context-contract-token"))
    path = f"/v1/conversations/{uuid4()}/runs/{uuid4()}/context"
    assert client.get(path).status_code == 401 and not seen
    result = client.get(path, headers={"Authorization": "Bearer synthetic-context-contract-token"})
    assert result.status_code == 200 and result.json()["candidates"] is None
    assert len(seen) == 1
    schema = client.app.openapi()
    assert set(schema["paths"]["/v1/conversations/{conversation_id}/runs/{run_id}/context"]) == {"get"}
    assert (
        not {"raw_interpretation_response", "candidate_input", "raw_provider", "weight"}
        & schema["components"]["schemas"]["ContextObservation"]["properties"].keys()
    )
