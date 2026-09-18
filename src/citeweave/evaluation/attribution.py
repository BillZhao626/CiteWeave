"""Observable stage losses are distinct from semantic sufficiency and generation blame."""

from enum import StrEnum


class Category(StrEnum):
    RETRIEVAL_NO_RECALL = "RETRIEVAL_NO_RECALL"
    CANDIDATE_OR_FUSION_LOSS = "CANDIDATE_OR_FUSION_LOSS"
    EVIDENCE_SELECTION_LOSS = "EVIDENCE_SELECTION_LOSS"
    GENERATION_ERROR = "GENERATION_ERROR"
    INCOMPLETE_ANSWER = "INCOMPLETE_ANSWER"
    IMPROPER_REFUSAL = "IMPROPER_REFUSAL"
    SEMANTIC_CITATION_ERROR = "SEMANTIC_CITATION_ERROR"
    PHYSICAL_CITATION_ERROR = "PHYSICAL_CITATION_ERROR"


def attribute(case, answerable, sufficient=None):
    result, human = case["result"], case.get("human_review") or {}
    scores = case["judge"].get("scores") or {}
    verdict = human.get("verdict") or scores.get("verdict")
    evidence = result["assessment"]["evidence"]
    categories, observations = [], []
    if evidence["initial"] == 0:
        categories.append(Category.RETRIEVAL_NO_RECALL)
    elif evidence["initial"] is not None and evidence["initial"] < 1:
        observations.append("partial_initial_finite_gold_coverage")
    if evidence["initial"] is not None:
        if evidence["rerank_input"] < evidence["initial"]:
            categories.append(Category.CANDIDATE_OR_FUSION_LOSS)
        if evidence["final"] < evidence["rerank_input"]:
            categories.append(Category.EVIDENCE_SELECTION_LOSS)
        if evidence["final"] < 1:
            observations.append("incomplete_final_finite_gold_is_not_proof_of_semantic_insufficiency")
    text = (result.get("answer") or {}).get("text", "")
    if answerable and text == "证据不足，无法回答。":
        categories.append(Category.IMPROPER_REFUSAL)
    if verdict == "partial":
        categories.append(Category.INCOMPLETE_ANSWER)
    if sufficient is True and verdict in {"partial", "incorrect_or_unjustified_refusal"}:
        categories.append(Category.GENERATION_ERROR)
    checks = result["assessment"]["citation"]["checks"]
    if any(not c["grounded"] for c in checks):
        categories.append(Category.PHYSICAL_CITATION_ERROR)
    claims = scores.get("claims", [])
    if any(c["support"] < 1 for c in claims) or human.get("evidence_support") in {"部分", "不支持"}:
        categories.append(Category.SEMANTIC_CITATION_ERROR)
    return dict(
        case_id=case["case_id"],
        verdict=verdict,
        categories=categories,
        observations=observations,
        evidence=evidence,
        supplied_evidence_sufficient=sufficient,
        root_cause="generation_with_reviewed_sufficient_context"
        if Category.GENERATION_ERROR in categories
        else "stage_loss_observed_semantic_root_cause_unverified",
        limitation="Non-exclusive observations. Initial partial coverage differs from no recall; finite gold alone cannot establish generation error.",
    )
