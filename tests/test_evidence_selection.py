"""Original miniature structures; no public PDF text or retrieval quality claims."""

from types import SimpleNamespace as NS

import pytest

from citeweave.evidence_selection import merge_atoms, seed_order, select_evidence, union_chars
from citeweave.query_evidence import StructuralCandidate


class Counter:
    def count(self, texts):
        return [{"bge": len(t) // 4 + 1} for t in texts]


def fixture(confidence="VERIFIED_RULE", sources=2, text_size=30):
    atoms, children, neighbors, candidates = {}, {}, {}, {}
    bindings = [
        NS(version_id=f"v{s}", document_id=f"d{s}", filename=f"original-{s}.pdf") for s in range(sources)
    ]
    for s in range(sources):
        ids = [f"a{s}-{n}" for n in range(5)]
        for n, eid in enumerate(ids):
            atoms[eid] = NS(
                id=eid,
                version_id=f"v{s}",
                text="x" * text_size,
                evidence=dict(
                    block_id=f"b{n}",
                    start_offset=0,
                    end_offset=text_size,
                    boxes=[{"page_index": 0 if n < 3 else 1}],
                ),
            )
        parent = NS(id=f"p{s}", heading_ids=[ids[0]], content_ids=ids, confidence=confidence)
        for ordinal in range(3):
            identity = f"c{s}-{ordinal}"
            child = dict(
                row=NS(id=identity, parent_node_id=parent.id, ordinal=ordinal),
                parent=parent,
                span_ids=[ids[ordinal + 1]],
                binding=bindings[s],
            )
            (children if ordinal == 1 else neighbors)[identity] = child
            if ordinal == 1:
                candidates[identity] = StructuralCandidate(
                    candidate_id=identity,
                    child_id=identity,
                    document_id=f"d{s}",
                    version_id=f"v{s}",
                    artifact_id=f"ar{s}",
                    parent_id=parent.id,
                    section_path=[],
                    evidence_ids=child["span_ids"],
                    retrieval=[],
                    rrf_rank=s + 1,
                    rrf_score=0.1,
                    pool_reason="top20",
                )
    snapshot = NS(
        evidence_mode="compare" if sources > 1 else "single",
        requested_documents=[f"d{s}" for s in range(sources)],
        bindings=bindings,
    )
    repo = NS(
        snapshot=snapshot, neighbors=lambda seeds: neighbors, atoms=lambda ids: {i: atoms[i] for i in ids}
    )
    return list(children), candidates, children, repo, atoms


@pytest.mark.parametrize(
    "confidence,cross,expanded",
    [("VERIFIED_RULE", True, True), ("HEURISTIC", False, True), ("FALLBACK_PAGE", False, False)],
)
def test_real_parent_heading_sibling_confidence_and_original_ids(confidence, cross, expanded):
    ordered, candidates, children, repo, _ = fixture(confidence, sources=1)
    for atom in repo.atoms(["a0-0", "a0-1", "a0-3"]).values():
        atom.text = "short"
        atom.evidence["end_offset"] = 5
    chunks, pack = select_evidence(ordered, candidates, children, repo, Counter())
    assert all(str(c.id) == span.evidence_id for c, span in zip(chunks, pack.spans, strict=True))
    assert any(s.origin != "seed" for s in pack.spans) == expanded
    assert any(s.cross_page for s in pack.spans) == cross
    assert all("rank" not in s.model_dump() and "score" not in s.model_dump() for s in pack.spans)
    assert all(s.evidence_id != candidates[ordered[0]].candidate_id for s in pack.spans)
    if expanded:
        assert any(s.origin == "heading" for s in pack.spans)


def test_compare_keeps_same_text_across_sources_and_gap_is_explicit():
    ordered, candidates, children, repo, _ = fixture()
    repo.snapshot.requested_documents += ["missing"]
    _, pack = select_evidence(ordered, candidates, children, repo, Counter())
    assert pack.source_coverage.selected == ["d0", "d1"]
    assert pack.source_coverage.missing == ["missing"]
    assert pack.source_coverage.coverage_unmet
    assert all(c.selection_reason == "source_quota_top12" for c in candidates.values())
    assert '"source_gaps":["missing"]' in pack.prompt_json


def test_degraded_has_only_seeds_and_no_fake_bge():
    ordered, candidates, children, repo, _ = fixture()
    _, pack = select_evidence(
        ordered, candidates, children, repo, Counter(), "degraded_reranker_unavailable", "model_timeout"
    )
    assert pack.degraded and pack.added_chars == 0
    assert all(s.origin == "seed" for s in pack.spans)
    assert all(c.bge is None for c in candidates.values())


@pytest.mark.parametrize("mode,limit", [("single", 4), ("compare", 6)])
def test_seed_count_limits_and_no_fixed_evidence_count(mode, limit):
    ordered, candidates, children, repo, _ = fixture(sources=8)
    repo.snapshot.evidence_mode = mode
    _, pack = select_evidence(
        ordered, candidates, children, repo, Counter(), "degraded_reranker_unavailable", "circuit_open"
    )
    assert len(pack.seed_child_ids) == limit
    assert sum(c.selection_reason == "seed_count_limit" for c in candidates.values()) == 8 - limit


def test_union_and_existing_span_containment_without_clipping():
    _, _, _, _, atoms = fixture(sources=1)
    small = NS(
        id="small", version_id="v0", text="xx", evidence=dict(block_id="b1", start_offset=2, end_offset=4)
    )
    atoms["small"] = small
    chosen, lineage = merge_atoms(["small"], ["a0-1"], atoms)
    assert chosen == ["a0-1"] and lineage == [{"evidence_id": "small", "covered_by": "a0-1"}]
    assert union_chars([small, atoms["a0-1"]]) == 30


def test_hard_char_token_span_budgets_no_partial_seed():
    ordered, candidates, children, repo, _ = fixture(sources=8, text_size=950)
    _, pack = select_evidence(ordered, candidates, children, repo, Counter())
    assert pack.seed_chars <= 3200 and pack.seed_tokens <= 1024 and pack.seed_spans <= 64
    assert pack.serialized_chars == len(pack.prompt_json) <= 6400
    assert pack.serialized_tokens <= 2048 and len(pack.spans) <= 96
    assert pack.added_chars <= min(pack.seed_chars, 3200)
    assert any(c.selection_reason == "evidence_budget" for c in candidates.values())
    assert all(len(c["span_ids"]) == 1 for c in children.values())


def test_fully_covered_child_is_rejected_duplicate():
    ordered, candidates, children, repo, _ = fixture(sources=1)
    duplicate = candidates[ordered[0]].model_copy(
        update={"candidate_id": "duplicate", "child_id": "duplicate"}
    )
    candidates["duplicate"] = duplicate
    children["duplicate"] = children[ordered[0]]
    _, pack = select_evidence(ordered + ["duplicate"], candidates, children, repo, Counter())
    assert duplicate.selection_reason == "duplicate_coverage" and len(pack.seed_child_ids) == 1


def test_compare_quota_does_not_pull_a_source_from_rank_thirteen():
    ordered = [str(i) for i in range(13)]
    candidates = {i: NS(document_id="first" if n < 12 else "second") for n, i in enumerate(ordered)}
    snapshot = NS(evidence_mode="compare", requested_documents=["first", "second"])
    decisions = seed_order(ordered, candidates, snapshot)
    assert decisions[0] == ("0", "source_quota_top12")
    assert decisions[-1] == ("12", "rank_order")
    assert sum(reason == "source_quota_top12" for _, reason in decisions) == 1
