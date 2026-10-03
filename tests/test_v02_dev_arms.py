"""Clarified all-member boundary and atomic provenance selection."""

import pytest
from test_v02_dev_readiness import correction_boundary

from citeweave.evaluation.dev_arms import ARM_IDS, arm, select_arm


def test_exact_factor_isolation_and_unapproved_arm_rejection():
    assert ARM_IDS == ("EXISTING_V01_CONTRACT", "cp-r-v1", "cp-a-v1", "cp-ab0-v1")
    r, a, ab = [arm(x) for x in ARM_IDS[1:]]
    assert r.n == a.n == ab.n == 2
    assert (r.state, r.b) == (False, False)
    assert (a.state, a.b) == (True, False)
    assert (ab.state, ab.b, ab.c, ab.k) == (True, True, 8, 2)
    assert r.common_hash == a.common_hash == ab.common_hash
    assert len({r.config_hash, a.config_hash, ab.config_hash}) == 3
    with pytest.raises(ValueError, match="dev_arm_rejected"):
        arm("cp-oracle-diagnostic-v1")


@pytest.mark.parametrize("identity", ARM_IDS[1:3])
def test_r_a_do_not_fetch_old_correction_member(identity):
    old, noise, corrected, query = correction_boundary()
    requested = []

    def fetch(refs):
        requested.extend(refs)
        return tuple(s for s in (old, noise, corrected) if s.ref in refs)

    selected = select_arm(identity, (noise.ref, corrected.ref), (), query, (), fetch)
    assert old.ref not in requested
    assert selected.failure == "incomplete_group"
    assert selected.search_incomplete and not selected.selected


def test_b_admitted_complete_correction_group_gets_b_attribution():
    old, noise, corrected, query = correction_boundary()
    sources = (old, noise, corrected)
    result = select_arm(
        ARM_IDS[3],
        (noise.ref, corrected.ref),
        (corrected.ref,),
        query,
        (),
        lambda refs: tuple(s for s in sources if s.ref in refs),
    )
    assert result.failure is None
    group = result.selected[0]
    assert {s.ref for s in group.sources} == {old.ref, corrected.ref}
    assert "B" in group.origins
