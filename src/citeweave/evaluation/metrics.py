"""Binary relevance metrics with explicit undefined denominators and duplicate handling."""

import math


def ranking_metrics(ranking: list[str], relevant: set[str], k: int) -> dict:
    if k < 1:
        raise ValueError("k_must_be_positive")
    ranked = list(dict.fromkeys(ranking))[:k]
    if not relevant:
        return dict(hit=None, recall=None, mrr=None, ndcg=None, k=k, relevant_count=0)
    hits = [i for i, identity in enumerate(ranked, 1) if identity in relevant]
    dcg = sum(1 / math.log2(i + 1) for i in hits)
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(relevant)) + 1))
    return dict(
        hit=int(bool(hits)),
        recall=len(hits) / len(relevant),
        mrr=1 / hits[0] if hits else 0,
        ndcg=dcg / ideal,
        k=k,
        relevant_count=len(relevant),
    )


def coverage(ids, relevant):
    return len(set(ids) & set(relevant)) / len(relevant) if relevant else None


def mean_defined(values):
    values = [v for v in values if v is not None]
    return dict(mean=sum(values) / len(values) if values else None, denominator=len(values))


def grounded_citations(citations, gold_ids, validate):
    """Structural grounding is independently checked, and does NOT imply semantic support.

    Precision is relevance-to-annotated-gold among independently grounded citations.
    Alternate valid supporting spans absent from the finite gold can score zero.
    """
    checks = []
    for citation in citations:
        try:
            detail = validate(citation)
        except Exception as exc:
            detail = dict(version=False, page=False, quote=False, grounded=False, error=type(exc).__name__)
        checks.append(dict(evidence_id=citation["evidence_id"], **detail))
    accepted = {c["evidence_id"] for c in checks if c["grounded"]}
    relevant = accepted & set(gold_ids)
    return dict(
        precision=len(relevant) / len(checks) if checks else None,
        recall=len(relevant) / len(gold_ids) if gold_ids else None,
        grounded_rate=sum(c["grounded"] for c in checks) / len(checks) if checks else None,
        checks=checks,
    )
