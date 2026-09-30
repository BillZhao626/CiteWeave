"""Finite synthetic routing/authority checks, not natural-language quality."""

import json
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from conversation_evidence_fixtures import FakeGenerator, FakeModel, Fixture
from test_conversation_history import source
from test_conversation_interpretation import completion, with_sources

from citeweave.answering import REFUSAL
from citeweave.conversation_contract import Admission, CoreConflict, DocumentaryResult, ResolvedSignals, Scope
from citeweave.conversation_evidence import assemble, make_result, produce, validate_evidence
from citeweave.conversation_history import HistorySelection
from citeweave.conversation_interpretation import InterpretationDraft, InterpretationInput, interpret
from citeweave.structural_retrieval import StructuralRetriever


@pytest.fixture
def context():
    from uuid import UUID

    return InterpretationInput(
        conversation_id=UUID(int=999),
        turn_id=uuid4(),
        request=Admission(
            question="Explain it; not X, in 2024, only C.",
            scope=Scope(kb_id=uuid4(), version_ids=(uuid4(),)),
            expected_head=None,
        ),
        history=HistorySelection(head=None),
    )


@pytest.fixture
def fixture(context):
    return Fixture(uuid4(), context.request.scope)


def original():
    return InterpretationDraft(topic_relation="continue", dependency="none")


def run(context, fixture, draft=None, generator=None, retriever=None, limit=131072):
    return produce(
        fixture.workspace,
        uuid4(),
        context,
        draft=draft or original(),
        retriever=retriever or fixture,
        generator=generator or FakeGenerator(),
        max_input_bytes=limit,
    )


def test_original_routes_exact_question_without_unrelated_history(context, fixture):
    context = with_sources(context, (source(context.request.scope, signals=ResolvedSignals(topic="noise")),))
    generator = FakeGenerator()
    result, decision = run(context, fixture, generator=generator)
    assert fixture.calls[0][2] == context.request.question
    assert generator.inputs[0].history == generator.inputs[0].working_state == ()
    assert result.trace.interpretation_mode == "USE_ORIGINAL"
    assert result.trace.history_sources == () and decision.sources == ()
    assert DocumentaryResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("topic", ["continue", "return"])
def test_rewrite_routes_validated_query_and_preserves_provenance(context, fixture, topic):
    context, draft, fact = completion(context, topic=topic)
    generator = FakeGenerator()
    result, _ = run(context, fixture, draft, generator)
    assert fixture.calls[0][2] == draft.rewrite.text
    assembled = generator.inputs[0]
    assert assembled.original_question == context.request.question
    assert assembled.history[0].source == fact.source
    assert assembled.history[0].authority == "contextual_intent_not_evidence"
    assert result.trace.history_sources == (fact.source,)
    assert result.answer.citations == [fixture.citation]
    assert fact.value not in result.evidence_pack.prompt_json


def test_clarify_calls_neither_retrieval_nor_generation(context, fixture):
    generator = FakeGenerator()
    result, decision = run(
        context, fixture, InterpretationDraft(topic_relation="continue", dependency="unresolved"), generator
    )
    assert result.kind == "clarification" and decision.selected_query is None
    assert not generator.inputs and not fixture.calls


def test_missing_interpretation_fails_before_retrieval(context, fixture):
    with pytest.raises(CoreConflict, match="interpretation_required"):
        produce(
            fixture.workspace,
            uuid4(),
            context,
            retriever=fixture,
            generator=FakeGenerator(),
            max_input_bytes=131072,
        )
    assert not fixture.calls


@pytest.mark.parametrize("fault", ["missing_context", "widening", "rewrite", "projection"])
def test_invalid_interpretation_stops_before_retrieval(context, fixture, fault):
    context, draft, _ = completion(context)
    if fault == "missing_context":
        context = context.model_copy(update={"history": context.history.model_copy(update={"selected": ()})})
    elif fault == "widening":
        draft = draft.model_copy(
            update={
                "rewrite": draft.rewrite.model_copy(
                    update={"scope": context.request.scope.model_copy(update={"version_ids": (uuid4(),)})}
                )
            }
        )
    elif fault == "rewrite":
        draft = draft.model_copy(update={"rewrite": draft.rewrite.model_copy(update={"text": "invented"})})
    else:
        context = context.model_copy(update={"history": context.history.model_copy(update={"head": uuid4()})})
    with pytest.raises(CoreConflict):
        run(context, fixture, draft)
    assert not fixture.calls


@pytest.mark.parametrize(
    "fault",
    ["version", "document", "workspace", "label", "quote", "duplicate", "prompt", "coverage", "length"],
)
def test_malformed_or_out_of_scope_pack_rejected_before_generation(context, fixture, fault):
    material = fixture.material().model_copy(deep=True)
    if fault == "version":
        material.pack.spans[0].version_id = str(uuid4())
    elif fault == "document":
        material.pack.spans[0].document_id = str(uuid4())
    elif fault == "workspace":
        material.snapshot.workspace_id = str(uuid4())
    elif fault == "label":
        material.citations[0].label = "E2"
    elif fault == "quote":
        material.citations[0].span = material.citations[0].span.model_copy(update={"quote": "memory claim"})
    elif fault == "duplicate":
        material.pack.spans.append(material.pack.spans[0])
    elif fault == "prompt":
        value = json.loads(material.pack.prompt_json)
        value["evidence"][0]["text"] = "history as truth"
        material.pack.prompt_json = json.dumps(value)
        material.pack.serialized_chars = len(material.pack.prompt_json)
    elif fault == "coverage":
        material.pack.source_coverage.selected = []
    else:
        material.pack.serialized_tokens = 2049
    generator = FakeGenerator()
    with pytest.raises(CoreConflict):
        run(context, fixture, generator=generator, retriever=NS(retrieve=lambda *args: material))
    assert not generator.inputs


@pytest.mark.parametrize("fault", ["old_run", "old_citation", "invented_label", "malformed", "uncited"])
def test_answer_must_match_current_run_and_current_pack(context, fixture, fault):
    def generate(assembled):
        answer = FakeGenerator().generate(assembled)
        if fault == "old_run":
            answer.run_id = uuid4()
        elif fault == "old_citation":
            # Even an identically labelled, physically valid old span is not this pack.
            answer.citations = [Fixture(fixture.workspace, fixture.scope).citation]
            answer.citations[0].evidence_id = uuid4()
        else:
            answer.text = {"invented_label": "claim [E2]", "malformed": "claim [E01]", "uncited": "claim"}[
                fault
            ]
        return answer

    with pytest.raises(ValueError):
        run(context, fixture, generator=NS(generate=generate))


def test_empty_current_pack_refuses_without_old_evidence_or_generation(context, fixture):
    generator = FakeGenerator()
    result, _ = run(
        context,
        fixture,
        generator=generator,
        retriever=NS(retrieve=lambda *args: fixture.material(empty=True)),
    )
    assert result.text == REFUSAL and result.kind == "evidence_insufficient"
    assert not result.answer.citations and not generator.inputs


def test_explicit_refusal_with_nonempty_pack_is_valid(context, fixture):
    def refuse(assembled):
        answer = FakeGenerator().generate(assembled)
        answer.text, answer.citations = REFUSAL, []
        return answer

    result, _ = run(context, fixture, generator=NS(generate=refuse))
    assert result.kind == "evidence_insufficient"


def test_overflow_is_not_evidence_insufficient(context, fixture):
    decision = interpret(context, draft=original())
    material = fixture.material()
    run_id = uuid4()
    assembled = assemble(fixture.workspace, run_id, context, decision, material, max_input_bytes=131072)
    count = len(assembled.model_dump_json().encode("utf-8"))
    assert (
        assemble(fixture.workspace, run_id, context, decision, material, max_input_bytes=count) == assembled
    )
    with pytest.raises(CoreConflict, match="context_overflow"):
        assemble(fixture.workspace, run_id, context, decision, material, max_input_bytes=count - 1)


def test_retrieval_failure_propagates_no_historical_fallback(context, fixture):
    generator = FakeGenerator()

    def failed(*args):
        raise TimeoutError("synthetic retrieval failure")

    with pytest.raises(TimeoutError):
        run(context, fixture, generator=generator, retriever=NS(retrieve=failed))
    assert not generator.inputs


def test_generation_cannot_mutate_current_pack(context, fixture):
    def mutate(assembled):
        answer = FakeGenerator().generate(assembled)
        answer.citations[0].evidence_id = uuid4()
        assembled.evidence.pack.spans[0].evidence_id = str(answer.citations[0].evidence_id)
        return answer

    with pytest.raises(CoreConflict, match="citation_conflict"):
        run(context, fixture, generator=NS(generate=mutate))


def test_existing_structural_rag_and_selection_are_reused_unchanged(context, fixture):
    retriever = StructuralRetriever(
        fixture.snapshot, model=FakeModel(), repository=fixture.repository, branch_query=fixture.branch
    )
    chunks, trace = retriever.retrieve(context.request.question, [str(fixture.version)])
    assert chunks == [fixture.atom] and trace[0]["bge"]["score"] == 0.5
    assert retriever.pack == fixture.material().pack
    validate_evidence(fixture.workspace, fixture.scope, fixture.material())


def test_result_validation_does_not_claim_semantic_entailment(context, fixture):
    decision = interpret(context, draft=original())
    assembled = assemble(
        fixture.workspace, uuid4(), context, decision, fixture.material(), max_input_bytes=131072
    )
    answer = FakeGenerator().generate(assembled)
    answer.text = "A deliberately unsupported synthetic proposition [E1]"
    result = make_result(assembled, answer)
    assert result.trace.validation == "CURRENT_PACK_PHYSICAL_ONLY"
    assert result.answer.citations[0].span.support_status == "not_assessed"


def test_corrected_state_is_absent_but_complete_source_relations_remain(context, fixture):
    from test_conversation_history import state_step
    from test_conversation_interpretation import state_context

    from citeweave.conversation_contract import HistoryRelation, StateValue
    from citeweave.conversation_interpretation import IntentFact, RetrievalRewrite

    old = StateValue(id=uuid4(), kind="entity", key="device", value="A")
    keep = StateValue(id=uuid4(), kind="constraint", key="limit", value="only C")
    first = state_step(context.request.scope, put=(old, keep))
    second = state_step(
        context.request.scope,
        first,
        deactivate=(old.id,),
        relations=(HistoryRelation(target=first.state.source, kind="correction", state_item_ids=(old.id,)),),
    )
    context = state_context(context, second, first)
    draft = InterpretationDraft(
        topic_relation="continue",
        dependency="required",
        facts=(
            IntentFact(kind="constraint", value="only C", source=first.state.source, state_item_id=keep.id),
        ),
        rewrite=RetrievalRewrite(text=context.request.question + "\nonly C", scope=context.request.scope),
    )
    generator = FakeGenerator()
    result, _ = run(context, fixture, draft, generator)
    assert result.trace.state_item_ids == (keep.id,)
    assert len(generator.inputs[0].history) == 2
    assert any(h.relations for h in generator.inputs[0].history)
    assert all(e.item.id != old.id for e in generator.inputs[0].working_state)


def test_historical_wider_scope_cannot_enter_current_retrieval(context, fixture):
    from citeweave.conversation_history import HistoryQuery, select_history

    wider = context.request.scope.model_copy(
        update={"version_ids": (*context.request.scope.version_ids, uuid4())}
    )
    old = source(wider, origins=("explicit",), signals=ResolvedSignals(entities=("Device A",)))
    history = select_history(
        (old,), HistoryQuery(scope=context.request.scope, expected_head=None, explicit=(old.ref,))
    )
    with pytest.raises(CoreConflict, match="history_unavailable"):
        run(context.model_copy(update={"history": history}), fixture)
    assert not fixture.calls


@pytest.mark.parametrize(
    "name", ["citeweave", "postgres", "cw_conversation_test_not_a_uuid", "cw_conversation_test_"]
)
def test_isolation_guard_rejects_application_database_before_fixture_writes(name):
    from conversation_evidence_fixtures import require_isolated_database

    with pytest.raises(RuntimeError, match="isolated_context_test_database_required"):
        require_isolated_database(NS(scalar=lambda query: name))


def test_isolation_fixture_remains_registered_and_uuid_guard_accepts():
    import test_conversation_evidence_postgres as pg
    from conversation_evidence_fixtures import require_isolated_database

    assert pg.isolated_pg is pg.pg.isolated_pg
    assert pg.pytestmark is pg.pg.pytestmark
    require_isolated_database(NS(scalar=lambda query: "cw_conversation_test_" + uuid4().hex))
