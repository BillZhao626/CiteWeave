"""Original synthetic intent fixtures; no semantic-quality or provider claims."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from citeweave.conversation_contract import (
    Acceptance,
    Admission,
    CoreConflict,
    HistoryRelation,
    ProducedResult,
    ResolvedConversationDelta,
    ResolvedSignals,
    Scope,
    SourceRef,
    StateSnapshot,
    StateValue,
)
from citeweave.conversation_history import (
    HistoryQuery,
    HistorySource,
    project_state,
    reduce_state,
    select_history,
)


@pytest.fixture
def scope():
    return Scope(kb_id=uuid4(), version_ids=(uuid4(),))


def source(scope, number=1, *, signals=None, relations=(), origins=("A",), question="same text"):
    turn = UUID(int=number + 10000)
    ref = SourceRef(acceptance_id=UUID(int=number), turn_id=turn)
    state = reduce_state(
        None,
        ref,
        scope,
        ResolvedConversationDelta(
            source_turn_id=turn,
            previous_snapshot_id=None,
            signals=signals or ResolvedSignals(),
            relations=relations,
        ),
    )
    accepted = Acceptance(
        id=ref.acceptance_id,
        conversation_id=UUID(int=999),
        turn_id=turn,
        run_id=uuid4(),
        result=ProducedResult(kind="clarification", text="Original control"),
        state=state,
        created_at=datetime.now(timezone.utc),
    )
    return HistorySource(
        acceptance=accepted,
        request=Admission(question=question, scope=scope, expected_head=None),
        origins=origins,
    )


def query(scope, **kwargs):
    return HistoryQuery(scope=scope, expected_head=None, **kwargs)


def test_empty_and_recent_without_relevance(scope):
    assert select_history((), query(scope)).selected == ()
    result = select_history((source(scope),), query(scope))
    assert len(result.a_inputs) == 1 and not result.selected
    assert result.rejected[0].reason == "no_active_relevance"


@pytest.mark.parametrize(
    "branch,signals",
    [
        ("entity_constraints", ResolvedSignals(task="t", entities=("e",), constraints=("not-x",))),
        ("task", ResolvedSignals(task="t")),
        ("topic", ResolvedSignals(topic="p")),
    ],
)
def test_exact_structured_branches(scope, branch, signals):
    old = source(scope, signals=signals, origins=(branch,))
    result = select_history((old,), query(scope, signals=signals))
    assert result.selected[0].reasons[0] == branch
    assert result.branch_matches[branch] == (old.ref,)


def test_explicit_old_and_exact_duplicate(scope):
    old = source(scope, origins=("explicit",))
    duplicate = old.model_copy(update={"origins": ("A",)})
    result = select_history((old, duplicate), query(scope, explicit=(old.ref,)))
    assert result.union_before_dedup == 2 and result.union_after_dedup == 1
    assert len(result.selected[0].sources) == 1
    assert result.selected[0].origins == ("A", "explicit")


def test_same_entity_other_task_and_missing_constraint_do_not_match_entity(scope):
    old = source(scope, signals=ResolvedSignals(task="old", topic="p", entities=("e",)))
    q = query(scope, signals=ResolvedSignals(task="new", topic="p", entities=("e",)))
    assert not select_history((old,), q).selected
    q = query(scope, signals=ResolvedSignals(task="old", entities=("e",), constraints=("required",)))
    assert select_history((old,), q).selected[0].reasons == ("task",)


def test_correction_is_indivisible_and_old_match_inactive(scope):
    old = source(scope, signals=ResolvedSignals(topic="old"))
    new = source(
        scope,
        2,
        signals=ResolvedSignals(topic="new"),
        relations=(HistoryRelation(target=old.ref, kind="correction"),),
    )
    result = select_history((new, old), query(scope, explicit=(old.ref,)))
    group = result.selected[0]
    assert group.identity == (old.ref.acceptance_id, new.ref.acceptance_id)
    assert group.superseded == (old.ref,) and len(group.edges) == 1
    assert not select_history((new, old), query(scope, signals=ResolvedSignals(topic="old"))).selected
    assert select_history((new,), query(scope)).failure == "incomplete_group"


def test_same_text_versions_remain_distinct_and_scope_rejected(scope):
    other_scope = Scope(kb_id=scope.kb_id, version_ids=(uuid4(),))
    one, two = source(scope), source(other_scope, 2)
    both = Scope(kb_id=scope.kb_id, version_ids=scope.version_ids + other_scope.version_ids)
    assert len(select_history((one, two), query(both, explicit=(one.ref, two.ref))).selected) == 2
    assert select_history((two,), query(scope, explicit=(two.ref,))).failure == "mandatory_scope_unavailable"
    assert select_history((), query(scope, explicit=(one.ref,))).failure == "mandatory_source_unavailable"


def test_stable_relevance_C_K_and_mandatory_overflow(scope):
    sources = tuple(source(scope, i, signals=ResolvedSignals(topic="p")) for i in range(1, 11))
    q = query(scope, signals=ResolvedSignals(topic="p"), explicit=(sources[-1].ref,))
    result = select_history(tuple(reversed(sources)), q)
    assert [g.identity[0].int for g in result.selected] == [10, 1]
    assert len(result.candidates) == 8 and result.cutoff == ("C_cutoff", "K_cutoff")
    assert result == select_history(tuple(reversed(sources)), q)
    for n, failure in ((3, "mandatory_exceeds_K"), (9, "mandatory_exceeds_C")):
        assert (
            select_history(sources, query(scope, mandatory=tuple(s.ref for s in sources[:n]))).failure
            == failure
        )


@pytest.mark.parametrize(
    "kwargs,reason",
    [
        ({"rows": 65}, "row_cap"),
        ({"payload_bytes": 131073}, "payload_cap"),
        ({"trips": 9}, "round_trip_cap"),
        ({"incomplete": ("branch_cap",)}, "branch_cap"),
    ],
)
def test_limits_are_explicit(scope, kwargs, reason):
    result = select_history((), query(scope), **kwargs)
    assert result.search_incomplete and result.failure == "search_incomplete" and reason in result.cutoff


def test_complete_group_member_cap(scope):
    members = [source(scope)]
    for i in range(2, 10):
        members.append(
            source(scope, i, relations=(HistoryRelation(target=members[-1].ref, kind="correction"),))
        )
    assert select_history(tuple(members), query(scope)).failure == "group_member_cap"


def state_step(scope, previous=None, *, put=(), deactivate=(), relations=(), head=None):
    ref = SourceRef(acceptance_id=uuid4(), turn_id=uuid4())
    delta = ResolvedConversationDelta(
        source_turn_id=ref.turn_id,
        previous_snapshot_id=head or (previous.id if previous else None),
        put=put,
        deactivate=deactivate,
        relations=relations,
    )
    state = reduce_state(previous, ref, scope, delta)
    return Acceptance(
        id=ref.acceptance_id,
        turn_id=ref.turn_id,
        conversation_id=UUID(int=999),
        run_id=uuid4(),
        state=state,
        result=ProducedResult(kind="clarification", text="Original"),
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize("kind", ["topic", "entity", "constraint", "ambiguity"])
def test_state_set_supersede_and_clear(scope, kind):
    item = StateValue(id=uuid4(), kind=kind, key="resolved-id", value="first")
    first = state_step(scope, put=(item,))
    replacement = StateValue(id=uuid4(), kind=kind, key=item.key, value="second", replaces=(item.id,))
    edge = HistoryRelation(target=first.state.source, kind="correction")
    second = state_step(scope, first, put=(replacement,), relations=(edge,))
    assert first.state.entries[0].active  # Old snapshot remains immutable.
    assert not second.state.entries[0].active and second.state.entries[0].change == "superseded"
    assert second.state.entries[0].changed_by == second.state.source
    third = state_step(
        scope,
        second,
        deactivate=(replacement.id,),
        relations=(HistoryRelation(target=second.state.source, kind="correction"),),
    )
    assert not project_state(third.state, scope)
    assert third.state.delta.deactivate == (replacement.id,)


def test_scope_narrowing_and_projection_cap_do_not_truncate_durable_snapshot(scope):
    wide = Scope(kb_id=scope.kb_id, version_ids=scope.version_ids + (uuid4(),))
    items = tuple(StateValue(id=uuid4(), kind="entity", key=str(i), value="original") for i in range(17))
    first = state_step(wide, put=items)
    with pytest.raises(CoreConflict, match="projection_cap"):
        project_state(first.state, wide)
    second = state_step(scope, first)
    assert len(second.state.entries) == 17 and not project_state(second.state, scope)
    assert all(e.change == "scope_narrowed" for e in second.state.entries)


def test_illegal_state_references_and_head(scope):
    with pytest.raises(CoreConflict, match="state_reference_unavailable"):
        state_step(scope, deactivate=(uuid4(),))
    with pytest.raises(CoreConflict, match="head_conflict"):
        state_step(scope, head=uuid4())
    first = state_step(scope, put=(StateValue(id=uuid4(), kind="constraint", key="c", value="v"),))
    with pytest.raises(CoreConflict, match="correction_provenance_missing"):
        state_step(scope, first, deactivate=(first.state.entries[0].item.id,))
    with pytest.raises(ValidationError):
        StateValue(id=uuid4(), kind="personality", key="x", value="x")
    with pytest.raises(ValidationError):
        ResolvedConversationDelta(source_turn_id=uuid4(), previous_snapshot_id=None, inferred_text="guess")


def test_legacy_v1_acceptance_remains_readable(scope):
    original = source(scope).acceptance
    legacy = original.model_copy(
        update={"state": StateSnapshot(source_turn_id=original.turn_id, previous_snapshot_id=None)}
    )
    assert Acceptance.model_validate_json(legacy.model_dump_json()) == legacy
    current = state_step(scope, legacy)
    assert current.state.previous_snapshot_id == legacy.id and current.state.entries == ()


def test_item_specific_correction_preserves_other_inherited_constraints(scope):
    entity = StateValue(id=uuid4(), kind="entity", key="e", value="resolved")
    constraint = StateValue(id=uuid4(), kind="constraint", key="c", value="inherited")
    first = state_step(scope, put=(entity, constraint))
    second = state_step(
        scope,
        first,
        deactivate=(entity.id,),
        relations=(
            HistoryRelation(target=first.state.source, kind="correction", state_item_ids=(entity.id,)),
        ),
    )
    assert [e.item.id for e in project_state(second.state, scope)] == [constraint.id]
    request = Admission(question="Original intent", scope=scope, expected_head=None)
    result = select_history(
        tuple(HistorySource(acceptance=a, request=request) for a in (first, second)),
        query(scope),
        project_state(second.state, scope),
    )
    assert result.selected[0].partially_superseded == (first.state.source,)
    assert result.selected[0].superseded == ()
    with pytest.raises(CoreConflict, match="correction_item_unavailable"):
        state_step(
            scope,
            second,
            relations=(
                HistoryRelation(target=first.state.source, kind="correction", state_item_ids=(uuid4(),)),
            ),
        )


def test_multi_edge_order_and_provenance_dedup_are_input_order_independent(scope):
    first = source(scope, 1)
    second = source(scope, 2, relations=(HistoryRelation(target=first.ref, kind="dependency"),))
    edge = HistoryRelation(target=second.ref, kind="correction")
    third = source(scope, 3, relations=(edge, edge))
    q = query(scope, explicit=(first.ref,))
    forward = select_history((first, second, third), q)
    assert forward == select_history((third, second, first), q)
    assert len(forward.selected[0].edges) == 2
