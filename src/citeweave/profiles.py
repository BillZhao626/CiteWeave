"""Allowlisted query-only revisions; indexing and immutable evidence remain unchanged."""

from typing import Literal

QueryProfile = Literal[
    "m2", "m3-dedup", "m3-context", "m3-answer", "m3-candidates40", "m3-parent", "m3-bge-dense"
]
JudgeProfile = Literal["judge-v1", "judge-v2", "judge-v3", "judge-v4"]
DEFAULT_PROFILE: QueryProfile = "m3-context"
PROFILES = {
    "m2": dict(candidate_dedup="none", answer_prompt="answer-v1"),
    "m3-dedup": dict(candidate_dedup="version-whitespace-v1", answer_prompt="answer-v1"),
    "m3-context": dict(
        candidate_dedup="none",
        answer_prompt="answer-v1",
        neighbor_radius=3,
        max_evidence_spans=30,
        max_evidence_chars=3200,
        max_vertical_distance=0.06,
        max_left_distance=0.15,
    ),
}
PROFILES["m3-answer"] = dict(PROFILES["m3-context"], answer_prompt="answer-v2")
PROFILES["m3-candidates40"] = dict(PROFILES["m3-context"], rerank_limit=40)
PROFILES["m3-bge-dense"] = dict(PROFILES["m3-context"], embedding_key="bge-m3")
PROFILES["m3-parent"] = dict(
    PROFILES["m3-context"],
    context_strategy="geometry-paragraph-v1",
    parent_max_chars=800,
    parent_max_members=12,
    parent_max_gap=0.009,
    parent_max_indent=0.055,
)


def query_profile(identity):
    if identity not in PROFILES:
        raise ValueError("unknown_query_profile")
    return dict(PROFILES[identity])


def candidate_cutoff(ranked, traces, limit, deduplicate):
    """Keep the first ranked exact text per version; never rewrite evidence identity."""
    seen, selected = {}, []
    for identity, score in ranked:
        candidate = traces[identity]
        key = (candidate["document_version_id"], " ".join(candidate["text"].split()))
        if deduplicate and key in seen:
            candidate["duplicate_of"] = seen[key]
            continue
        seen[key] = identity
        if len(selected) < limit:
            selected.append((identity, score))
            candidate["rerank_input_rank"] = len(selected)
    return selected


def expand_context(seeds, pool, profile):
    """Bounded neighboring ORIGINAL spans; no synthesized quote or changed identity."""

    def page_key(chunk):
        box = chunk.evidence["boxes"][0]
        return str(chunk.version_id), box["page_index"]

    def position(chunk):
        box = chunk.evidence["boxes"][0]
        return box["top"], box["left"], chunk.evidence["start_offset"], str(chunk.id)

    pages = {}
    for chunk in pool:
        pages.setdefault(page_key(chunk), []).append(chunk)
    for chunks in pages.values():
        chunks.sort(key=position)
    chosen, origins = {str(c.id): c for c in seeds}, {}
    chars = sum(len(c.text) for c in chosen.values())
    for distance in range(1, profile["neighbor_radius"] + 1):
        for seed in seeds:
            page = pages[page_key(seed)]
            index = next(i for i, c in enumerate(page) if c.id == seed.id)
            for at in (index + distance, index - distance):
                if not 0 <= at < len(page):
                    continue
                chunk = page[at]
                identity = str(chunk.id)
                if identity in chosen:
                    continue
                seed_box, box = seed.evidence["boxes"][0], chunk.evidence["boxes"][0]
                if (
                    abs(box["top"] - seed_box["top"]) > profile["max_vertical_distance"]
                    or abs(box["left"] - seed_box["left"]) > profile["max_left_distance"]
                ):
                    continue
                if (
                    len(chosen) >= profile["max_evidence_spans"]
                    or chars + len(chunk.text) > profile["max_evidence_chars"]
                ):
                    continue
                chosen[identity], origins[identity] = chunk, str(seed.id)
                chars += len(chunk.text)
    page_order = {key: i for i, key in enumerate(dict.fromkeys(page_key(c) for c in seeds))}
    return sorted(chosen.values(), key=lambda c: (page_order[page_key(c)], *position(c))), origins
