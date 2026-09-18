"""Original CC0 fixture data, independent of all benchmark/gold documents."""

import io
import re
from uuid import UUID

from reportlab.pdfgen import canvas

from citeweave.document_profiles import document_profile
from citeweave.evidence import Block, Box, Scope, digest
from citeweave.tokenization import TOKENIZERS

PROFILE = document_profile("telecom-protocol-pdf-v1")
SCOPE = Scope(workspace_id=UUID(int=901), kb_id=UUID(int=902), revision_id=UUID(int=903))


class FixtureTokenizer:
    identity = TOKENIZERS

    def count(self, texts):
        result = []
        for text in texts:
            offsets = [[m.start(), m.end()] for m in re.finditer(r"\w+|[^\w\s]", text)]
            result.append(
                dict(
                    e5=len(offsets),
                    bge=len(offsets),
                    e5_input=len(offsets) + 4,
                    bge_pair_special=4,
                    e5_offsets=offsets,
                    bge_offsets=offsets,
                )
            )
        return result


def blocks(lines, scope=SCOPE):
    result, hints = [], {}
    for i, (text, page, heading) in enumerate(lines):
        boxes = tuple(
            Box(page_index=page, left=0.1 + j * 0.0003, top=0.2, right=0.1003 + j * 0.0003, bottom=0.22)
            for j in range(len(text))
        )
        b = Block(
            scope=scope,
            source_sha256=digest("original-fixture"),
            block_id=str(i),
            text=text,
            locator_kind="pdf_bbox",
            boxes=boxes,
            char_boxes=boxes,
        )
        result.append(b)
        hints[b.block_id] = dict(
            page=page,
            bold=heading,
            font_size=14 if heading else 10,
            body_size=10,
            indent=0.1,
            whitespace_before=12 if heading else 2,
            top=0.2,
            bottom=0.22,
        )
    return result, hints


def original_pdf():
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(612, 792), invariant=1)
    for page in range(2):
        pdf.setFont("Helvetica", 9)
        pdf.drawString(60, 760, "ORIGINAL FIXTURE HEADER")
        pdf.drawString(60, 30, f"Original fixture page {page + 1}")
        y = 700
        lines = (
            [
                ("1. Transport Rules", 14),
                ("1.1. Request Handling", 12),
                ("The original request carries a marker and a bounded sequence value.", 10),
                ("Table 1. Original fields", 10),
                ("Field | Purpose", 10),
                ("Marker | Identifies the request", 10),
                ("1.1.1. Continuation", 12),
            ]
            if page == 0
            else [
                ("This paragraph continues the same original clause on the next page.", 10),
                ("2. Transport Rules", 14),
                ("A distinct section reuses the title with different source spans.", 10),
                ("Appendix A. Examples", 14),
                ("A.1. Example message", 12),
                ("An original example message contains a local marker.", 10),
            ]
        )
        for text, size in lines:
            pdf.setFont("Helvetica-Bold" if size > 10 else "Helvetica", size)
            pdf.drawString(60, y, text)
            y -= 28
        pdf.showPage()
    pdf.save()
    return output.getvalue()
