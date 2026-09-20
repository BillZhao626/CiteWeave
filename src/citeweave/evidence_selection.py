"""Whole-atom seed selection and bounded, confidence-aware Parent projection."""

import json

from citeweave.query_evidence import EvidencePack, PackSpan, SourceCoverage
from citeweave.trace import network_timeout


def page(atom):
    return atom.evidence["boxes"][0]["page_index"]


def interval(atom):
    e = atom.evidence
    return (str(atom.version_id), e["block_id"]), e["start_offset"], e["end_offset"]


def union_chars(atoms):
    groups = {}
    for atom in atoms:
        key, start, end = interval(atom)
        groups.setdefault(key, []).append((start, end))
    total = 0
    for ranges in groups.values():
        last = -1
        for start, end in sorted(ranges):
            total += max(0, end - max(start, last))
            last = max(last, end)
    return total


def merge_atoms(current, incoming, atoms):
    """Keep existing identities; contained ranges use the complete original larger span.

    Partial overlaps cannot be displayed without clipping an atom, so fail closed on
    that proposal. Accepted Batch-2 children have zero overlap.
    """
    chosen, lineage = list(current), []
    for eid in incoming:
        if eid in chosen:
            lineage.append({"evidence_id": eid, "covered_by": eid})
            continue
        key, start, end = interval(atoms[eid])
        remove, covered = [], False
        for other in chosen:
            k, a, b = interval(atoms[other])
            if k != key or end <= a or b <= start:
                continue
            if a <= start and end <= b:
                lineage.append({"evidence_id": eid, "covered_by": other})
                covered = True
                break
            if start <= a and b <= end:
                remove.append(other)
                lineage.append({"evidence_id": other, "covered_by": eid})
            else:
                raise ValueError("partial_overlap_requires_unclipped_atom")
        if not covered:
            chosen = [i for i in chosen if i not in remove] + [eid]
    return chosen, lineage


def seed_order(ordered, candidates, snapshot):
    if snapshot.evidence_mode == "single":
        return [(i, "rank_order") for i in ordered]
    top = ordered[:12]
    sources = snapshot.requested_documents or list(dict.fromkeys(candidates[i].document_id for i in top))
    quota = []
    for source in sources:
        found = next((i for i in top if candidates[i].document_id == source), None)
        if found and found not in quota:
            quota.append(found)
        if len(quota) == 2:
            break
    return [(i, "source_quota_top12") for i in quota] + [(i, "rank_order") for i in ordered if i not in quota]


def select_evidence(
    ordered,
    candidates,
    children,
    repository,
    tokenizer,
    degraded=None,
    reason=None,
    seed_atoms=None,
    *,
    parent_expansion=True,
):
    snapshot = repository.snapshot
    # Reuse this run's already verified seed atoms. Read expansion atoms only
    # after selection, for the at-most-three Parents actually admitted.
    all_children = dict(children)
    atom_ids = {i for c in children.values() for i in c["span_ids"]}
    atoms = dict(seed_atoms) if seed_atoms is not None else repository.atoms(atom_ids)
    if set(atoms) != atom_ids:
        raise ValueError("seed_atom_membership_mismatch")
    selected, seeds, origins, decisions, seed_tokens = [], [], {}, [], 0
    source_lookup = {b.version_id: b for b in snapshot.bindings}
    eligible = list(dict.fromkeys(candidates[i].document_id for i in ordered[:12]))
    requested = snapshot.requested_documents or (eligible if snapshot.evidence_mode == "compare" else [])
    parent_priority = {}

    def ordered_ids(ids, provenance):
        def key(eid):
            origin = provenance[eid]
            parent = all_children[origin["seed_child_id"]]["parent"]
            return (
                parent_priority.get(str(parent.id), 99),
                str(atoms[eid].version_id),
                parent.content_ids.index(eid) if eid in parent.content_ids else -1,
                eid,
            )

        return sorted(ids, key=key)

    def serialize(ids, provenance):
        ids = ordered_ids(ids, provenance)
        versions = list(dict.fromkeys(str(atoms[i].version_id) for i in ids))
        labels = {v: "S" + str(n) for n, v in enumerate(versions, 1)}
        selected_docs = {source_lookup[v].document_id for v in versions}
        missing = [d for d in requested if d not in selected_docs]
        value = dict(
            sources=[
                {"source": labels[v], "title": source_lookup[v].filename, "version": v} for v in versions
            ],
            source_gaps=missing,
            evidence=[
                {"label": "E" + str(n), "source": labels[str(atoms[i].version_id)], "text": atoms[i].text}
                for n, i in enumerate(ids, 1)
            ],
        )
        return ids, json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def fits(ids, provenance, seed=False):
        network_timeout(2)
        sorted_ids, encoded = serialize(ids, provenance)
        chars = union_chars(atoms[i] for i in ids)
        if len(ids) > (64 if seed else 96) or len(encoded) > 6400 or (seed and chars > 3200):
            return False, 0, 0
        texts = [encoded]
        if seed:
            texts.append("\n".join(atoms[i].text for i in sorted_ids))
        counts = tokenizer.count(texts)
        return (
            counts[0]["bge"] <= 2048 and (not seed or counts[1]["bge"] <= 1024),
            counts[0]["bge"],
            counts[1]["bge"] if seed else 0,
        )

    max_seeds = 6 if snapshot.evidence_mode == "compare" else 4
    for identity, why in seed_order(ordered, candidates, snapshot):
        candidate, child = candidates[identity], children[identity]
        if len(seeds) == max_seeds:
            candidate.selection_reason = "seed_count_limit"
            continue
        try:
            proposal, lineage = merge_atoms(selected, child["span_ids"], atoms)
        except ValueError:
            candidate.selection_reason = "partial_overlap"
            continue
        if proposal == selected:
            candidate.selection_reason = "duplicate_coverage"
            decisions.extend(lineage)
            continue
        parent_id = str(child["parent"].id)
        parent_priority.setdefault(parent_id, len(parent_priority))
        before = union_chars(atoms[i] for i in selected)
        proposed_origins = dict(origins)
        for eid in proposal:
            proposed_origins.setdefault(
                eid,
                dict(
                    seed_child_id=identity,
                    parent_id=parent_id,
                    origin="seed",
                    cross_page=False,
                    budget_before=before,
                    budget_after=union_chars(atoms[i] for i in proposal),
                ),
            )
        accepted, _, tokens = fits(proposal, proposed_origins, seed=True)
        if not accepted:
            candidate.selection_reason = "evidence_budget"
            continue
        selected, origins, seed_tokens = proposal, proposed_origins, tokens
        seeds.append(identity)
        candidate.seed_rank = len(seeds)
        candidate.selection_reason = why
        decisions.extend(lineage)
    seed_chars, seed_spans = union_chars(atoms[i] for i in selected), len(selected)
    seed_ids = list(selected)
    # One anchor per Parent; round-robin headings, previous, next, at most three Parents.
    anchors = []
    seen = set()
    for identity in seeds:
        parent = children[identity]["parent"]
        if str(parent.id) not in seen and len(anchors) < 3:
            seen.add(str(parent.id))
            anchors.append(identity)
    if not degraded and parent_expansion:
        neighbors = repository.neighbors([children[i] for i in anchors])
        all_children.update(neighbors)
        added_ids = {i for c in neighbors.values() for i in c["span_ids"]}
        added_ids.update(i for anchor in anchors for i in children[anchor]["parent"].heading_ids)
        if missing_atoms := added_ids - set(atoms):
            atoms.update(repository.atoms(missing_atoms))
        for round_number in range(3):
            for identity in anchors:
                child = children[identity]
                parent, row = child["parent"], child["row"]
                if parent.confidence == "FALLBACK_PAGE":
                    decisions.append(dict(seed_child_id=identity, reason="fallback_page_seed_only"))
                    continue
                if round_number == 0:
                    incoming, origin = parent.heading_ids, "heading"
                else:
                    neighbor = next(
                        (
                            c
                            for c in neighbors.values()
                            if c["row"].parent_node_id == row.parent_node_id
                            and c["row"].ordinal == row.ordinal + (-1 if round_number == 1 else 1)
                        ),
                        None,
                    )
                    incoming, origin = (neighbor["span_ids"] if neighbor else []), "sibling"
                seed_pages = {page(atoms[i]) for i in child["span_ids"]}
                allowed = [
                    i
                    for i in incoming
                    if (
                        page(atoms[i]) in seed_pages
                        or parent.confidence == "VERIFIED_RULE"
                        and min(abs(page(atoms[i]) - p) for p in seed_pages) <= 1
                    )
                ]
                for i in set(incoming) - set(allowed):
                    decisions.append(
                        dict(evidence_id=i, seed_child_id=identity, reason="confidence_page_limit")
                    )
                # Context may add a prefix of complete atoms, never a clipped quote.
                # At most six tokenizer probes for a 24-atom Child.
                prefix_sizes = []
                size = len(allowed)
                while size:
                    prefix_sizes.append(size)
                    size //= 2
                proposals = []
                for count in prefix_sizes:
                    proposal, lineage = merge_atoms(selected, allowed[:count], atoms)
                    if proposal == selected:
                        break
                    before, after = (
                        union_chars(atoms[i] for i in selected),
                        union_chars(atoms[i] for i in proposal),
                    )
                    if after - seed_chars > min(seed_chars, 3200) or len(proposal) > 96:
                        continue
                    proposed_origins = dict(origins)
                    for eid in proposal:
                        proposed_origins.setdefault(
                            eid,
                            dict(
                                seed_child_id=identity,
                                parent_id=str(parent.id),
                                origin=origin,
                                cross_page=page(atoms[eid]) not in seed_pages,
                                budget_before=before,
                                budget_after=after,
                            ),
                        )
                    _, encoded = serialize(proposal, proposed_origins)
                    if len(encoded) <= 6400:
                        proposals.append((proposal, proposed_origins, lineage, encoded))
                measured = tokenizer.count([p[3] for p in proposals]) if proposals else []
                for (proposal, proposed_origins, lineage, _), counts in zip(proposals, measured, strict=True):
                    if counts["bge"] <= 2048:
                        selected, origins = proposal, proposed_origins
                        decisions.extend(lineage)
                        break
                else:
                    if allowed:
                        decisions.append(
                            dict(seed_child_id=identity, origin=origin, reason="expansion_budget")
                        )
    selected, encoded = serialize(selected, origins)
    total_tokens = tokenizer.count([encoded])[0]["bge"]
    if len(encoded) > 6400 or total_tokens > 2048 or len(selected) > 96:
        raise ValueError("evidence_pack_budget")
    # Every accepted seed interval must still be covered by an original displayed span.
    for eid in seed_ids:
        _, coverage = merge_atoms(selected, [eid], atoms)
        if not coverage:
            raise ValueError("seed_coverage_lost")
    selected_docs = list(dict.fromkeys(source_lookup[str(atoms[i].version_id)].document_id for i in selected))
    missing = [d for d in requested if d not in selected_docs]
    spans = [
        PackSpan(
            label="E" + str(n),
            evidence_id=eid,
            document_id=source_lookup[str(atoms[eid].version_id)].document_id,
            version_id=str(atoms[eid].version_id),
            **origins[eid],
            covered_by=[
                d["evidence_id"] for d in decisions if d.get("covered_by") == eid and d["evidence_id"] != eid
            ],
        )
        for n, eid in enumerate(selected, 1)
    ]
    pack = EvidencePack(
        evidence_mode=snapshot.evidence_mode,
        spans=spans,
        seed_child_ids=seeds,
        source_coverage=SourceCoverage(
            requested=requested,
            eligible=eligible,
            selected=selected_docs,
            missing=missing,
            coverage_unmet=bool(missing) or snapshot.evidence_mode == "compare" and len(selected_docs) < 2,
        ),
        degraded=degraded,
        fallback_reason=reason,
        seed_chars=seed_chars,
        seed_spans=seed_spans,
        seed_tokens=seed_tokens,
        added_chars=union_chars(atoms[i] for i in selected) - seed_chars,
        serialized_chars=len(encoded),
        serialized_tokens=total_tokens,
        prompt_json=encoded,
        decisions=decisions,
    )
    return [atoms[i] for i in selected], pack
