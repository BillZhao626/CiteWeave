"""Query-independent bounded paragraph projections over immutable original spans.

Parents are derived context objects, never EvidenceSpans. Generation receives their
bounded original member spans and citations continue to resolve those children.
"""

import hashlib
import re
from dataclasses import dataclass

REVISION = "geometry-paragraph-v1"
BOUNDARY = re.compile(r"^(?:\d+(?:\.\d+)*\.?\s+|[A-Z]\.\s+|[-*•]\s+)")


def page_key(chunk):
    return str(chunk.version_id), chunk.evidence["boxes"][0]["page_index"]


def position(chunk):
    box = chunk.evidence["boxes"][0]
    return box["top"], box["left"], chunk.evidence["start_offset"], str(chunk.id)


@dataclass(frozen=True)
class ParentContext:
    id: str
    version_id: str
    page_index: int
    members: tuple

    def provenance(self):
        return dict(
            parent_id=self.id,
            revision=REVISION,
            document_version_id=self.version_id,
            page_index=self.page_index,
            member_ids=[str(c.id) for c in self.members],
            context_chars=sum(len(c.text) for c in self.members),
        )


def project_parents(pool, profile):
    """No question, rank, relevance label or gold enters paragraph construction."""
    pages, parents = {}, []
    for chunk in pool:
        pages.setdefault(page_key(chunk), []).append(chunk)
    for key, chunks in sorted(pages.items()):
        groups = []
        for chunk in sorted(chunks, key=position):
            box = chunk.evidence["boxes"][0]
            split = not groups
            if groups:
                previous = groups[-1][-1]
                before = previous.evidence["boxes"][0]
                same_block = chunk.evidence["block_id"] == previous.evidence["block_id"]
                split = (
                    (not same_block and bool(BOUNDARY.match(chunk.text.strip())))
                    or box["top"] - before["bottom"] > profile["parent_max_gap"]
                    or abs(box["left"] - before["left"]) > profile["parent_max_indent"]
                    or len(groups[-1]) >= profile["parent_max_members"]
                    or sum(len(c.text) for c in groups[-1]) + len(chunk.text) > profile["parent_max_chars"]
                )
            if split:
                groups.append([])
            groups[-1].append(chunk)
        for members in groups:
            identity = hashlib.sha256(
                (REVISION + ":" + ":".join(str(c.id) for c in members)).encode()
            ).hexdigest()
            parents.append(ParentContext(identity, key[0], key[1], tuple(members)))
    return parents


def expand_parents(seeds, pool, profile):
    parents = project_parents(pool, profile)
    membership = {str(c.id): p for p in parents for c in p.members}
    chosen = {str(c.id): c for c in seeds}
    chars = sum(len(c.text) for c in chosen.values())
    origins, selected_parents = {}, {}
    queues = []
    for seed in seeds:
        parent = membership[str(seed.id)]
        if parent.id in selected_parents:
            continue
        selected_parents[parent.id] = parent
        members = list(parent.members)
        at = next(i for i, c in enumerate(members) if c.id == seed.id)
        ordered = sorted(enumerate(members), key=lambda item: (abs(item[0] - at), item[0]))
        queues.append((seed, [c for _, c in ordered]))
    # Round-robin gives each seed's parent an opportunity under the shared cap.
    for distance in range(max((len(q) for _, q in queues), default=0)):
        for seed, queue in queues:
            if distance >= len(queue):
                continue
            chunk = queue[distance]
            identity = str(chunk.id)
            if identity in chosen:
                continue
            if (
                len(chosen) >= profile["max_evidence_spans"]
                or chars + len(chunk.text) > profile["max_evidence_chars"]
            ):
                continue
            chosen[identity], origins[identity] = chunk, str(seed.id)
            chars += len(chunk.text)
    page_order = {key: i for i, key in enumerate(dict.fromkeys(page_key(c) for c in seeds))}
    selected = sorted(chosen.values(), key=lambda c: (page_order[page_key(c)], *position(c)))
    metadata = [
        dict(p.provenance(), selected_member_ids=[str(c.id) for c in p.members if str(c.id) in chosen])
        for p in selected_parents.values()
    ]
    return selected, origins, metadata
