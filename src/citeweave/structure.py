"""Source-only section recognition and deterministic multi-atom retrieval units.

No query, benchmark, rank, or desired answer enters this module. Canonical text
is never normalized; normalization below is only for comparing heading cues.
"""

import re
import unicodedata
from collections import Counter, defaultdict
from uuid import UUID, uuid5

from citeweave.document_profiles import (
    CHILD_POLICY,
    canonical_blocks_hash,
    canonical_json,
    content_hash,
    validate_profile,
)
from citeweave.evidence import Block, EvidenceSpan, bind_span, digest, resolve_span
from citeweave.tokenization import TOKENIZERS, fits

NAMESPACE = UUID("2d2747d9-a945-4d61-a289-76bfe2dadc4e")
HEADING = re.compile(r"^(?:(Annex|Appendix)\s+([A-Z])\.?|([A-Z](?:\.\d+)+|\d+(?:\.\d+)*))\.?\s+(.+)$")


def identity(kind, *parts):
    return str(uuid5(NAMESPACE, canonical_json([kind, *parts])))


def _title(text):
    return re.sub(r"\s+", " ", re.sub(r"[.\s]*\d+\s*$", "", unicodedata.normalize("NFKC", text))).strip()


def _atom(block, start, end):
    span = bind_span(block, start, end, block.text[start:end])
    return dict(
        id=str(span.id),
        text=span.quote,
        block=block.model_dump(mode="json"),
        evidence=span.model_dump(mode="json"),
    )


def parse_structure(canonical_blocks, layout_hints, document_profile):
    profile = validate_profile(document_profile)
    blocks = list(canonical_blocks)
    if not blocks:
        raise ValueError("unsupported_no_text")
    if sum((len(b.text) + 159) // 160 for b in blocks) > profile["limits"]["atoms"]:
        raise ValueError("structural_atom_limit")
    scope = blocks[0].scope
    if any(b.scope != scope or b.source_sha256 != blocks[0].source_sha256 for b in blocks):
        raise ValueError("structure_scope_mismatch")
    canonical_sha = canonical_blocks_hash(blocks)
    profile_hash = content_hash(profile)
    aid = identity("artifact", str(scope.revision_id), canonical_sha, profile_hash)
    artifact = dict(
        id=aid,
        version_id=str(scope.revision_id),
        parser_revision=profile["parser_revision"],
        profile=profile,
        profile_hash=profile_hash,
        canonical_sha=canonical_sha,
        tokenizers=TOKENIZERS,
        state="DRAFT",
    )
    chunks, by_block = [], {}
    for block in blocks:
        values, start = [], 0
        glyph_groups = layout_hints.get(block.block_id, {}).get("glyph_groups", [])
        while start < len(block.text):
            end = min(start + 160, len(block.text))
            for group in glyph_groups:
                if group["start"] < end < group["end"]:
                    end = group["start"]
            if end <= start:
                raise ValueError("unsupported_glyph_group_size")
            values.append(_atom(block, start, end))
            start = end
        if not block.text.strip():
            values = []
        chunks.extend(values)
        by_block[block.block_id] = [a["id"] for a in values]
    if not chunks or len(chunks) > profile["limits"]["atoms"]:
        raise ValueError("structural_atom_limit")
    hints = {b.block_id: dict(layout_hints.get(b.block_id, {})) for b in blocks}
    repeats = defaultdict(set)
    for block in blocks:
        hint = hints[block.block_id]
        if hint.get("top", 0.5) < 0.09 or hint.get("bottom", 0.5) > 0.92:
            repeats[re.sub(r"\d+", "#", block.text.strip())].add(hint.get("page", 0))
    candidates = {}
    for order, block in enumerate(blocks):
        hint = hints[block.block_id]
        if (hint.get("top", 0.5) < 0.09 or hint.get("bottom", 0.5) > 0.92) and len(
            repeats[re.sub(r"\d+", "#", block.text.strip())]
        ) >= 2:
            hint["excluded"] = "repeated_page_header_footer"
        match = HEADING.match(block.text.strip())
        if not match or hint.get("excluded"):
            continue
        annex, letter, number, title = match.groups()
        number = letter or number
        if number.isdigit() and len(number) > 1 and number.startswith("0"):
            continue
        if not any(ch.isalpha() for ch in title) or hint.get("monospace"):
            continue
        font_cue = hint.get("bold", False) or (
            hint.get("font_size", 0) >= 11 and hint.get("font_size", 0) > hint.get("body_size", 10) + 0.8
        )
        whitespace_cue = (
            hint.get("whitespace_before", 0) >= 8
            and hint.get("indent", 1) < 0.22
            and len(title.split()) <= 8
            and not title.rstrip().endswith((".", ":", ";"))
            and not hint.get("table_confidence")
        )
        candidates[order] = dict(
            number=number, title=title, font_cue=font_cue, whitespace_cue=whitespace_cue, annex=bool(annex)
        )
    body_matches = {(c["number"], _title(c["title"])) for c in candidates.values() if c["font_cue"]}
    excluded = {}
    nodes = []
    block_parents = {}

    def node(kind, number, title, heading_ids, parent, order, page, confidence, reasons, details=None):
        item = dict(
            id=identity("node", aid, kind, heading_ids, number, order),
            artifact_id=aid,
            parent_node_id=parent,
            kind=kind,
            number=number,
            title=title,
            heading_ids=heading_ids,
            content_ids=[],
            reading_order=order,
            page_start=page,
            page_end=page,
            confidence=confidence,
            reasons=reasons,
            details=details or {},
        )
        nodes.append(item)
        return item

    root = node("document", None, "", [], None, 0, 0, "FALLBACK_PAGE", ["document_root"])
    seen, numbered, fallback = Counter(), {}, {}
    active = None
    last_page = None
    in_toc = False
    for order, block in enumerate(blocks):
        hint = hints[block.block_id]
        page = hint.get("page", block.boxes[0].page_index if block.boxes else 0)
        c = candidates.get(order)
        if re.sub(r"\s+", "", block.text).lower() == "tableofcontents":
            in_toc = True
            hint["excluded"] = "toc_heading"
        if (
            in_toc
            and c
            and hint.get("bold")
            and hint.get("font_size", 0) >= 11
            and not re.search(r"\.{2,}\s*\d+\s*$", c["title"])
        ):
            in_toc = False
        if (
            c
            and (in_toc or re.search(r"(?:\.{2,}|\s)\d+\s*$", c["title"]))
            and (c["number"], _title(c["title"])) in body_matches
        ):
            hint["excluded"] = "toc_body_heading_match_and_page_label"
        if hint.get("excluded"):
            excluded[block.block_id] = hint["excluded"]
            continue
        if page != last_page and active and active["confidence"] != "VERIFIED_RULE":
            active = None
        if c and (c["font_cue"] or c["whitespace_cue"]):
            number = c["number"]
            parts = number.split(".")
            parent = root
            for end in range(len(parts) - 1, 0, -1):
                if "parent" not in c and (ancestor := numbered.get(".".join(parts[:end]))):
                    parent = ancestor
                    break
            missing = len(parts) > 1 and ".".join(parts[:-1]) not in numbered
            conflict = seen[number] > 0
            seen[number] += 1
            reasons = ["explicit_number", "font_cue" if c["font_cue"] else "whitespace_indent_cue"]
            if missing:
                reasons.append("missing_numbering_level")
            if conflict:
                reasons.append("repeated_or_conflicting_number")
            confidence = "HEURISTIC" if missing or conflict or not c["font_cue"] else "VERIFIED_RULE"
            active = node(
                "annex" if c["annex"] else "clause" if len(parts) > 1 else "section",
                number,
                c["title"].strip(),
                by_block[block.block_id],
                parent["id"],
                order + 1,
                page,
                confidence,
                reasons,
            )
            numbered[number] = active
        if active is None:
            if page not in fallback:
                fallback[page] = node(
                    "page",
                    None,
                    "",
                    [],
                    root["id"],
                    order + 1,
                    page,
                    "FALLBACK_PAGE",
                    ["no_reliable_heading_on_page"],
                )
            current = fallback[page]
        else:
            current = active
        current["content_ids"].extend(by_block[block.block_id])
        current["page_end"] = page
        if hint.get("table_confidence"):
            row = {
                "block_id": block.block_id,
                "span_ids": by_block[block.block_id],
                "table_confidence": hint["table_confidence"],
                "table_id": hint.get("table_id"),
                "cells": hint.get("cells", []),
                "header_span_ids": [],
                "caption_span_ids": [],
            }
            if (
                order > 0
                and re.match(r"^Table\s+\d+[.:]", blocks[order - 1].text.strip(), re.I)
                and block_parents.get(blocks[order - 1].block_id) == current["id"]
            ):
                row["caption_span_ids"] = by_block[blocks[order - 1].block_id]
            if hint.get("table_header"):
                row["header_span_ids"] = by_block[block.block_id]
            elif hint.get("table_id"):
                previous = next(
                    (
                        r
                        for r in reversed(current["details"].get("table_rows", []))
                        if r["table_id"] == hint["table_id"]
                    ),
                    None,
                )
                if previous:
                    row["header_span_ids"] = previous["header_span_ids"]
                    row["caption_span_ids"] = previous["caption_span_ids"]
            current["details"].setdefault("table_rows", []).append(row)
        block_parents[block.block_id] = current["id"]
        last_page = page
    by_id = {n["id"]: n for n in nodes}
    for n in reversed(nodes):
        if n["parent_node_id"]:
            parent = by_id[n["parent_node_id"]]
            parent["page_end"] = max(parent["page_end"], n["page_end"])
    root["details"]["exclusions"] = excluded
    root["details"]["canonical_blocks"] = {
        b.block_id: content_hash(b.model_dump(mode="json")) for b in blocks
    }
    root["details"]["glyph_groups"] = {
        bid: h["glyph_groups"] for bid, h in hints.items() if h.get("glyph_groups")
    }
    return {
        "artifact": artifact,
        "nodes": nodes,
        "chunks": chunks,
        "children": [],
        "block_parents": block_parents,
    }


def build_children(draft, tokenizer):
    """Count atoms in batches, split oversized atoms on source codepoints, then pack."""
    if tokenizer.identity != TOKENIZERS:
        raise ValueError("tokenizer_identity_mismatch")
    original, accepted, counts = draft["chunks"], [], {}
    replacements = {}

    def accept(atom, count):
        if fits(atom["text"], count):
            accepted.append(atom)
            counts[atom["id"]] = count
            return [atom["id"]]
        if len(atom["text"]) == 1:
            raise ValueError("unsupported_single_codepoint_token_limit")
        block = Block.model_validate(atom["block"])
        start, end = atom["evidence"]["start_offset"], atom["evidence"]["end_offset"]
        middle = (start + end) // 2
        for group in draft["nodes"][0]["details"].get("glyph_groups", {}).get(block.block_id, []):
            if group["start"] < middle < group["end"]:
                middle = group["start"] if group["start"] > start else group["end"]
        if middle in (start, end):
            raise ValueError("unsupported_glyph_group_token_limit")
        pieces = [_atom(block, start, middle), _atom(block, middle, end)]
        result = []
        for piece, measured in zip(pieces, tokenizer.count([p["text"] for p in pieces]), strict=True):
            result.extend(accept(piece, measured))
        return result

    for start in range(0, len(original), 20):
        batch = original[start : start + 20]
        for atom, count in zip(batch, tokenizer.count([a["text"] for a in batch]), strict=True):
            replacements[atom["id"]] = accept(atom, count)
    if len(accepted) > draft["artifact"]["profile"]["limits"]["atoms"]:
        raise ValueError("structural_atom_limit")
    draft["chunks"] = accepted
    atoms = {a["id"]: a for a in accepted}
    for n in draft["nodes"]:
        for key in ("heading_ids", "content_ids"):
            n[key] = [new for old in n[key] for new in replacements[old]]
        for row in n["details"].get("table_rows", []):
            row["span_ids"] = [new for old in row["span_ids"] for new in replacements[old]]
            for key in ("caption_span_ids", "header_span_ids"):
                row[key] = [new for old in row.get(key, []) for new in replacements[old]]
    # Token-driven atom refinement also refines heading identity before any child is built.
    remap = {
        n["id"]: identity(
            "node", draft["artifact"]["id"], n["kind"], n["heading_ids"], n["number"], n["reading_order"]
        )
        for n in draft["nodes"]
    }
    for n in draft["nodes"]:
        n["id"] = remap[n["id"]]
        n["parent_node_id"] = remap.get(n["parent_node_id"])
    proposals = []
    for n in draft["nodes"]:
        group, e5, bge, chars, last_page = [], 0, 0, 0, None
        table_blocks = {r["block_id"] for r in n["details"].get("table_rows", [])}
        last_block = None
        for aid in n["content_ids"]:
            a, c = atoms[aid], counts[aid]
            block_id = a["block"]["block_id"]
            # Start and end rows on child boundaries. A row exceeding a child
            # budget is split explicitly, with continuation membership below.
            row_boundary = block_id != last_block and (block_id in table_blocks or last_block in table_blocks)
            page = a["evidence"]["boxes"][0]["page_index"] if a["evidence"]["boxes"] else 0
            cross = (
                last_page is not None
                and page != last_page
                and (n["confidence"] != "VERIFIED_RULE" or page != last_page + 1)
            )
            if group and (
                len(group) >= 24
                or chars + len(a["text"]) + 1 > 960
                or e5 + c["e5"] + 2 > 184
                or bge + c["bge"] + 2 > 312
                or cross
                or row_boundary
            ):
                proposals.append((n, group))
                group, e5, bge, chars = [], 0, 0, 0
            group.append(aid)
            e5 += c["e5"] + 2
            bge += c["bge"] + 2
            chars += len(a["text"]) + 1
            last_page = page
            last_block = block_id
        if group:
            proposals.append((n, group))
    groups = defaultdict(list)

    def text(ids):
        return "\n".join(atoms[x]["text"] for x in ids)

    def checked(n, ids, measured):
        if fits(text(ids), measured, len(ids)):
            groups[n["id"]].append((ids, measured))
        elif len(ids) > 1:
            halves = [ids[: len(ids) // 2], ids[len(ids) // 2 :]]
            for part, measurement in zip(halves, tokenizer.count([text(p) for p in halves]), strict=True):
                checked(n, part, measurement)
        else:
            raise ValueError("child_token_contract_mismatch")

    for start in range(0, len(proposals), 20):
        batch = proposals[start : start + 20]
        for (n, ids), measured in zip(batch, tokenizer.count([text(ids) for _, ids in batch]), strict=True):
            checked(n, ids, measured)
    for n in list(draft["nodes"]):
        children = groups[n["id"]]
        table_blocks = {r["block_id"] for r in n["details"].get("table_rows", [])}
        bundles = []
        previous_row = None
        for item in children:
            block_ids = {atoms[x]["block"]["block_id"] for x in item[0]}
            row = next(iter(block_ids)) if len(block_ids) == 1 else None
            row = row if row in table_blocks else None
            if row and row == previous_row:
                bundles[-1].append(item)
            else:
                bundles.append([item])
            previous_row = row
        # Keep a row's children in one Parent whenever that whole row fits.
        units = []
        for bundle in bundles:
            if (
                len(bundle) <= 24
                and sum(m["e5"] + 2 for _, m in bundle) <= 4000
                and sum(len(text(ids)) + 1 for ids, _ in bundle) <= 15000
            ):
                units.append(bundle)
            else:
                units.extend([[item] for item in bundle])
        partitions, current, tokens, chars = [], [], 0, 0
        for unit in units:
            unit_tokens = sum(m["e5"] + 2 for _, m in unit)
            unit_chars = sum(len(text(ids)) + 1 for ids, _ in unit)
            if current and (
                len(current) + len(unit) > 24 or tokens + unit_tokens > 4000 or chars + unit_chars > 15000
            ):
                partitions.append(current)
                current, tokens, chars = [], 0, 0
            current.extend(unit)
            tokens += unit_tokens
            chars += unit_chars
        if current:
            partitions.append(current)
        for pi, partition in enumerate(partitions):
            parent = n
            if len(partitions) > 1:
                members = [x for ids, _ in partition for x in ids]
                parent = {
                    **n,
                    "id": identity("partition", n["id"], pi, members),
                    "parent_node_id": n["id"],
                    "kind": "partition",
                    "number": None,
                    "title": "",
                    "heading_ids": [],
                    "content_ids": members,
                    "details": {
                        "original_node_id": n["id"],
                        "partition_ordinal": pi,
                        "source_authored": False,
                    },
                }
                parent["page_start"] = min(atoms[x]["evidence"]["boxes"][0]["page_index"] for x in members)
                parent["page_end"] = max(atoms[x]["evidence"]["boxes"][0]["page_index"] for x in members)
                draft["nodes"].append(parent)
            for ordinal, (ids, measured) in enumerate(partition):
                value = text(ids)
                draft["children"].append(
                    dict(
                        id=identity("child", draft["artifact"]["id"], parent["id"], ids, CHILD_POLICY),
                        version_id=draft["artifact"]["version_id"],
                        artifact_id=draft["artifact"]["id"],
                        parent_node_id=parent["id"],
                        ordinal=ordinal,
                        retrieval_text=value,
                        text_hash=digest(value),
                        membership_hash=content_hash(ids),
                        span_ids=ids,
                        tokenizers=TOKENIZERS,
                        token_counts={k: v for k, v in measured.items() if not k.endswith("_offsets")},
                        details={"heading_prefix": "", "overlap": 0, "child_policy": CHILD_POLICY},
                    )
                )
    if not draft["children"] or len(draft["children"]) > draft["artifact"]["profile"]["limits"]["children"]:
        raise ValueError("structural_child_limit")
    parent_ids = {c["parent_node_id"] for c in draft["children"]}
    parents = {n["id"]: n for n in draft["nodes"] if n["id"] in parent_ids}
    ordered_parents = list(parents.values())
    for start in range(0, len(ordered_parents), 20):
        batch = ordered_parents[start : start + 20]
        for parent, measured in zip(
            batch, tokenizer.count([text(n["content_ids"]) for n in batch]), strict=True
        ):
            if measured["e5"] > 4096:
                raise ValueError("structural_parent_token_limit")
            parent["details"]["e5_tokens"] = measured["e5"]
    block_children = defaultdict(set)
    for child in draft["children"]:
        for x in child["span_ids"]:
            block_children[atoms[x]["block"]["block_id"]].add(child["id"])
    for child in draft["children"]:
        source_blocks = {atoms[x]["block"]["block_id"] for x in child["span_ids"]}
        child["details"]["continuation_blocks"] = [
            bid for bid in sorted(source_blocks) if len(block_children[bid]) > 1
        ]
    seal(draft)
    validate_draft(draft)
    return draft


def seal(draft):
    draft["artifact"]["tree_hash"] = content_hash(draft["nodes"])
    draft["artifact"]["membership_hash"] = content_hash(
        [[c["id"], c["parent_node_id"], c["span_ids"]] for c in draft["children"]]
    )


def validate_draft(draft):
    artifact = draft["artifact"]
    validate_profile(artifact["profile"])
    if (
        not 0 < len(draft["chunks"]) <= artifact["profile"]["limits"]["atoms"]
        or not 0 < len(draft["children"]) <= artifact["profile"]["limits"]["children"]
    ):
        raise ValueError("structural_count_limit")
    if artifact["profile_hash"] != content_hash(artifact["profile"]) or artifact["id"] != identity(
        "artifact", artifact["version_id"], artifact["canonical_sha"], artifact["profile_hash"]
    ):
        raise ValueError("artifact_identity_mismatch")
    if artifact["tree_hash"] != content_hash(draft["nodes"]) or artifact["membership_hash"] != content_hash(
        [[c["id"], c["parent_node_id"], c["span_ids"]] for c in draft["children"]]
    ):
        raise ValueError("structure_hash_mismatch")
    atoms, nodes = {a["id"]: a for a in draft["chunks"]}, {n["id"]: n for n in draft["nodes"]}
    if len(atoms) != len(draft["chunks"]) or len(nodes) != len(draft["nodes"]):
        raise ValueError("structure_duplicate_identity")
    for atom in atoms.values():
        block, span = Block.model_validate(atom["block"]), EvidenceSpan.model_validate(atom["evidence"])
        if str(span.scope.revision_id) != artifact["version_id"] or str(span.id) != atom["id"]:
            raise ValueError("structure_scope_mismatch")
        if content_hash(atom["block"]) != draft["nodes"][0]["details"]["canonical_blocks"].get(
            block.block_id
        ):
            raise ValueError("canonical_block_mismatch")
        if resolve_span(span, block, block.scope) != atom["text"] or len(atom["text"]) > 160:
            raise ValueError("structure_atom_mismatch")
        for group in draft["nodes"][0]["details"].get("glyph_groups", {}).get(block.block_id, []):
            if any(
                group["start"] < boundary < group["end"] for boundary in (span.start_offset, span.end_offset)
            ):
                raise ValueError("atom_splits_glyph_group")
            if block.text[group["start"] : group["end"]] != group["text"] or any(
                box.model_dump(mode="json") != group["box"]
                for box in block.char_boxes[group["start"] : group["end"]]
            ):
                raise ValueError("glyph_group_geometry_mismatch")
    roots = []
    for n in nodes.values():
        if n["artifact_id"] != artifact["id"] or any(
            x not in atoms for x in n["content_ids"] + n["heading_ids"]
        ):
            raise ValueError("structure_node_scope_mismatch")
        expected_node_id = (
            identity(
                "partition",
                n["details"]["original_node_id"],
                n["details"]["partition_ordinal"],
                n["content_ids"],
            )
            if n["kind"] == "partition"
            else identity(
                "node", artifact["id"], n["kind"], n["heading_ids"], n["number"], n["reading_order"]
            )
        )
        if n["id"] != expected_node_id:
            raise ValueError("structure_node_identity_mismatch")
        if not set(n["heading_ids"]).issubset(n["content_ids"]):
            raise ValueError("structure_heading_membership_mismatch")
        for row in n["details"].get("table_rows", []):
            references = row["span_ids"] + row.get("header_span_ids", []) + row.get("caption_span_ids", [])
            if not row["span_ids"] or any(x not in n["content_ids"] for x in references):
                raise ValueError("table_reference_scope_mismatch")
            block = atoms[row["span_ids"][0]]["block"]
            if any(atoms[x]["block"]["block_id"] != row["block_id"] for x in row["span_ids"]):
                raise ValueError("table_row_source_mismatch")
            for cell in row.get("cells", []):
                left, top, right, bottom = cell["bbox"]
                if not (
                    0 <= cell["start"] < cell["end"] <= len(block["text"])
                    and cell["row"] >= 0
                    and cell["column"] >= 0
                    and 0 <= left < right <= 1
                    and 0 <= top < bottom <= 1
                ):
                    raise ValueError("table_cell_geometry_mismatch")
        visited, cursor = set(), n
        while cursor["parent_node_id"]:
            if cursor["id"] in visited or cursor["parent_node_id"] not in nodes:
                raise ValueError("structure_tree_cycle_or_missing_parent")
            visited.add(cursor["id"])
            cursor = nodes[cursor["parent_node_id"]]
        if n["parent_node_id"] is None:
            roots.append(n)
    if len(roots) != 1 or roots[0]["kind"] != "document":
        raise ValueError("structure_root_mismatch")
    used = set()
    parent_counts = Counter(c["parent_node_id"] for c in draft["children"])
    for child in draft["children"]:
        ids = child["span_ids"]
        parent = nodes.get(child["parent_node_id"])
        if parent and (parent["details"].get("e5_tokens", 4097) > 4096 or parent_counts[parent["id"]] > 24):
            raise ValueError("structural_parent_limit")
        if not parent or not ids or any(x not in parent["content_ids"] or x in used for x in ids):
            raise ValueError("child_parent_membership_mismatch")
        if child["version_id"] != artifact["version_id"] or child["artifact_id"] != artifact["id"]:
            raise ValueError("child_version_mismatch")
        if ids != sorted(ids, key=parent["content_ids"].index):
            raise ValueError("child_membership_order_mismatch")
        value = "\n".join(atoms[x]["text"] for x in ids)
        if (
            value != child["retrieval_text"]
            or digest(value) != child["text_hash"]
            or content_hash(ids) != child["membership_hash"]
        ):
            raise ValueError("child_text_or_membership_mismatch")
        if child["id"] != identity("child", artifact["id"], parent["id"], ids, CHILD_POLICY):
            raise ValueError("child_identity_mismatch")
        if child["tokenizers"] != TOKENIZERS or not fits(value, child["token_counts"], len(ids)):
            raise ValueError("child_token_contract_mismatch")
        pages = [atoms[x]["evidence"]["boxes"][0]["page_index"] for x in ids if atoms[x]["evidence"]["boxes"]]
        if len(set(pages)) > 1 and (
            parent["confidence"] != "VERIFIED_RULE"
            or any(b - a not in (0, 1) for a, b in zip(pages, pages[1:]))
        ):
            raise ValueError("child_cross_page_mismatch")
        used.update(ids)
    expected = {x for n in nodes.values() for x in n["content_ids"]}
    if used != expected:
        raise ValueError("child_coverage_mismatch")
