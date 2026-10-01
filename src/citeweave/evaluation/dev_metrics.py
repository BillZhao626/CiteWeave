"""Frozen descriptive denominators; semantic annotations stay human inputs."""

import json
from statistics import median

QUALITY = (
    "evidence_support",
    "correctness",
    "completeness",
    "relevance",
    "coreference",
    "clarification",
    "rewrite_fidelity",
    "correction_supersession",
    "topic_shift_return",
    "evidence_insufficient",
    "behavior_completion",
)
CRITICAL = (
    "memory_evidence",
    "scope",
    "stale_acceptance",
    "duplicate_acceptance",
    "rewrite_drift",
    "draft_final",
)


def ratio(numerator, denominator):
    return dict(
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator if denominator else None,
        status="DEFINED" if denominator else "N/A",
    )


def coverage(found, required):
    return ratio(len(set(found) & set(required)), len(set(required)))


def groups_covered(groups, materialized):
    materialized = set(materialized)
    return {g.id for g in groups if any(set(alt) <= materialized for alt in g.alternatives)}


def history_metrics(view, receipt, source_names, *, token_count=None):
    history = receipt.get("history") or {}

    def names(groups):
        return {
            source_names[s["acceptance"]["id"]]
            for g in groups
            for s in g["sources"]
            if s["acceptance"]["id"] in source_names
        }

    candidates = history.get("candidates", [])
    selected = history.get("selected", [])
    # On incomplete search, do not credit partly materialized atomic groups.
    if history.get("search_incomplete") or history.get("failure"):
        candidates, selected = [], []

    def branch_members(branch):
        return {
            source_names[s["acceptance"]["id"]]
            for g in candidates
            for s in g["sources"]
            if branch in s["origins"] and s["acceptance"]["id"] in source_names
        }

    a, b = branch_members("A"), branch_members("B")
    union = names(candidates)
    chosen = names(selected)
    interpreted = {
        (source_names.get(s["acceptance_id"]))
        for s in (receipt.get("interpretation") or {}).get("sources", [])
    } - {None}
    generation = set()
    serialized_history = []
    for call in receipt.get("calls", []):
        serialized_history.extend(call.get("context", {}).get("history", []))
        generation.update(
            source_names.get(h["source"]["acceptance_id"]) for h in call.get("context", {}).get("history", [])
        )
    generation.discard(None)
    required = {g.id for g in view.required_history}
    found = groups_covered(view.required_history, union)
    final = groups_covered(view.required_history, generation)
    old = [g for g in view.required_history if g.old]
    irrelevant = set(view.irrelevant_history)
    final_groups = [{source_names.get(s["acceptance"]["id"]) for s in g["sources"]} for g in selected]
    final_groups = [g for g in final_groups if g & generation]
    token_fraction = None
    if token_count is not None:

        def count(items):
            return token_count(json.dumps(items, ensure_ascii=False, separators=(",", ":"))) if items else 0

        unwanted = [
            h for h in serialized_history if source_names.get(h["source"]["acceptance_id"]) in irrelevant
        ]
        token_fraction = ratio(count(unwanted), count(serialized_history))
    return dict(
        required_candidate={
            "A": coverage(groups_covered(view.required_history, a), required),
            "B": coverage(groups_covered(view.required_history, b), required),
            "union": coverage(found, required),
        },
        candidate_raw_sources=sorted(union),
        selected_raw_sources=sorted(chosen),
        interpretation_coverage=coverage(groups_covered(view.required_history, interpreted), required),
        generation_coverage=coverage(final, required),
        retention=ratio(len(final & found), len(found)),
        intrusion=ratio(sum(bool(g & irrelevant) for g in final_groups), len(final_groups)),
        no_history_need_intrusion=int(not view.required_history and bool(generation)),
        old_candidate_recovery=ratio(len(groups_covered(old, union)), len(old)),
        old_final_recovery=ratio(len(groups_covered(old, generation)), len(old)),
        old_recovery_B=ratio(len(groups_covered(old, b)), len(old)),
        noise_rejection=ratio(len(irrelevant - generation), len(irrelevant)),
        state_coverage="SEPARATE_NOT_RAW_HISTORY",
        state_items=len(history.get("state_projection", [])),
        state_intent_items_used=len(
            {
                e["item"]["id"]
                for c in receipt.get("calls", [])
                for e in c.get("context", {}).get("working_state", [])
            }
        ),
        incomplete=bool(history.get("search_incomplete")),
        failure=history.get("failure"),
        correction_supersession="OWNER_REVIEW_REQUIRED",
        topic_shift_return="OWNER_REVIEW_REQUIRED",
        intrusion_token_fraction=token_fraction,
        intrusion_token_reason="Standalone serialized history-array tokens, not additive full-request usage or historical source cost. Empty history is N/A.",
    )


def hard_gates(*, accepted_citations, valid_citations, violations, verified=False):
    if (
        type(accepted_citations) is not int
        or type(valid_citations) is not int
        or not 0 <= valid_citations <= accepted_citations
    ):
        raise ValueError("citation_counts_invalid")
    if set(violations) != set(CRITICAL) or any(type(v) is not int or v < 0 for v in violations.values()):
        raise ValueError("critical_violation_counts_invalid")
    bad = valid_citations != accepted_citations or any(violations.values())
    return dict(
        status="FAIL" if bad else "PASS" if verified else "NOT_VERIFIED",
        citations=ratio(valid_citations, accepted_citations),
        accepted_violations=violations,
    )


def citation_checks(data, view, receipt):
    """Independent binding check against original immutable fixture sources.

    Full canonical fixture spans only. Real ingestion requires its own READY
    bindings and authorized resolver; this result cannot certify real Qdrant.
    """
    from citeweave.evaluation.dev_fixtures import FixtureRepository
    from citeweave.evidence import Block, EvidenceSpan, resolve_span
    from citeweave.schemas import Citation

    repo = FixtureRepository(data)
    result = (receipt.get("acceptance") or {}).get("result", receipt.get("evaluation_output", {}))
    citations = result.get("answer", {}).get("citations", [])
    allowed = {str(s.version_id) for s in data.sources if s.id in view.scope}
    checks = []
    for raw in citations:
        try:
            c = Citation.model_validate(raw)
            if str(c.document_version_id) not in allowed or c.span.scope.revision_id != c.document_version_id:
                raise ValueError("scope_denied")
            atom = repo.atoms.get(str(c.evidence_id))
            if atom is None or c.evidence_id != c.span.id:
                raise ValueError("fixture_evidence_identity_mismatch")
            block = Block.model_validate(atom.block)
            resolve_span(EvidenceSpan.model_validate(c.span), block, block.scope)
            checks.append(dict(evidence_id=str(c.evidence_id), valid=True))
        except (ValueError, KeyError) as exc:
            checks.append(dict(valid=False, error_type=type(exc).__name__))
    return dict(
        physical_validity=ratio(sum(c["valid"] for c in checks), len(checks)),
        checks=checks,
        semantic_support=None,
        verification_scope="ORIGINAL_FIXTURE_BINDINGS_ONLY_NOT_REAL_INGESTION",
    )


def aggregate_metrics(planned, receipts, reviews=None):
    """Reviews are external inputs, never generated from fixture expectations."""
    reviews = reviews or {}
    ids = [(r["view_id"], r["arm_id"]) for r in receipts]
    if len(set(ids)) != len(ids) or not set(ids) <= set(planned):
        raise ValueError("receipt_membership_invalid")
    timings = [r["latency_ms"] for r in receipts if r.get("latency_ms") is not None]
    resources = provider_resources(receipts)
    quality = {}
    for dimension in QUALITY:
        values = [reviews.get(key, {}).get(dimension) for key in planned]
        evaluated = [v for v in values if isinstance(v, (float, int)) and not isinstance(v, bool)]
        quality[dimension] = dict(
            planned=len(planned),
            attempted=len(receipts),
            evaluable=len(evaluated),
            missing=sum(v is None for v in values),
            na=sum(v == "N/A" for v in values),
            mean=sum(evaluated) / len(evaluated) if evaluated else None,
        )
    return dict(
        planned=len(planned),
        attempted=len(receipts),
        not_run=len(planned) - len(receipts),
        completed_transport=sum(r["status"] == "COMPLETED" for r in receipts),
        quality=quality,
        external_calls=sum(r.get("external_calls", 0) for r in receipts),
        calls_by_purpose={
            p: sum(c["purpose"] == p for r in receipts for c in r.get("calls", []))
            for p in ("interpretation", "generation")
        },
        call_kind="FAKE_CALLS_ARE_NOT_PROVIDER_CALLS",
        provider_resources=resources,
        tokens=resources["provider_reported_tokens"],
        estimated_yuan=resources["estimated_yuan"],
        failures=sum(r["status"] in {"GUARD_FAILURE", "FAILED"} for r in receipts),
        unknown=sum(r["status"] == "UNKNOWN" for r in receipts),
        overflow=sum(r.get("error_code") == "conversation_context_overflow" for r in receipts),
        retry=sum(r.get("retry", 0) for r in receipts),
        refetch=sum(r.get("refetch", 0) for r in receipts),
        latency=dict(
            min=min(timings) if timings else None,
            median=median(timings) if timings else None,
            max=max(timings) if timings else None,
            timeout_censored=sum(r.get("timeout_censored", False) for r in receipts),
        ),
        limitations=[
            "Synthetic fake-L1 timing is not provider latency.",
            "Unreviewed semantic outputs remain missing.",
            "Only finite original cases; no population accuracy/statistical significance claim.",
        ],
    )


def provider_resources(receipts):
    real = [
        c
        for r in receipts
        for c in r.get("calls", [])
        if c.get("execution_kind")
        not in {"fake_not_provider_dispatch", "serialization_only_no_provider_dispatch"}
    ]
    totals = {}
    for p in ("interpretation", "generation"):
        calls = [c for c in real if c["purpose"] == p]
        known = [c for c in calls if c.get("provider_usage") is not None]
        totals[p] = dict(
            attempted=len(calls),
            usage_known=len(known),
            usage_unknown=len(calls) - len(known),
            input=sum(c["provider_usage"].get("prompt_tokens", 0) for c in known)
            if all(c["provider_usage"].get("prompt_tokens") is not None for c in known)
            and len(known) == len(calls)
            else None,
            output=sum(c["provider_usage"].get("completion_tokens", 0) for c in known)
            if all(c["provider_usage"].get("completion_tokens") is not None for c in known)
            and len(known) == len(calls)
            else None,
            dispatched=sum(c.get("state") in {"DISPATCHED", "COMPLETE", "UNKNOWN"} for c in calls),
            completed=sum(c.get("state") == "COMPLETE" for c in calls),
            unknown=sum(c.get("state") == "UNKNOWN" for c in calls),
        )
    estimates = [c.get("estimated_yuan") for c in real]
    return dict(
        provider_reported_tokens=totals,
        estimated_yuan=sum(estimates) if all(v is not None for v in estimates) else None,
        actual_charge="NOT_AVAILABLE",
        rate_revisions=sorted({c["rate_revision"] for c in real if c.get("rate_revision")}),
        offline_accounting="Separate request specimens; never provider-reported usage.",
    )


def layered_metrics(data, planned, receipts, reviews=None):
    def layer(views):
        subset = [p for p in planned if p[0] in views]
        return aggregate_metrics(subset, [r for r in receipts if r["view_id"] in views], reviews)

    return dict(
        all_views=layer({v.id for v in data.views}),
        hard=layer({v.id for v in data.views if v.hard}),
        family={f"D{i}": layer({v.id for v in data.views if v.family == f"D{i}"}) for i in range(1, 7)},
        category={c: layer(set(ids)) for c, ids in data.category_coverage.items()},
        macro_rule="Family/category are separate finite strata; overlapping categories are never pooled as independent samples.",
    )
