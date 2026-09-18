from copy import deepcopy

import pytest
from structure_fixtures import PROFILE, SCOPE, FixtureTokenizer, blocks, original_pdf

from citeweave.evidence import Block, EvidenceSpan, resolve_span
from citeweave.parsing import parse_structural_pdf
from citeweave.structure import build_children, parse_structure, seal, validate_draft


def build(lines):
    source, hints = blocks(lines)
    return build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())


def test_numbered_hierarchy_membership_identity_and_exact_evidence():
    lines = [
        ("1. Transport", 0, True),
        ("1.1. Requests", 0, True),
        ("1.1.1. Markers", 0, True),
        ("The request has an original marker.", 0, False),
        ("The marker survives a page break.", 1, False),
        ("2. Transport", 1, True),
        ("A different original section.", 1, False),
        ("Appendix A. Examples", 1, True),
        ("A.1. Markers", 1, True),
        ("An original example.", 1, False),
    ]
    first, second = build(lines), build(lines)
    assert first == second
    nodes = {n["number"]: n for n in first["nodes"] if n["number"]}
    assert nodes["1.1.1"]["parent_node_id"] == nodes["1.1"]["id"]
    assert nodes["A.1"]["parent_node_id"] == nodes["A"]["id"]
    assert nodes["1"]["id"] != nodes["2"]["id"]
    assert nodes["1.1.1"]["page_end"] == 1
    assert any(len(c["span_ids"]) > 1 for c in first["children"])
    for a in first["chunks"]:
        assert (
            resolve_span(EvidenceSpan.model_validate(a["evidence"]), Block.model_validate(a["block"]), SCOPE)
            == a["text"]
        )


def test_toc_lists_duplicate_numbers_missing_level_and_fallback():
    source, hints = blocks(
        [
            ("Table of Contents", 0, True),
            ("1. Start12", 0, False),
            ("1.1. Detail ........ 12", 0, False),
            ("1. Start", 1, True),
            ("1.1. Detail", 1, True),
            ("1. take the first item", 1, False),
            ("1.3.1. Missing level", 1, True),
            ("1.3.1. Missing level", 1, True),
            ("Unstructured next page.", 2, False),
        ]
    )
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    assert draft["nodes"][0]["details"]["exclusions"]["1"].startswith("toc_")
    assert draft["nodes"][0]["details"]["exclusions"]["2"].startswith("toc_")
    details = [n for n in draft["nodes"] if n["number"] == "1.3.1"]
    assert len(details) == 2 and details[0]["id"] != details[1]["id"]
    assert all(n["confidence"] == "HEURISTIC" for n in details)
    assert not any(n["title"] == "take the first item" for n in draft["nodes"])
    assert any(n["kind"] == "page" and n["page_start"] == 2 for n in draft["nodes"])


def test_table_stays_with_current_section_and_long_parent_partitions():
    source, hints = blocks(
        [
            ("1. Fields", 0, True),
            ("Name | Value", 0, False),
            ("Marker | Local", 0, False),
            ("2. Long clause", 0, True),
        ]
        + [("Original words for the long clause. " * 4, 0, False)] * 220
    )
    hints["1"]["table_confidence"] = "unresolved"
    hints["2"]["table_confidence"] = "unresolved"
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    section = next(n for n in draft["nodes"] if n["number"] == "1")
    assert len(section["details"]["table_rows"]) == 2
    partitions = [n for n in draft["nodes"] if n["kind"] == "partition"]
    assert len(partitions) > 1
    assert all(not p["details"]["source_authored"] and p["number"] is None for p in partitions)
    assert max(sum(c["parent_node_id"] == p["id"] for c in draft["children"]) for p in partitions) <= 24


@pytest.mark.parametrize("fault", ["version", "membership", "text", "cycle", "token"])
def test_corruption_rejected(fault):
    draft = deepcopy(build([("1. Original", 0, True), ("Source paragraph.", 0, False)]))
    child = draft["children"][0]
    if fault == "version":
        child["version_id"] = "00000000-0000-0000-0000-000000000001"
    if fault == "membership":
        child["span_ids"].reverse()
    if fault == "text":
        child["retrieval_text"] = "invented"
    if fault == "cycle":
        draft["nodes"][1]["parent_node_id"] = draft["nodes"][1]["id"]
    if fault == "token":
        child["token_counts"]["e5"] = 193
    seal(draft)
    with pytest.raises(ValueError):
        validate_draft(draft)


def test_original_pdf_headers_cross_page_and_geometry(tmp_path):
    path = tmp_path / "original.pdf"
    path.write_bytes(original_pdf())
    source, hints, pages = parse_structural_pdf(path, SCOPE, PROFILE)
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    assert pages == 2
    assert any(
        v == "repeated_page_header_footer" for v in draft["nodes"][0]["details"]["exclusions"].values()
    )
    clause = next(n for n in draft["nodes"] if n["number"] == "1.1.1")
    assert clause["page_start"] == 0 and clause["page_end"] == 1
    assert all(len(b.text) == len(b.char_boxes) for b in source)


def test_blank_pdf_is_explicitly_unsupported(tmp_path):
    from reportlab.pdfgen import canvas

    path = tmp_path / "blank.pdf"
    c = canvas.Canvas(str(path))
    c.showPage()
    c.save()
    with pytest.raises(ValueError, match="unsupported_no_text"):
        parse_structural_pdf(path, SCOPE, PROFILE)


def test_glyph_group_boundary_preserves_original_box():
    source, hints = blocks([("x" * 159 + "fi" + " ending", 0, False)])
    b = source[0]
    boxes = list(b.char_boxes)
    boxes[160] = boxes[159]
    source[0] = b.model_copy(update={"boxes": tuple(boxes), "char_boxes": tuple(boxes)})
    hints["0"]["glyph_groups"] = [dict(start=159, end=161, text="fi", box=boxes[159].model_dump(mode="json"))]
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    assert [a["evidence"]["end_offset"] for a in draft["chunks"]] == [159, len(b.text)]
    assert draft["nodes"][0]["details"]["glyph_groups"]["0"][0]["text"] == "fi"
