"""Read-only, model-free PDF source diagnostics under the structural parser contract."""

import argparse
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

import pdfplumber

from citeweave.document_profiles import document_profile
from citeweave.evidence import Scope, digest
from citeweave.parsing import glyph_mapping_supported, parse_structural_pdf
from citeweave.structure import parse_structure


def glyph_summary(chars, width, height):
    return dict(
        glyphs=len(chars),
        fffd=sum(c["text"].count("\ufffd") for c in chars),
        missing_or_unverifiable=sum(not glyph_mapping_supported(c["text"]) for c in chars),
        multi_codepoint_ligatures=sum(
            len(c["text"]) > 1 and glyph_mapping_supported(c["text"]) for c in chars
        ),
        geometry_failures=sum(
            not (0 <= c["x0"] < c["x1"] <= width and 0 <= c["top"] < c["bottom"] <= height) for c in chars
        ),
    )


def preflight(path: Path):
    profile = document_profile("telecom-protocol-pdf-v1")
    if path.stat().st_size > profile["limits"]["bytes"]:
        return dict(status="UNSUPPORTED", reason="structural_pdf_byte_limit")
    raw = path.read_bytes()
    report = dict(
        source_sha256=digest(raw),
        byte_length=len(raw),
        pdf_signature=raw[:8].decode("ascii", errors="replace"),
    )
    if not raw.startswith(b"%PDF-"):
        return dict(report, status="UNSUPPORTED", reason="invalid_pdf_signature")
    pages = []
    try:
        with pdfplumber.open(path) as pdf:
            report["page_count"] = len(pdf.pages)
            if pdf.doc.encryption or not 0 < len(pdf.pages) <= profile["limits"]["pages"]:
                return dict(report, status="UNSUPPORTED", reason="encrypted_or_page_limit")
            for i, page in enumerate(pdf.pages):
                summary = glyph_summary(page.chars, page.width, page.height)
                summary.update(
                    page=i + 1,
                    page_geometry_failure=page.rotation not in (0, 90, 270)
                    or tuple(page.mediabox[:2]) != (0, 0)
                    or bool(page.cropbox and tuple(page.cropbox) != tuple(page.mediabox)),
                )
                pages.append(summary)
                page.close()
    except Exception as exc:
        return dict(report, status="UNSUPPORTED", reason=type(exc).__name__)
    report["pages"] = pages
    for key in (
        "glyphs",
        "fffd",
        "missing_or_unverifiable",
        "multi_codepoint_ligatures",
        "geometry_failures",
    ):
        report[key] = sum(p[key] for p in pages)
    report["page_geometry_failures"] = sum(p["page_geometry_failure"] for p in pages)
    report["mapping_anomaly_pages"] = [p["page"] for p in pages if p["missing_or_unverifiable"]]
    if report["missing_or_unverifiable"] or report["geometry_failures"] or report["page_geometry_failures"]:
        return dict(report, status="UNSUPPORTED", reason="glyph_mapping_or_geometry")
    scope = Scope(workspace_id=UUID(int=0), kb_id=UUID(int=0), revision_id=UUID(int=0))
    try:
        blocks, hints, _ = parse_structural_pdf(path, scope, profile)
        draft = parse_structure(blocks, hints, profile)
    except ValueError as exc:
        return dict(report, status="UNSUPPORTED", reason=str(exc))
    nodes = {n["id"]: n for n in draft["nodes"]}
    numbered = [n for n in nodes.values() if n["number"]]
    report["structure"] = dict(
        nodes=len(nodes),
        numbered_nodes=len(numbered),
        max_depth=max((n["number"].count(".") + 1 for n in numbered), default=0),
        confidence=dict(Counter(n["confidence"] for n in nodes.values())),
        verified_nested=sum(
            n["confidence"] == "VERIFIED_RULE" and bool(nodes[n["parent_node_id"]]["number"])
            for n in numbered
        ),
        suitability="numbered_hierarchy" if numbered else "fallback_only",
    )
    return dict(report, status="PASS", scope="source_preflight_only_not_ingestion_acceptance")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    result = preflight(args.pdf)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
