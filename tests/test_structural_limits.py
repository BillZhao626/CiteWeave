from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from structure_fixtures import PROFILE, SCOPE, FixtureTokenizer, blocks, original_pdf

from citeweave.catalog import upload
from citeweave.document_profiles import document_profile
from citeweave.index import child_payload
from citeweave.parsing import parse_structural_pdf
from citeweave.pipeline import chunk_blocks
from citeweave.structure import build_children, parse_structure


def test_target_keeps_more_than_legacy_atom_limit():
    source, hints = blocks([("Original source line.", i // 10, False) for i in range(1001)])
    with pytest.raises(ValueError, match="chunk_count"):
        chunk_blocks(source)
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    assert len(draft["chunks"]) == 1001
    with pytest.raises(ValueError, match="structural_atom_limit"):
        parse_structure([source[0]] * 100001, hints, PROFILE)


def test_pdf_byte_page_and_profile_limits(tmp_path):
    for profile, size in [("telecom-protocol-pdf-v1", 32), ("pdf-glyph160-e5small-bm25-rrf60-bgev2-v1", 10)]:
        with pytest.raises(HTTPException, match=f"max_{size}_mib"):
            upload(
                uuid4(),
                uuid4(),
                b"%PDF-" + b"x" * (size * 1024 * 1024),
                "large.pdf",
                "original",
                "key",
                None,
                profile,
            )
    path = tmp_path / "large.pdf"
    pdf = canvas.Canvas(str(path))
    for _ in range(601):
        pdf.showPage()
    pdf.save()
    with pytest.raises(ValueError, match="structural_pdf_page_limit"):
        parse_structural_pdf(path, SCOPE, PROFILE)
    with pytest.raises(ValueError, match="unknown_ingestion_profile"):
        document_profile("invented")


@pytest.mark.parametrize("rotation", [0, 90, 270])
def test_supported_rotations_preserve_glyph_geometry(tmp_path, rotation):
    source = tmp_path / "source.pdf"
    source.write_bytes(original_pdf())
    writer = PdfWriter()
    for page in PdfReader(source).pages:
        writer.add_page(page.rotate(rotation))
    rotated = tmp_path / "rotated.pdf"
    writer.write(rotated)
    parsed, _, _ = parse_structural_pdf(rotated, SCOPE, PROFILE)
    assert all(len(b.text) == len(b.char_boxes) for b in parsed)


def test_encryption_crop_and_rotation_fail_explicitly(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(original_pdf())
    for mode in ["encrypted", "crop", "rotation"]:
        writer = PdfWriter()
        writer.add_page(PdfReader(source).pages[0])
        if mode == "encrypted":
            writer.encrypt("original-private-fixture")
        if mode == "crop":
            writer.pages[0].cropbox.lower_left = (10, 10)
        if mode == "rotation":
            writer.pages[0].rotate(180)
        path = tmp_path / (mode + ".pdf")
        writer.write(path)
        with pytest.raises(ValueError, match="unsupported_"):
            parse_structural_pdf(path, SCOPE, PROFILE)


def test_typed_payload_rejects_wrong_unit_artifact_or_membership():
    source, hints = blocks([("1. Example", 0, True), ("An original source.", 0, False)])
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    child = draft["children"][0]
    binding = dict(unit_kind="structural_child", artifact_id=draft["artifact"]["id"])
    scope = dict(
        version_id=str(SCOPE.revision_id), kb_id=str(SCOPE.kb_id), workspace_id=str(SCOPE.workspace_id)
    )
    assert child_payload(child, binding, scope)["span_ids"] == child["span_ids"]
    for bad in [{**binding, "unit_kind": "legacy_span"}, {**binding, "artifact_id": str(uuid4())}]:
        with pytest.raises(ValueError, match="payload_mismatch"):
            child_payload(child, bad, scope)
    bad = deepcopy(child)
    bad["span_ids"].reverse()
    with pytest.raises(ValueError, match="payload_mismatch"):
        child_payload(bad, binding, scope)


def test_original_rule_gold_has_exact_parent_membership_and_heading_edges():
    lines = [
        ("1. Root clause", 0, True),
        ("Root content.", 0, False),
        ("1.1. Narrow clause", 0, True),
        ("Narrow content.", 0, False),
        ("1.1.1. Deep clause", 0, True),
        ("Deep content.", 0, False),
        ("Continued deep content.", 1, False),
        ("2. Next clause", 1, True),
        ("Next content.", 1, False),
        ("Annex A. Original appendix", 1, True),
        ("A.1. Original detail", 1, True),
        ("Appendix content.", 1, False),
    ]
    source, hints = blocks(lines)
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    nodes = {n["id"]: n for n in draft["nodes"]}
    observed = {(n["number"], nodes[n["parent_node_id"]]["number"]) for n in nodes.values() if n["number"]}
    expected = {("1", None), ("1.1", "1"), ("1.1.1", "1.1"), ("2", None), ("A", None), ("A.1", "A")}
    assert observed == expected  # Heading edge precision: 6/6, 100%.
    expected_members = ["1", "1", "1.1", "1.1", "1.1.1", "1.1.1", "1.1.1", "2", "2", "A", "A.1", "A.1"]
    membership = {aid: n["number"] for n in nodes.values() for aid in n["content_ids"]}
    assert [membership[a["id"]] for a in draft["chunks"]] == expected_members  # 12/12, 100%.


def test_ruled_table_cells_caption_and_headers_keep_source_ranges(tmp_path):
    path = tmp_path / "table.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792), invariant=1)
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(60, 700, "1. Original table")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(60, 665, "Table 1. Original fields")
    pdf.rect(60, 580, 360, 60)
    pdf.line(240, 580, 240, 640)
    pdf.line(60, 600, 420, 600)
    pdf.line(60, 620, 420, 620)
    for y, left, right, bold in [
        (625, "Field", "Purpose", True),
        (605, "Marker", "Local request", False),
        (585, "Sequence", "Local order", False),
    ]:
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        pdf.drawString(65, y, left)
        pdf.drawString(245, y, right)
    pdf.save()
    source, hints, _ = parse_structural_pdf(path, SCOPE, PROFILE)
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    parent = next(n for n in draft["nodes"] if n["number"] == "1")
    rows = parent["details"]["table_rows"]
    assert len(rows) == 3 and all(r["table_confidence"] == "verified_grid" for r in rows)
    assert all(len(r["cells"]) == 2 for r in rows)
    assert rows[-1]["header_span_ids"] == rows[0]["span_ids"]
    assert rows[-1]["caption_span_ids"]


def test_complex_prose_columns_are_not_concatenated(tmp_path):
    path = tmp_path / "columns.pdf"
    pdf = canvas.Canvas(str(path), pagesize=(612, 792))
    pdf.setFont("Helvetica", 7)
    for i in range(12):
        pdf.drawString(50, 700 - i * 18, "Original independent prose in the first column here.")
        pdf.drawString(400, 700 - i * 18, "A different original prose passage in column two.")
    pdf.save()
    with pytest.raises(ValueError, match="unsupported_multiple_prose_columns"):
        parse_structural_pdf(path, SCOPE, PROFILE)


def test_table_row_children_stay_in_one_parent_when_row_fits():
    lines = [("1. Rows", 0, True)] + [("field " * 280, 0, False) for _ in range(18)]
    source, hints = blocks(lines)
    for block in source[1:]:
        hints[block.block_id].update(table_confidence="unresolved_row", table_id="original")
    draft = build_children(parse_structure(source, hints, PROFILE), FixtureTokenizer())
    atoms = {a["id"]: a for a in draft["chunks"]}
    for block in source[1:]:
        parents = {
            c["parent_node_id"]
            for c in draft["children"]
            if any(atoms[x]["block"]["block_id"] == block.block_id for x in c["span_ids"])
        }
        assert len(parents) == 1
    assert any(n["kind"] == "partition" for n in draft["nodes"])
