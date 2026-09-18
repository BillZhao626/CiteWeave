from structure_fixtures import original_pdf

from citeweave.source_preflight import glyph_summary, preflight


def test_source_preflight_is_model_free_and_finds_original_hierarchy(tmp_path):
    path = tmp_path / "original.pdf"
    path.write_bytes(original_pdf())
    report = preflight(path)
    assert report["status"] == "PASS"
    assert report["fffd"] == report["missing_or_unverifiable"] == report["geometry_failures"] == 0
    assert report["structure"]["max_depth"] == 3
    assert report["structure"]["verified_nested"] >= 3


def test_mapping_and_geometry_diagnostics_do_not_guess_or_drop_glyphs():
    box = dict(x0=1, x1=2, top=1, bottom=2)
    chars = [dict(box, text=t) for t in ["a", "fi", "\ufffd", "(cid:42)", ""]]
    chars.append(dict(box, text="x", x1=1))
    result = glyph_summary(chars, 10, 10)
    assert result == dict(
        glyphs=6, fffd=1, missing_or_unverifiable=3, multi_codepoint_ligatures=1, geometry_failures=1
    )


def test_bad_signature_fails_explicitly(tmp_path):
    path = tmp_path / "not-a-pdf.pdf"
    path.write_bytes(b"original non-PDF fixture")
    assert preflight(path)["reason"] == "invalid_pdf_signature"
