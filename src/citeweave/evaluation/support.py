"""Source-range union projection, independent of retrieval unit boundaries."""

import math
from collections import defaultdict


def contains(ranges, target):
    key = (target["source_id"], target["block_id"])
    end = target["start_offset"]
    for start, stop in sorted(ranges.get(key, [])):
        if start > end:
            break
        if stop > end:
            end = stop
        if end >= target["end_offset"]:
            return True
    return False


def covered_groups(atoms, groups):
    ranges = defaultdict(list)
    for atom in atoms:
        ranges[(atom["source_id"], atom["block_id"])].append((atom["start_offset"], atom["end_offset"]))
    return {
        g["group_id"]
        for g in groups
        if any(all(contains(ranges, r) for r in alternative) for alternative in g["alternatives"])
    }


def group_ranking(ranking, projection, groups, k):
    if k < 1:
        raise ValueError("k_must_be_positive")
    if not groups:
        return dict(hit=None, recall=None, mrr=None, ndcg=None, k=k, relevant_count=0)
    atoms, seen, hits = [], set(), []
    for rank, identity in enumerate(list(dict.fromkeys(ranking))[:k], 1):
        atoms.extend(projection.get(identity, []))
        covered = covered_groups(atoms, groups)
        if covered - seen:
            hits.append(rank)  # binary gain per retrieval position, never repeated support credit
        seen |= covered
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, len(groups)) + 1))
    return dict(
        hit=int(bool(hits)),
        recall=len(seen) / len(groups),
        mrr=1 / hits[0] if hits else 0,
        ndcg=sum(1 / math.log2(i + 1) for i in hits) / ideal,
        k=k,
        relevant_count=len(groups),
    )


def support_coverage(atoms, groups, aspects, required_sources):
    covered = covered_groups(atoms, groups)
    satisfied = sum(set(a["required_groups"]) <= covered for a in aspects)
    ranges = _ranges(atoms)
    supported_sources = {
        r["source_id"]
        for g in groups
        if g["group_id"] in covered
        for alt in g["alternatives"]
        if all(contains(ranges, part) for part in alt)
        for r in alt
    }
    return dict(
        groups=sorted(covered),
        group_coverage=len(covered) / len(groups) if groups else None,
        required_aspect_coverage=satisfied / len(aspects) if aspects else None,
        required_source_coverage=len(supported_sources & set(required_sources)) / len(required_sources)
        if required_sources
        else None,
    )


def _ranges(atoms):
    value = defaultdict(list)
    for atom in atoms:
        value[(atom["source_id"], atom["block_id"])].append((atom["start_offset"], atom["end_offset"]))
    return value
