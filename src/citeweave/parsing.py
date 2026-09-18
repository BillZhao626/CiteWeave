"""M0 horizontal and 90/270-degree text PDF adapter. No OCR or layout guessing."""

from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError
from pdfplumber.utils.exceptions import PdfminerException

from citeweave.evidence import Block, Box, Scope, digest


def glyph_mapping_supported(text: str) -> bool:
    return "\ufffd" not in text and (len(text) == 1 or text in {"ff", "fi", "fl", "ffi", "ffl", "st"})


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


def parse_structural_pdf(path: Path, scope: Scope, profile: dict):
    """New-version extractor. Original glyphs stay literal; layout is a sidecar.

    Pages release pdfplumber caches immediately. No OCR, inferred cell text, or
    text normalization is used. Small baseline differences are grouped only in
    this explicitly versioned adapter; the legacy extractor above is unchanged.
    """
    from collections import Counter
    from statistics import median

    from citeweave.document_profiles import validate_profile
    from citeweave.trace import ingestion_guard

    validate_profile(profile)
    if path.stat().st_size > profile["limits"]["bytes"]:
        raise ValueError("structural_pdf_byte_limit")
    source_hash = digest(path.read_bytes())
    blocks, hints = [], {}
    try:
        document = pdfplumber.open(path)
    except PDFPasswordIncorrect:
        raise ValueError("unsupported_encrypted_pdf") from None
    except PDFSyntaxError:
        raise ValueError("unsupported_pdf_syntax") from None
    except PdfminerException as exc:
        code = (
            "unsupported_encrypted_pdf"
            if exc.args and isinstance(exc.args[0], PDFPasswordIncorrect)
            else "unsupported_pdf_syntax"
        )
        raise ValueError(code) from None
    with document as pdf:
        if pdf.doc.encryption:
            raise ValueError("unsupported_encrypted_pdf")
        if not 0 < len(pdf.pages) <= profile["limits"]["pages"]:
            raise ValueError("structural_pdf_page_limit")
        page_count = len(pdf.pages)
        for page_index, page in enumerate(pdf.pages):
            if guard := ingestion_guard.get():
                guard()
            if page.rotation not in (0, 90, 270):
                raise ValueError("unsupported_page_rotation")
            if tuple(page.mediabox[:2]) != (0, 0) or (
                page.cropbox and tuple(page.cropbox) != tuple(page.mediabox)
            ):
                raise ValueError("unsupported_page_geometry")
            chars = page.chars
            if not chars:
                raise ValueError("unsupported_no_text")
            if any(not glyph_mapping_supported(c["text"]) for c in chars):
                raise ValueError("unsupported_glyph_to_codepoint_mapping")
            vertical = page.rotation in (90, 270)
            axis = "x0" if vertical else "top"
            groups = []
            for char in sorted(chars, key=lambda c: c[axis]):
                if not groups or abs(groups[-1][0][axis] - char[axis]) > 2:
                    groups.append([])
                groups[-1].append(char)
            body_size = Counter(round(c["size"], 1) for c in chars).most_common(1)[0][0]
            # Only explicit ruling lines establish cells. Borderless layouts remain unresolved.
            tables = page.find_tables() if not vertical and len(page.lines) + len(page.rects) >= 4 else []
            previous_end = 0
            large_gaps = 0
            for number, line in enumerate(groups):
                line.sort(key=lambda c: c["top"] if vertical else c["x0"], reverse=page.rotation == 270)
                # Marginal line labels remain canonical blocks with an exclusion reason.
                margin = [c for c in line if not vertical and c["x1"] < page.width * 0.095]
                rest = [c for c in line if c not in margin]
                pieces = [line]
                if margin and rest and "".join(c["text"] for c in margin).strip().isdigit():
                    pieces = [margin, rest]
                for part, glyphs in enumerate(pieces):
                    text = "".join(c["text"] for c in glyphs)
                    if not text.strip():
                        continue
                    boxes = tuple(
                        Box(
                            page_index=page_index,
                            left=c["x0"] / page.width,
                            top=c["top"] / page.height,
                            right=c["x1"] / page.width,
                            bottom=c["bottom"] / page.height,
                        )
                        for c in glyphs
                        for _ in c["text"]
                        if c["x0"] < c["x1"] and c["top"] < c["bottom"]
                    )
                    if len(boxes) != len(text):
                        raise ValueError("unsupported_empty_glyph_geometry")
                    identity = f"page-{page_index}-line-{number}-part-{part}"
                    blocks.append(
                        Block(
                            scope=scope,
                            source_sha256=source_hash,
                            block_id=identity,
                            text=text,
                            locator_kind="pdf_bbox",
                            boxes=(
                                Box(
                                    page_index=page_index,
                                    left=min(b.left for b in boxes),
                                    top=min(b.top for b in boxes),
                                    right=max(b.right for b in boxes),
                                    bottom=max(b.bottom for b in boxes),
                                ),
                            ),
                            char_boxes=boxes,
                            normalizer_revision="pdfplumber-structural-glyph-v2",
                        )
                    )
                    font_names = [c["fontname"].lower() for c in glyphs]
                    mono = sum("mono" in f or "courier" in f for f in font_names) > len(glyphs) / 2
                    gaps = [b["x0"] - a["x1"] for a, b in zip(glyphs, glyphs[1:])]
                    max_gap = max(gaps, default=0)
                    # Prose columns cannot be reconstructed by concatenating their lines.
                    if not vertical and max_gap > page.width * 0.18 and len(text) > 90 and not mono:
                        large_gaps += 1
                    top, bottom = min(c["top"] for c in glyphs), max(c["bottom"] for c in glyphs)
                    hint = dict(
                        page=page_index,
                        font_size=median(c["size"] for c in glyphs),
                        body_size=body_size,
                        bold=sum("bold" in f for f in font_names) > len(glyphs) / 2,
                        indent=min(c["x0"] for c in glyphs) / page.width,
                        whitespace_before=max(0, top - previous_end),
                        top=top / page.height,
                        bottom=bottom / page.height,
                        monospace=mono,
                        table_confidence="unresolved" if mono or "|" in text else None,
                    )
                    offset, glyph_groups = 0, []
                    for glyph in glyphs:
                        end = offset + len(glyph["text"])
                        if end - offset > 1:
                            glyph_groups.append(
                                {
                                    "start": offset,
                                    "end": end,
                                    "text": glyph["text"],
                                    "box": boxes[offset].model_dump(mode="json"),
                                }
                            )
                        offset = end
                    if glyph_groups:
                        hint["glyph_groups"] = glyph_groups
                    for table_index, table in enumerate(tables):
                        cells = []
                        for row_index, row in enumerate(table.rows):
                            for column_index, cell in enumerate(row.cells):
                                if cell is None:
                                    continue
                                indices = []
                                offset = 0
                                for glyph in glyphs:
                                    cx, cy = (
                                        (glyph["x0"] + glyph["x1"]) / 2,
                                        (glyph["top"] + glyph["bottom"]) / 2,
                                    )
                                    if cell[0] <= cx <= cell[2] and cell[1] <= cy <= cell[3]:
                                        indices.extend(range(offset, offset + len(glyph["text"])))
                                    offset += len(glyph["text"])
                                if indices and indices == list(range(min(indices), max(indices) + 1)):
                                    cells.append(
                                        dict(
                                            row=row_index,
                                            column=column_index,
                                            start=min(indices),
                                            end=max(indices) + 1,
                                            bbox=[
                                                cell[0] / page.width,
                                                cell[1] / page.height,
                                                cell[2] / page.width,
                                                cell[3] / page.height,
                                            ],
                                        )
                                    )
                        if cells:
                            hint.update(
                                table_confidence="verified_grid",
                                table_id=f"page-{page_index}-table-{table_index}",
                                cells=cells,
                                table_header=hint["bold"] and all(c["row"] == 0 for c in cells),
                            )
                            break
                    if len(pieces) == 2 and part == 0:
                        hint["excluded"] = "marginal_line_label"
                    hints[identity] = hint
                    previous_end = max(previous_end, bottom)
            if large_gaps >= 8:
                raise ValueError("unsupported_multiple_prose_columns")
            # Limit canonical growth before constructing any derived structures.
            if sum((len(b.text) + 159) // 160 for b in blocks) > profile["limits"]["atoms"]:
                raise ValueError("structural_atom_limit")
            page.close()
    return blocks, hints, page_count
