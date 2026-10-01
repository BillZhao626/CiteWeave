"""Original L1 diagnostic of an unresolved R arm boundary, not DEV execution.

No D/G cases, files, provider, database or Qdrant are loaded. These tests expose
existing selector behavior; they choose neither interpretation as the R contract.
"""

from uuid import UUID

from test_conversation_history import source

from citeweave.conversation_contract import HistoryRelation, ResolvedSignals, Scope
from citeweave.conversation_history import HistoryQuery, select_history


def correction_boundary():
    scope = Scope(kb_id=UUID(int=9001), version_ids=(UUID(int=9002),))
    signals = ResolvedSignals(task="original-lattice-diagnostic", entities=("Lattice",))
    old = source(scope, 1, signals=signals, origins=(), question="Use Lattice release amber.")
    noise = source(scope, 2, origins=("A",), question="Unrelated display task.")
    correction = source(
        scope,
        3,
        signals=signals,
        origins=("A",),
        question="Correct the earlier Lattice choice to release violet.",
        relations=(HistoryRelation(target=old.ref, kind="correction"),),
    )
    query = HistoryQuery(scope=scope, expected_head=correction.acceptance.id, signals=signals)
    return old, noise, correction, query


def test_strict_recent_members_cannot_silently_split_correction_group():
    _, noise, correction, query = correction_boundary()
    result = select_history((noise, correction), query)
    assert result.failure == "incomplete_group"
    assert result.search_incomplete
    assert not result.selected and not result.state_projection


def test_recent_roots_with_provenance_closure_recover_old_member_without_b():
    old, noise, correction, query = correction_boundary()
    result = select_history((old, noise, correction), query)
    assert result.failure is None
    assert len(result.selected) == 1
    group = result.selected[0]
    assert {s.ref for s in group.sources} == {old.ref, correction.ref}
    assert group.superseded == (old.ref,)
    assert group.origins == ("A",)
    assert not result.state_projection
    assert old.ref not in result.a_inputs
    # The old member is provenance, not an active hypothesis or Evidence.
    assert result.authority == "contextual_intent_not_evidence"
