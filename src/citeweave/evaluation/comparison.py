"""Paired, same-rubric comparisons with failures and denominators kept explicit."""

from collections import Counter

from citeweave.evaluation.reporting import aggregate

DIMENSIONS = ("correctness", "completeness", "faithfulness", "relevancy", "refusal_correctness")


def compare(baseline, candidate, old_cases, new_cases):
    if (baseline.dataset_hash, baseline.split) != (candidate.dataset_hash, candidate.split):
        raise ValueError("comparison_dataset_or_split_mismatch")
    if baseline.runtime_config["judge_prompt_sha256"] != candidate.runtime_config["judge_prompt_sha256"]:
        raise ValueError("comparison_judge_mismatch")
    old, new = {c.case_id: c for c in old_cases}, {c.case_id: c for c in new_cases}
    if set(old) != set(new) or not old:
        raise ValueError("comparison_membership_mismatch")
    pairs = []
    for identity in sorted(old):
        left, right = old[identity], new[identity]
        changes = {}
        for metric in DIMENSIONS:
            before = (left.judge.get("scores") or {}).get(metric)
            after = (right.judge.get("scores") or {}).get(metric)
            changes[metric] = (
                "unavailable"
                if before is None or after is None
                else "win"
                if after > before
                else "loss"
                if after < before
                else "tie"
            )

        def view(case):
            result = case.result
            return dict(
                query_run_id=str(case.query_run_id),
                answer=(result.get("answer") or {}).get("text"),
                evidence=result.get("selected_evidence"),
                coverage=result.get("assessment", {}).get("evidence"),
                scores=case.judge.get("scores"),
                judge_status=case.judge.get("status"),
                physical_citation=result.get("assessment", {}).get("citation"),
                latency_ms=result.get("latency_ms"),
                estimated_yuan=result.get("estimated_yuan"),
            )

        pairs.append(
            dict(
                case_id=identity,
                question=right.result.get("question"),
                question_type=right.result.get("question_type"),
                changes=changes,
                baseline=view(left),
                candidate=view(right),
                verdict_flip=(left.judge.get("scores") or {}).get("verdict")
                != (right.judge.get("scores") or {}).get("verdict"),
            )
        )
    return dict(
        baseline_id=str(baseline.id),
        candidate_id=str(candidate.id),
        dataset_hash=baseline.dataset_hash,
        split=baseline.split,
        baseline=aggregate(old_cases),
        candidate=aggregate(new_cases),
        paired={key: dict(Counter(p["changes"][key] for p in pairs)) for key in DIMENSIONS},
        new_regression_ids=[
            p["case_id"]
            for p in pairs
            if any(p["changes"][key] == "loss" for key in ("correctness", "completeness", "faithfulness"))
        ],
        same_versions=baseline.versions == candidate.versions,
        configurations=dict(baseline=baseline.runtime_config, candidate=candidate.runtime_config),
        cases=pairs,
        limitations=[
            "Small benchmark, single generated answer and fallible Judge per configuration; no general accuracy claim.",
            "Replayed baseline query latency/cost describe the source run; replay's incremental API spend is Judge cost only.",
            "No candidate human labels inferred from baseline. Undefined comparisons remain unavailable.",
            "Physical grounding, finite annotated-gold overlap and sentence-unit semantic support are distinct.",
        ],
    )
