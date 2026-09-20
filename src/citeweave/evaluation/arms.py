"""Frozen evaluation-only arm policies; no new public query profiles."""

import json
from copy import deepcopy

from citeweave.evidence_selection import select_evidence
from citeweave.profiles import expand_context, query_profile

ARM_REVISION = "d1-frozen-arms-v1"
ARMS = {
    "B0": dict(build="legacy-glyph-large-v1", evidence="legacy-m3-context-v1"),
    "B1": dict(build="legacy-glyph-large-v1", evidence="legacy-context-budget6400-v1"),
    "T1": dict(build="telecom-structural-v1", evidence="structural-seed-only-v1", parent_expansion=False),
    "T2": dict(build="telecom-structural-v1", evidence="structural-parent-v1", parent_expansion=True),
}


def legacy_pack(chunks, question, tokenizer, policy):
    # Exactly the legacy product's user-message serialization, including question.
    encoded = json.dumps(
        {
            "question": question,
            "evidence": [{"label": f"E{n}", "text": c.text} for n, c in enumerate(chunks, 1)],
        },
        ensure_ascii=False,
    )
    return dict(
        policy=policy,
        prompt_json=encoded,
        serialized_chars=len(encoded),
        serialized_tokens=tokenizer.count([encoded])[0]["bge"],
        spans=[
            dict(label=f"E{n}", evidence_id=str(c.id), version_id=str(c.version_id))
            for n, c in enumerate(chunks, 1)
        ],
    )


def budget_legacy(seeds, pool, question, tokenizer):
    """Same geometric traversal; apply all three gates to each whole-span proposal."""
    profile = dict(query_profile("m3-context"), max_evidence_chars=6400, max_evidence_spans=96)
    page_order = {
        key: i
        for i, key in enumerate(
            dict.fromkeys((str(c.version_id), c.evidence["boxes"][0]["page_index"]) for c in seeds)
        )
    }

    def ordered(chunks):
        def key(c):
            box = c.evidence["boxes"][0]
            return (
                page_order[(str(c.version_id), box["page_index"])],
                box["top"],
                box["left"],
                c.evidence["start_offset"],
                str(c.id),
            )

        return sorted(chunks, key=key)

    def accepts(chunks):
        if len(chunks) > 96:
            return False
        pack = legacy_pack(ordered(chunks), question, tokenizer, ARMS["B1"]["evidence"])
        return pack["serialized_chars"] <= 6400 and pack["serialized_tokens"] <= 2048

    admitted = []
    for seed in seeds:
        if accepts([*admitted, seed]):
            admitted.append(seed)
    chunks, origins = expand_context(admitted, pool, profile, accept=accepts)
    pack = legacy_pack(chunks, question, tokenizer, ARMS["B1"]["evidence"])
    if pack["serialized_chars"] > 6400 or pack["serialized_tokens"] > 2048 or len(chunks) > 96:
        raise ValueError("B1_serialized_budget")
    pack["context_origins"] = origins
    return chunks, pack


def structural_pack(inputs, *, parent_expansion, rrf_only=False):
    """Re-execute selection from the same healthy pre-selection BGE result."""
    if inputs["degraded"]:
        raise ValueError("arm_requires_healthy_bge")
    values = dict(inputs, candidates=deepcopy(inputs["candidates"]))
    if rrf_only:
        values["ordered"] = sorted(values["ordered"], key=lambda i: values["candidates"][i].rrf_rank)
    chunks, pack = select_evidence(**values, parent_expansion=parent_expansion)
    return chunks, pack, [c.model_dump(mode="json") for c in values["candidates"].values()]


def retrieval_identity(candidates):
    """Exclude evidence selection fields; retain every branch and real BGE score/rank."""
    keys = (
        "candidate_id",
        "document_version_id",
        "version_id",
        "retrieval",
        "rrf_rank",
        "rrf_score",
        "rerank_input_rank",
        "reranker_rank",
        "reranker_score",
        "bge",
        "pool_reason",
    )
    return sorted(
        [{k: c[k] for k in keys if k in c} for c in candidates if c.get("retrieval")],
        key=lambda c: c["candidate_id"],
    )
