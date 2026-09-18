"""Validate submitted review assets before an atomic, non-overwriting import."""

import re
from collections import Counter

LABELS = {
    "正确完整": "correct_complete",
    "部分正确": "partial",
    "错误或不当拒答": "incorrect_or_unjustified_refusal",
    "无法判断": "unassessable",
}


def validate_reviews(document, markdown, dataset, digest, artifact):
    run = artifact["evaluation"]
    if document["run_id"] != run["id"] or document["dataset_sha256"] != digest:
        raise ValueError("review_identity_mismatch")
    if run["dataset_hash"] != digest or document["split"] != "dev":
        raise ValueError("review_scope_mismatch")
    expected = {c["case_id"]: c for c in dataset["cases"] if c["split"] == "dev"}
    saved = {c["case_id"]: c for c in artifact["cases"]}
    reviews = document["reviews"]
    ids = ["cw-public-" + c["case_id"] for c in reviews]
    if len(ids) != 24 or len(set(ids)) != 24 or set(ids) != set(expected):
        raise ValueError("review_dev_membership_mismatch")
    sections = re.findall(r"^## (\d{3}) · ([^\n]+)\n(.*?)(?=^## |\Z)", markdown, re.M | re.S)
    if len(sections) != 24 or len({i for i, _, _ in sections}) != 24:
        raise ValueError("review_markdown_membership_mismatch")
    sections = {i: (q.strip(), body) for i, q, body in sections}
    for review, identity in zip(reviews, ids, strict=True):
        case, result = expected[identity], saved[identity]
        if result["eval_run_id"] != run["id"] or result["result"]["split"] != "dev":
            raise ValueError("review_case_run_mismatch")
        if result["result"]["question"] != case["question"]:
            raise ValueError("review_question_mismatch")
        label = review["human_review"]
        if label not in LABELS or not review["reason"].strip():
            raise ValueError("review_label_invalid")
        question, body = sections[review["case_id"]]
        match = re.findall(r"^- 总体结论：([^\n]+)", body, re.M)
        index = re.findall(r"^\| " + review["case_id"] + r" \| [^\n]+ \| ([^|]+) \|$", markdown, re.M)
        if question != case["question"] or match != [label] or index != [label]:
            raise ValueError("review_markdown_label_mismatch")
    return {
        identity: dict(review, verdict=LABELS[review["human_review"]])
        for identity, review in zip(ids, reviews, strict=True)
    }


def agreement(cases):
    """Exact label agreement, not correctness-score agreement or universal accuracy."""
    entries = [
        dict(
            case_id=c["case_id"],
            question_type=c["result"]["question_type"],
            human=c["human_review"]["verdict"],
            judge=(c["judge"].get("scores") or {}).get("verdict", "unavailable"),
            judge_method=c["judge"].get("method", "unknown"),
            refusal_related=(c["result"].get("answer") or {}).get("text") == "证据不足，无法回答。"
            or c["human_review"]["verdict"] == "incorrect_or_unjustified_refusal",
        )
        for c in cases
        if c.get("human_review")
    ]

    def summary(values):
        count = sum(v["human"] == v["judge"] for v in values)
        return dict(agree=count, count=len(values), rate=count / len(values) if values else None)

    return dict(
        **summary(entries),
        distribution=dict(Counter(c["human"] for c in entries)),
        disagreement_ids=[c["case_id"] for c in entries if c["human"] != c["judge"]],
        confusion_matrix={
            h: dict(Counter(c["judge"] for c in entries if c["human"] == h)) for h in LABELS.values()
        },
        by_question_type={
            t: summary([c for c in entries if c["question_type"] == t])
            for t in sorted({c["question_type"] for c in entries})
        },
        by_judge_method={
            m: summary([c for c in entries if c["judge_method"] == m])
            for m in sorted({c["judge_method"] for c in entries})
        },
        refusal_related=summary([c for c in entries if c["refusal_related"]]),
        refusal_group_definition="Exact full refusal or human incorrect_or_unjustified_refusal (combined label; not all are proven refusal failures).",
        comparisons=entries,
        limitation="Current 24 Dev, owner-submitted AI-assisted material review; not independent human annotation or general Judge accuracy.",
    )
