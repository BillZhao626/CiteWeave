"""M0 horizontal and 90/270-degree text PDF adapter. No OCR or layout guessing."""

from pathlib import Path

import pdfplumber

from citeweave.evidence import Block, Box, Scope, digest


def parse_simple_pdf(path: Path, scope: Scope) -> list[Block]:
    blocks = []
    source_hash = digest(path.read_bytes())
    with pdfplumber.open(path) as pdf:
        for index, page in enumerate(pdf.pages):
            if page.rotation not in (0, 90, 270):
                raise ValueError("unsupported_page_rotation")
            if not page.chars:
                raise ValueError("no_text_ocr_required")
            # pdfplumber exposes display coordinates after /Rotate; group original text baselines.
            vertical = page.rotation in (90, 270)
            groups = {}
            for char in page.chars:
                if len(char["text"]) != 1:
                    raise ValueError("unsupported_glyph_to_codepoint_mapping")
                axis = char["x0"] if vertical else char["top"]
                groups.setdefault(round(axis, 1), []).append(char)
            for number, (_, chars) in enumerate(sorted(groups.items())):
                chars.sort(key=lambda c: c["top"] if vertical else c["x0"], reverse=page.rotation == 270)
                text = "".join(c["text"] for c in chars)
                boxes = tuple(
                    Box(
                        page_index=index,
                        left=c["x0"] / page.width,
                        top=c["top"] / page.height,
                        right=c["x1"] / page.width,
                        bottom=c["bottom"] / page.height,
                    )
                    for c in chars
                )
                blocks.append(
                    Block(
                        scope=scope,
                        source_sha256=source_hash,
                        block_id=f"page-{index}-line-{number}",
                        text=text,
                        locator_kind="pdf_bbox",
                        boxes=boxes,
                        char_boxes=boxes,
                        normalizer_revision="pdfplumber-display-glyph-v1",
                    )
                )
    return blocks
