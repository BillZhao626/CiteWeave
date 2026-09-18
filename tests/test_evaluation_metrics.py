import math

import pytest

from citeweave.evaluation.metrics import coverage, grounded_citations, mean_defined, ranking_metrics


def test_rank_metrics_known_order_and_duplicate_do_not_inflate():
    result = ranking_metrics(["x", "a", "a", "b"], {"a", "b", "c"}, 3)
    assert result["recall"] == 2 / 3
    assert result["mrr"] == 0.5
    assert result["ndcg"] == pytest.approx((1 / math.log2(3) + 0.5) / (1 + 1 / math.log2(3) + 0.5))
    assert ranking_metrics([], {"a"}, 6)["recall"] == 0


def test_undefined_gold_and_failure_denominators_explicit():
    assert ranking_metrics(["a"], set(), 6)["recall"] is None
    assert coverage([], {"a"}) == 0
    assert mean_defined([None, 0, 1]) == {"mean": 0.5, "denominator": 2}
    with pytest.raises(ValueError):
        ranking_metrics([], {"a"}, 0)


def test_id_presence_does_not_prove_citation_grounding():
    def verify(citation):
        if citation["evidence_id"] == "forged":
            raise ValueError("pdf_span_mismatch")
        return dict(version=True, page=True, quote=True, grounded=True)

    result = grounded_citations([{"evidence_id": "a"}, {"evidence_id": "forged"}], {"a", "forged"}, verify)
    assert result["precision"] == 0.5 and result["recall"] == 0.5
    assert result["grounded_rate"] == 0.5


def test_assessment_failure_stays_visible_in_denominator_bad_cases_and_cost():
    from types import SimpleNamespace

    from citeweave.evaluation.reporting import aggregate

    case = SimpleNamespace(
        case_id="failed",
        result={},
        status="FAILED",
        human_review={},
        judge={"status": "FAILED", "error_code": "source_corrupt"},
        judge_estimated_yuan=None,
        judge_reserved_yuan=0,
    )
    report = aggregate([case], {"prior-query": 0.0123})
    assert report["unassessed_failed_count"] == 1
    assert report["answer"]["correctness"] == {"mean": 0, "denominator": 1}
    assert report["answer"]["faithfulness"]["denominator"] == 0
    assert report["bad_cases"] == [{"case_id": "failed", "reasons": ["assessment_failure:source_corrupt"]}]
    assert report["cost"]["query_known_estimated_yuan"] == 0.0123
