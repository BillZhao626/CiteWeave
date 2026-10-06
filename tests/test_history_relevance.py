"""Synthetic product boundary checks, not model-quality or history-recall claims."""

import hashlib
import json
from uuid import UUID, uuid4

import pytest
from conversation_evidence_fixtures import FakeGenerator, Fixture
from pydantic import ValidationError
from test_conversation_history import source, state_step
from test_conversation_interpretation import publish_local, span

import citeweave.history_relevance as relevance
from citeweave.answering import REFUSAL
from citeweave.catalog import fingerprint
from citeweave.conversation_contract import (
    Admission,
    CoreConflict,
    HistoryRelation,
    ResolvedSignals,
    Scope,
    SourceRef,
    StateValue,
)
from citeweave.conversation_evidence import intent_context, produce
from citeweave.conversation_history import (
    MAX_BYTES,
    AcceptedHistory,
    C,
    HistoryQuery,
    HistorySource,
    K,
    project_state,
    select_history,
)
from citeweave.conversation_interpretation import (
    IntentFact,
    InterpretationDraft,
    InterpretationInput,
    interpret,
)
from citeweave.history_relevance import CandidateHistory, candidate_messages, resolve_response


@pytest.fixture
def scope():
    return Scope(kb_id=uuid4(), version_ids=(uuid4(),))


def candidate_context(
    scope,
    sources=(),
    *,
    question="那它的一条连接断开时，其他请求会怎样？",
    previous=None,
    signals=None,
    explicit=(),
    incomplete=(),
    **limits,
):
    query = HistoryQuery(
        scope=scope,
        expected_head=previous.id if previous else None,
        signals=signals or ResolvedSignals(),
        explicit=explicit,
    )
    history = select_history(
        tuple(sources),
        query,
        project_state(previous.state, scope) if previous else (),
        incomplete=incomplete,
        candidate_mode=True,
        **limits,
    )
    context = InterpretationInput(
        conversation_id=UUID(int=999),
        turn_id=uuid4(),
        request=Admission(question=question, scope=scope, expected_head=query.expected_head),
        history=history,
        previous=previous,
    )
    return context, CandidateHistory(query=query, history=history)


def compact_source(acceptance, question="Original accepted request"):
    return HistorySource(
        acceptance=AcceptedHistory.from_acceptance(acceptance),
        request=Admission(question=question, scope=acceptance.state.scope, expected_head=None),
        origins=("A",),
    )


def historical_fact(old, value="Device A", kind="entity", *, item_id=None):
    origin = {"type": "history", "source": old.ref.model_dump(mode="json")}
    if item_id is not None:
        origin.update(type="state", state_item_id=str(item_id))
    return {"kind": kind, "value": value, "origin": origin}


def wire(*refs, topic="continue", dependency="required", **fields):
    return json.dumps(
        {
            "topic_relation": topic,
            "dependency": dependency,
            "relevant_sources": [r.model_dump(mode="json") for r in refs],
            **fields,
        },
        ensure_ascii=False,
    )


def resolved(context, candidates, raw):
    final, draft, decision = resolve_response(raw, context=context, candidates=candidates, run_id=uuid4())
    return final, draft, interpret(final, draft=draft), decision


def test_natural_pronoun_is_explicitly_resolved_from_unselected_recent_candidate(scope):
    old = source(scope, signals=ResolvedSignals(entities=("Device A",)), question="Explain Device A")
    context, candidates = candidate_context(scope, (old,))
    assert len(context.history.candidates) == 1
    assert not context.history.selected and not context.history.candidates[0].reasons
    assert select_history((old,), candidates.query).selected == ()  # Legacy semantics stay frozen.
    final, _, decision, declared = resolved(
        context,
        candidates,
        wire(
            old.ref,
            references=[{"mention": {"quote": "它", "occurrence": 0}, "candidates": [historical_fact(old)]}],
        ),
    )
    assert declared.relevant_sources == (old.ref,)
    assert decision.mode == "USE_REWRITE" and decision.sources == (old.ref,)
    assert decision.selected_query == context.request.question + "\nDevice A"
    assert decision.bindings[0].mention == span(context, "它")
    assert final.history.selected == context.history.candidates
    assert context.history.selected == ()  # Resolution does not mutate the inspection input.


@pytest.mark.parametrize("include_noise", [False, True])
def test_self_contained_request_can_choose_no_candidate(scope, include_noise):
    sources = (source(scope, signals=ResolvedSignals(entities=("unrelated",))),) if include_noise else ()
    context, candidates = candidate_context(scope, sources, question="Explain a checksum.")
    final, _, decision, _ = resolved(context, candidates, wire(dependency="none", topic="shift"))
    assert final.history.selected == () and decision.sources == ()
    assert decision.mode == "USE_ORIGINAL" and decision.selected_query == context.request.question
    assert intent_context(final, decision) == ((), ())
    if include_noise:
        assert final.history.rejected[-1].reason == "model_no_relevance"


def test_old_legitimate_metadata_candidate_survives_newer_unrelated_noise(scope):
    # B discovery is supplied by resolved metadata here, not claimed as semantic whole-history recall.
    signals = ResolvedSignals(task="receiver", entities=("Device A",))
    old = source(scope, 1, signals=signals, origins=("B", "task"), question="Old receiver request")
    noise = source(scope, 2, signals=ResolvedSignals(task="display"), question="New display request")
    context, candidates = candidate_context(scope, (noise, old), signals=signals)
    final, _, decision, _ = resolved(context, candidates, wire(old.ref, facts=[historical_fact(old)]))
    assert decision.sources == (old.ref,)
    assert {s.ref for g in final.history.selected for s in g.sources} == {old.ref}
    assert next(g for g in candidates.history.candidates if old in g.sources).reasons
    assert candidate_messages(context, candidates) == candidate_messages(context, candidates)


@pytest.mark.parametrize("identity", ["absent", "forged", "wrong_turn"])
def test_model_cannot_authorize_unavailable_source_identity(scope, identity):
    visible = source(scope, signals=ResolvedSignals(entities=("Device A",)))
    absent = source(scope, 2, signals=ResolvedSignals(entities=("Device A",)))
    context, candidates = candidate_context(scope, (visible,))
    ref = (
        absent.ref
        if identity == "absent"
        else SourceRef(
            acceptance_id=visible.ref.acceptance_id if identity == "wrong_turn" else uuid4(),
            turn_id=uuid4(),
        )
    )
    fact = historical_fact(visible)
    fact["origin"]["source"] = ref.model_dump(mode="json")
    with pytest.raises(CoreConflict, match="relevance_source_unavailable"):
        resolved(context, candidates, wire(ref, facts=[fact]))


def test_source_omitted_by_C_cannot_be_reintroduced_by_model(scope):
    sources = tuple(
        source(scope, n, origins=("B", "topic"), signals=ResolvedSignals(topic="receiver"))
        for n in range(1, C + 2)
    )
    context, candidates = candidate_context(scope, sources, signals=ResolvedSignals(topic="receiver"))
    omitted = sources[-1]
    assert len(context.history.candidates) == C
    assert all(omitted.ref != s.ref for g in context.history.candidates for s in g.sources)
    with pytest.raises(CoreConflict, match="relevance_source_unavailable"):
        resolved(
            context, candidates, wire(omitted.ref, facts=[historical_fact(omitted, "receiver", "topic")])
        )


@pytest.mark.parametrize("location", ["facts", "references", "ambiguities"])
def test_all_semantic_origins_require_explicit_relevance(scope, location):
    old = source(scope, signals=ResolvedSignals(entities=("Device A",)))
    context, candidates = candidate_context(scope, (old,))
    fact = historical_fact(old)
    fields = {
        "facts": {"facts": [fact]},
        "references": {"references": [{"mention": {"quote": "它", "occurrence": 0}, "candidates": [fact]}]},
        "ambiguities": {"ambiguities": [{"reason": "multiple_candidates", "candidates": [fact]}]},
    }[location]
    with pytest.raises(CoreConflict, match="relevance_origin_conflict"):
        resolved(context, candidates, wire(**fields))


def test_inert_and_duplicate_relevance_declarations_are_rejected(scope):
    old = source(scope, signals=ResolvedSignals(entities=("Device A",)))
    context, candidates = candidate_context(scope, (old,))
    with pytest.raises(CoreConflict, match="relevance_origin_conflict"):
        resolved(context, candidates, wire(old.ref, dependency="none"))
    with pytest.raises(CoreConflict, match="relevance_duplicate_source"):
        resolved(context, candidates, wire(old.ref, old.ref, facts=[historical_fact(old)]))


def test_explicit_source_does_not_bypass_existing_dependency_or_intent_guards(scope):
    old = source(scope, signals=ResolvedSignals(entities=("Device A",)))
    context, candidates = candidate_context(scope, (old,))
    with pytest.raises(CoreConflict, match="independent_query_inheritance"):
        resolved(context, candidates, wire(old.ref, dependency="none", facts=[historical_fact(old)]))
    with pytest.raises(CoreConflict, match="incomplete_provenance"):
        resolved(context, candidates, wire(old.ref, facts=[historical_fact(old, "Invented device")]))


def test_explicit_none_is_required_even_for_empty_candidate_set(scope):
    context, candidates = candidate_context(scope)
    with pytest.raises(CoreConflict, match="interpretation_format_schema") as error:
        resolved(context, candidates, '{"topic_relation":"continue","dependency":"none"}')
    assert isinstance(error.value.__cause__, ValidationError)


def test_multiple_plausible_referents_clarify_without_retrieval_or_generation(scope):
    first = source(scope, 1, signals=ResolvedSignals(entities=("Device A",)))
    second = source(scope, 2, signals=ResolvedSignals(entities=("Device B",)))
    context, candidates = candidate_context(scope, (first, second))
    final, draft, decision, _ = resolved(
        context,
        candidates,
        wire(
            first.ref,
            second.ref,
            references=[
                {
                    "mention": {"quote": "它", "occurrence": 0},
                    "candidates": [historical_fact(first), historical_fact(second, "Device B")],
                }
            ],
        ),
    )
    fixture, generator = Fixture(uuid4(), scope), FakeGenerator()
    result, actual = produce(
        fixture.workspace,
        uuid4(),
        final,
        draft=draft,
        retriever=fixture,
        generator=generator,
        max_input_bytes=MAX_BYTES,
    )
    assert decision.mode == actual.mode == "CLARIFY" and result.kind == "clarification"
    assert decision.ambiguities[0].reason == "multiple_candidates"
    assert not fixture.calls and not generator.inputs


def test_K_is_enforced_after_explicit_resolution_without_silent_trimming(scope):
    sources = tuple(
        source(scope, n, signals=ResolvedSignals(entities=(f"Device {n}",))) for n in range(1, K + 2)
    )
    context, candidates = candidate_context(scope, sources)
    assert len(context.history.candidates) > K and not context.history.selected
    with pytest.raises(CoreConflict, match="relevance_exceeds_K"):
        resolved(
            context,
            candidates,
            wire(
                *(s.ref for s in sources),
                facts=[historical_fact(s, f"Device {n}") for n, s in enumerate(sources, 1)],
            ),
        )


def test_correction_group_expands_as_whole_but_superseded_hypothesis_stays_invalid(scope):
    old = source(scope, 1, signals=ResolvedSignals(entities=("Device A",)))
    new = source(
        scope,
        2,
        signals=ResolvedSignals(entities=("Device B",)),
        relations=(HistoryRelation(target=old.ref, kind="correction"),),
    )
    context, candidates = candidate_context(scope, (old, new))
    final, _, decision, _ = resolved(
        context, candidates, wire(new.ref, facts=[historical_fact(new, "Device B")])
    )
    assert len(final.history.selected) == 1
    assert {s.ref for s in final.history.selected[0].sources} == {old.ref, new.ref}
    assert decision.sources == (new.ref,)
    assert {h.source for h in intent_context(final, decision)[0]} == {old.ref, new.ref}
    with pytest.raises(CoreConflict, match="source_superseded"):
        resolved(context, candidates, wire(old.ref, facts=[historical_fact(old)]))
    # A sibling being present for provenance is not permission to use its intent.
    with pytest.raises(CoreConflict, match="relevance_origin_conflict"):
        resolved(context, candidates, wire(new.ref, facts=[historical_fact(old)]))


def test_forged_split_correction_group_cannot_drop_newer_correction(scope):
    old = source(scope, 1, signals=ResolvedSignals(entities=("Device A",)))
    new = source(
        scope,
        2,
        signals=ResolvedSignals(entities=("Device B",)),
        relations=(HistoryRelation(target=old.ref, kind="correction"),),
    )
    context, candidates = candidate_context(scope, (old, new))
    group = context.history.candidates[0]
    original_half = group.model_copy(
        update={
            "identity": (old.acceptance.id,),
            "sources": (old,),
            "edges": (),
            "superseded": (),
            "partially_superseded": (),
        }
    )
    correction_half = group.model_copy(
        update={
            "identity": (new.acceptance.id,),
            "sources": (new,),
            "superseded": (),
            "partially_superseded": (),
        }
    )
    history = context.history.model_copy(update={"candidates": (original_half, correction_half)})
    context = context.model_copy(update={"history": history})
    candidates = candidates.model_copy(update={"history": history})
    # Checking closure across the whole candidate set alone would permit A to be
    # resolved without B, hiding B's correction from the domain validator.
    with pytest.raises(CoreConflict):
        candidate_messages(context, candidates)
    with pytest.raises(CoreConflict):
        resolved(context, candidates, wire(old.ref, facts=[historical_fact(old)]))


@pytest.mark.parametrize(
    "metadata", ["edges", "superseded", "reasons", "origins", "request_hashes", "mandatory"]
)
def test_candidate_group_derived_metadata_cannot_be_silently_forged(scope, metadata):
    old = source(scope, 1, signals=ResolvedSignals(entities=("Device A",)))
    new = source(
        scope,
        2,
        signals=ResolvedSignals(entities=("Device B",)),
        relations=(HistoryRelation(target=old.ref, kind="correction"),),
    )
    context, candidates = candidate_context(scope, (old, new))
    group = context.history.candidates[0]
    forged = () if metadata != "mandatory" else not group.mandatory
    group = group.model_copy(update={metadata: forged})
    history = context.history.model_copy(update={"candidates": (group,)})
    context = context.model_copy(update={"history": history})
    candidates = candidates.model_copy(update={"history": history})
    with pytest.raises(CoreConflict):
        candidate_messages(context, candidates)


def test_mandatory_state_source_flag_cannot_be_cleared(scope):
    previous = state_step(scope, put=(StateValue(id=uuid4(), kind="entity", key="device", value="Device A"),))
    context, candidates = candidate_context(scope, (compact_source(previous),), previous=previous)
    group = context.history.candidates[0]
    assert group.mandatory
    history = context.history.model_copy(
        update={"candidates": (group.model_copy(update={"mandatory": False}),)}
    )
    context = context.model_copy(update={"history": history})
    candidates = candidates.model_copy(update={"history": history})
    with pytest.raises(CoreConflict):
        resolved(context, candidates, wire(dependency="none"))


def test_incomplete_correction_group_fails_before_model_input(scope):
    missing = source(scope, 1)
    corrected = source(scope, 2, relations=(HistoryRelation(target=missing.ref, kind="correction"),))
    context, candidates = candidate_context(scope, (corrected,))
    assert context.history.failure == "incomplete_group"
    with pytest.raises(CoreConflict, match="history_unavailable"):
        candidate_messages(context, candidates)


def test_partial_correction_requires_active_item_and_explicit_state_origin(scope):
    removed = StateValue(id=uuid4(), kind="entity", key="device", value="Device A")
    keep = StateValue(id=uuid4(), kind="constraint", key="limit", value="only C")
    first = state_step(scope, put=(removed, keep))
    second = state_step(
        scope,
        first,
        deactivate=(removed.id,),
        relations=(
            HistoryRelation(target=first.state.source, kind="correction", state_item_ids=(removed.id,)),
        ),
    )
    old, current = compact_source(first), compact_source(second)
    context, candidates = candidate_context(scope, (old, current), previous=second)
    final, _, decision, _ = resolved(
        context,
        candidates,
        wire(old.ref, facts=[historical_fact(old, "only C", "constraint", item_id=keep.id)]),
    )
    assert decision.facts[0].state_item_id == keep.id
    assert len(final.history.selected[0].sources) == 2
    with pytest.raises(CoreConflict, match="source_superseded"):
        resolved(context, candidates, wire(old.ref, facts=[historical_fact(old, "only C", "constraint")]))
    with pytest.raises(CoreConflict, match="state_source_identity"):
        resolved(context, candidates, wire(old.ref, facts=[historical_fact(old, item_id=removed.id)]))
    with pytest.raises(CoreConflict, match="relevance_origin_conflict"):
        resolved(
            context, candidates, wire(facts=[historical_fact(old, "only C", "constraint", item_id=keep.id)])
        )


def test_mandatory_working_state_provenance_alone_does_not_enter_generation_history(scope):
    previous = state_step(scope, put=(StateValue(id=uuid4(), kind="entity", key="device", value="Device A"),))
    old = compact_source(previous)
    context, candidates = candidate_context(scope, (old,), previous=previous, question="Explain a checksum.")
    final, _, decision, _ = resolved(context, candidates, wire(dependency="none"))
    assert final.history.selected[0].mandatory
    assert decision.sources == () and intent_context(final, decision) == ((), ())


def test_explicit_current_correction_uses_mandatory_raw_provenance(scope):
    item = StateValue(id=uuid4(), kind="entity", key="device", value="Device A")
    previous = state_step(scope, put=(item,))
    old = compact_source(previous)
    context, candidates = candidate_context(scope, (old,), previous=previous, question="Use Device B")
    final, _, decision, _ = resolved(
        context,
        candidates,
        wire(
            old.ref,
            dependency="none",
            facts=[{"kind": "entity", "value": "Device B", "origin": {"type": "current", "occurrence": 0}}],
            corrections=[{"item_id": str(item.id), "mention": {"quote": "Device B", "occurrence": 0}}],
            put=[
                StateValue(
                    id=uuid4(), kind="entity", key="device", value="Device B", replaces=(item.id,)
                ).model_dump(mode="json")
            ],
        ),
    )
    assert decision.mode == "USE_ORIGINAL"
    assert any(r.kind == "correction" and r.target == old.ref for r in decision.delta.relations)
    assert intent_context(final, decision) == ((), ())


def test_topic_return_can_use_shift_retired_provenance_but_continue_cannot(scope):
    initial, initial_candidates = candidate_context(scope, question="Explain Device A")
    first_result = interpret(
        initial,
        draft=InterpretationDraft(
            topic_relation="shift",
            dependency="none",
            facts=(IntentFact(kind="topic", value="Device A", span=span(initial, "Device A")),),
            put=(StateValue(id=uuid4(), kind="topic", key="topic", value="Device A"),),
        ),
    )
    first = publish_local(initial, first_result)
    intermediate, intermediate_candidates = candidate_context(
        scope, (compact_source(first),), previous=first, question="Explain a checksum."
    )
    shift_context, _, shifted, _ = resolved(
        intermediate, intermediate_candidates, wire(dependency="none", topic="shift")
    )
    second = publish_local(shift_context, shifted)
    context, candidates = candidate_context(
        scope,
        (compact_source(first), compact_source(second)),
        previous=second,
        question="Return to the old device; how does it behave?",
    )
    old = compact_source(first)
    _, _, decision, _ = resolved(
        context, candidates, wire(old.ref, topic="return", facts=[historical_fact(old, "Device A", "topic")])
    )
    assert decision.topic_relation == "return" and decision.sources == (old.ref,)
    with pytest.raises(CoreConflict, match="inactive_topic_requires_return"):
        resolved(context, candidates, wire(old.ref, facts=[historical_fact(old, "Device A", "topic")]))


@pytest.mark.parametrize("scope_fault", ["wider", "other_kb"])
def test_scope_mismatch_never_becomes_visible_or_resolved(scope, scope_fault):
    invalid = (
        scope.model_copy(update={"version_ids": (*scope.version_ids, uuid4())})
        if scope_fault == "wider"
        else Scope(kb_id=uuid4(), version_ids=scope.version_ids)
    )
    old = source(invalid, signals=ResolvedSignals(entities=("Device A",)))
    context, candidates = candidate_context(scope, (old,))
    assert context.history.candidates == ()
    assert context.history.rejected[0].reason == "scope_unavailable"
    with pytest.raises(CoreConflict, match="relevance_source_unavailable"):
        resolved(context, candidates, wire(old.ref, facts=[historical_fact(old)]))


def test_cross_conversation_candidate_rejected_before_dispatch(scope):
    old = source(scope)
    foreign = old.model_copy(
        update={"acceptance": old.acceptance.model_copy(update={"conversation_id": uuid4()})}
    )
    context, candidates = candidate_context(scope, (foreign,))
    with pytest.raises(CoreConflict, match="conversation_conflict"):
        candidate_messages(context, candidates)


@pytest.mark.parametrize(
    "tampering", ["wrong_group_identity", "duplicate_group", "already_selected", "over_C", "over_members"]
)
def test_unchecked_model_copy_cannot_forge_candidate_structure(scope, tampering):
    old = source(scope)
    context, candidates = candidate_context(scope, (old,))
    group = context.history.candidates[0]
    if tampering == "wrong_group_identity":
        changes = {"candidates": (group.model_copy(update={"identity": (uuid4(),)}),)}
    elif tampering == "duplicate_group":
        changes = {"candidates": (group, group)}
    elif tampering == "already_selected":
        changes = {"selected": (group,)}
    elif tampering == "over_C":
        changes = {"candidates": (group,) * (C + 1)}
    else:
        changes = {"candidates": (group.model_copy(update={"sources": (old,) * 9}),)}
    history = context.history.model_copy(update=changes)
    context = context.model_copy(update={"history": history})
    candidates = candidates.model_copy(update={"history": history})
    with pytest.raises(CoreConflict):
        candidate_messages(context, candidates)


def test_changed_head_or_state_projection_cannot_become_candidate_context(scope):
    previous = state_step(scope, put=(StateValue(id=uuid4(), kind="entity", key="device", value="Device A"),))
    context, candidates = candidate_context(scope, (compact_source(previous),), previous=previous)
    history = context.history.model_copy(update={"state_projection": ()})
    wrong_projection = context.model_copy(update={"history": history})
    with pytest.raises(CoreConflict, match="projection_conflict"):
        candidate_messages(wrong_projection, candidates.model_copy(update={"history": history}))
    request = context.request.model_copy(update={"expected_head": uuid4()})
    with pytest.raises(CoreConflict, match="head_conflict"):
        candidate_messages(context.model_copy(update={"request": request}), candidates)


@pytest.mark.parametrize("reason", ["branch_cap", "statement_timeout", "round_trip_cap"])
def test_incomplete_search_fails_closed_before_candidate_input(scope, reason):
    context, candidates = candidate_context(scope, (source(scope),), incomplete=(reason,))
    with pytest.raises(CoreConflict, match="history_unavailable"):
        candidate_messages(context, candidates)


@pytest.mark.parametrize(
    "metric,excess", [("materialized_rows", 65), ("payload_bytes", MAX_BYTES + 1), ("round_trips", 9)]
)
def test_caller_cannot_forge_past_existing_history_limits(scope, metric, excess):
    context, candidates = candidate_context(scope, (source(scope),))
    history = context.history.model_copy(update={metric: excess})
    context = context.model_copy(update={"history": history})
    candidates = candidates.model_copy(update={"history": history})
    with pytest.raises(CoreConflict, match="candidate_bound"):
        candidate_messages(context, candidates)


def test_candidate_serialization_has_its_own_unchanged_payload_bound(scope):
    old = source(scope, question="x" * (MAX_BYTES + 1))
    context, candidates = candidate_context(scope, (old,))
    with pytest.raises(CoreConflict, match="candidate_payload_cap"):
        candidate_messages(context, candidates)


def test_candidate_input_is_allowlisted_even_for_legacy_full_acceptance(scope):
    old = source(scope, question="User request", signals=ResolvedSignals(entities=("Device A",)))
    context, candidates = candidate_context(scope, (old,))
    text = candidate_messages(context, candidates)[1]["content"]
    message = json.loads(text)
    assert "Original control" not in text
    assert "history" not in message and "working_state" in message["candidate_history"]
    view = message["candidate_history"]["groups"][0]["sources"][0]
    assert set(view) == {"source", "original_question", "scope", "signals", "relations"}
    assert view["source"] == old.ref.model_dump(mode="json")
    assert not {"result", "answer", "citations", "evidence_pack", "boxes", "trace"} & set(view)


def test_new_current_retrieval_and_evidence_are_required_after_resolution(scope):
    old = source(scope, signals=ResolvedSignals(entities=("Device A",)))
    context, candidates = candidate_context(scope, (old,))
    final, draft, _, _ = resolved(context, candidates, wire(old.ref, facts=[historical_fact(old)]))
    fixture, generator = Fixture(uuid4(), scope), FakeGenerator()
    result, decision = produce(
        fixture.workspace,
        uuid4(),
        final,
        draft=draft,
        retriever=fixture,
        generator=generator,
        max_input_bytes=MAX_BYTES,
    )
    assert len(fixture.calls) == 1 and fixture.calls[0][2] == decision.selected_query
    assert len(generator.inputs) == 1 and generator.inputs[0].history[0].source == old.ref
    assert result.answer.citations == [fixture.citation]
    assert "Device A" not in result.evidence_pack.prompt_json
    assert result.trace.evidence_identity and result.trace.history_sources == (old.ref,)


def test_no_current_evidence_refuses_without_using_historical_result(scope):
    old = source(scope, signals=ResolvedSignals(entities=("Device A",)))
    context, candidates = candidate_context(scope, (old,))
    final, draft, _, _ = resolved(context, candidates, wire(old.ref, facts=[historical_fact(old)]))
    fixture, generator = Fixture(uuid4(), scope), FakeGenerator()

    class EmptyCurrentEvidence:
        def retrieve(self, workspace, requested_scope, query):
            fixture.calls.append((workspace, requested_scope, query))
            return fixture.material(empty=True)

    result, _ = produce(
        fixture.workspace,
        uuid4(),
        final,
        draft=draft,
        retriever=EmptyCurrentEvidence(),
        generator=generator,
        max_input_bytes=MAX_BYTES,
    )
    assert len(fixture.calls) == 1 and not generator.inputs
    assert result.kind == "evidence_insufficient" and result.text == REFUSAL
    assert not result.answer.citations


def test_context_receipt_is_off_by_default(scope, tmp_path, monkeypatch):
    monkeypatch.setattr(relevance, "ROOT", tmp_path)
    monkeypatch.delenv("CW_INTERPRETATION_CONTEXT_RECEIPTS", raising=False)
    context, candidates = candidate_context(scope)
    raw = wire(dependency="none")
    final, _, decision, declared = resolved(context, candidates, raw)
    relevance.record_context_receipt(
        uuid4(),
        messages=[{"role": "user", "content": "Diagnostic input"}],
        candidates=candidates,
        context=final,
        wire=declared,
        raw=raw,
    )
    assert decision.mode == "USE_ORIGINAL"
    assert not list(tmp_path.iterdir())


def test_context_receipt_binds_exact_provider_bytes_and_is_never_overwritten(
    scope, tmp_path, monkeypatch, caplog
):
    old = compact_source(
        source(scope, signals=ResolvedSignals(entities=("Device A",))).acceptance,
        question="解释设备 A 的连接方式。",
    )
    context, candidates = candidate_context(scope, (old,))
    messages = candidate_messages(context, candidates)
    # Whitespace and Unicode distinguish the provider's exact text from a
    # normalized structured draft; the ledger result_hash hashes these bytes.
    raw = " \r\n" + wire(old.ref, facts=[historical_fact(old)]) + "\r\n"
    final, _, decision, declared = resolved(context, candidates, raw)
    monkeypatch.setattr(relevance, "ROOT", tmp_path)
    monkeypatch.setenv("CW_INTERPRETATION_CONTEXT_RECEIPTS", "1")
    run_id = uuid4()
    relevance.record_context_receipt(
        run_id, messages=messages, candidates=candidates, context=final, wire=declared, raw=raw
    )
    path = tmp_path / ".runtime" / "interpretation-context" / str(run_id) / "receipt.json"
    original_bytes = path.read_bytes()
    receipt = json.loads(original_bytes)
    assert receipt["kind"] == "interpretation_context_not_evidence"
    assert receipt["raw_interpretation_response"] == raw
    assert receipt["provider_response_sha256"] == hashlib.sha256(raw.encode("utf-8")).hexdigest()
    assert receipt["candidate_input"] == messages
    assert receipt["candidate_input_identity"] == fingerprint(messages)
    assert receipt["candidate_history_identity"] == fingerprint(candidates.model_dump(mode="json"))
    assert receipt["resolved_history"] == final.history.model_dump(mode="json")
    assert receipt["resolved_history_identity"] == fingerprint(receipt["resolved_history"])
    assert receipt["relevance_decision"] == declared.model_dump(mode="json")
    assert receipt["relevance_decision"]["relevant_sources"] == [old.ref.model_dump(mode="json")]
    assert candidates.history.selected == () and final.history.selected
    assert decision.mode == "USE_REWRITE"
    relevance.record_context_receipt(
        run_id, messages=[], candidates=candidates, context=final, wire=declared, raw=raw + "changed"
    )
    assert path.read_bytes() == original_bytes
    assert "interpretation_context_receipt_write_failed" in caplog.text
    assert "changed" not in caplog.text
