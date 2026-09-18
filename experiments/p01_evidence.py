"""Original, generated fixtures; reproducible source hashes and exact quote geometry."""

import json
import subprocess
from uuid import NAMESPACE_URL, uuid5

from common import ROOT, report
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from citeweave.evidence import Block, Scope, TableCell, bind_span, digest, resolve_span, utf16_range
from citeweave.parsing import parse_simple_pdf


def main():
    output = ROOT / ".artifacts" / "p01"
    output.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    scope = Scope(
        workspace_id=uuid5(NAMESPACE_URL, "cw-m0"),
        kb_id=uuid5(NAMESPACE_URL, "p01"),
        revision_id=uuid5(NAMESPACE_URL, "p01-fixtures-v1"),
    )
    fixtures, previews = [], []
    for n in range(8):
        path = output / f"original-{n:02}.pdf"
        headings = [
            "知识库引用必须绑定不可变文档版本。",
            "证据原件使用内容摘要校验身份。",
            "检索配置升级后保留历史索引快照。",
            "任务状态由持久化数据库统一维护。",
            "中文标点：引号、括号（测试）均应保留。",
            "表格标题为证据提供必要上下文。",
            "页面顺时针旋转后仍能精确定位。",
            "页面逆时针旋转后仍能精确定位。",
        ]
        lines = [headings[n], "重复段落用于检验定位精度。", "重复段落用于检验定位精度。"]
        # ASCII identifiers use a separate fixture to avoid mixed-font baseline ambiguities in this adapter.
        if n == 3:
            lines = [
                "连接超时后进入恢复队列。",
                "失败消息保留持久化任务编号。",
                "完成结果使用唯一键避免重复写入。",
            ]
        c = canvas.Canvas(str(path), pagesize=(600, 260), invariant=1)
        c.setFont("STSong-Light", 16)
        for j, line in enumerate(lines):
            c.drawString(40, 195 - j * 65, line)
        c.save()
        if n >= 6:
            reader = PdfReader(path)
            writer = PdfWriter()
            writer.add_page(reader.pages[0].rotate(90 if n == 6 else 270))
            with path.open("wb") as stream:
                writer.write(stream)
        blocks = parse_simple_pdf(path, scope)
        assert sorted(b.text for b in blocks) == sorted(lines), [b.text for b in blocks]
        spans = []
        for b in blocks:
            # Partial quote, not merely a whole-paragraph bounding box.
            span = bind_span(b, 2, len(b.text) - 1, b.text[2:-1])
            assert resolve_span(span, b, scope) == b.text[2:-1]
            spans.append(span)
        prefix = output / f"render-{n:02}"
        subprocess.run(
            ["pdftoppm", "-scale-to", "900", "-png", "-singlefile", str(path), str(prefix)],
            check=True,
            capture_output=True,
        )
        im = Image.open(prefix.with_suffix(".png")).convert("RGBA")
        overlay = Image.new("RGBA", im.size)
        draw = ImageDraw.Draw(overlay)
        for span in spans:
            for box in span.boxes:
                draw.rectangle(
                    (box.left * im.width, box.top * im.height, box.right * im.width, box.bottom * im.height),
                    fill=(255, 200, 0, 75),
                    outline=(200, 100, 0, 150),
                )
        im = Image.alpha_composite(im, overlay).convert("RGB")
        im.save(output / f"highlight-{n:02}.png")
        previews.append(im)
        fixtures.append(
            {
                "name": path.name,
                "sha256": digest(path.read_bytes()),
                "rotation": 90 if n == 6 else 270 if n == 7 else 0,
                "blocks": [b.model_dump(mode="json") for b in blocks],
                "spans": [s.model_dump(mode="json") for s in spans],
            }
        )
    text = "中文😀证据\n重复段落。重复段落。\n跨平台偏移采用码点。"
    path = output / "unicode.txt"
    path.write_text(text, encoding="utf-8")
    spans = []
    for i, line in enumerate(text.splitlines()):
        block = Block(scope=scope, source_sha256=digest(path.read_bytes()), block_id=f"p{i}", text=line)
        start = 3 if i == 0 else 5 if i == 1 else 2
        span = bind_span(block, start, len(line), line[start:])
        assert resolve_span(span, block, scope) == line[start:]
        assert (
            line.encode("utf-16-le")[utf16_range(line, start, len(line))[0] * 2 :].decode("utf-16-le")
            == span.quote
        )
        spans.append(span.model_dump(mode="json"))
    fixtures.append({"name": path.name, "sha256": digest(path.read_bytes()), "spans": spans})
    table = {"columns": ["服务", "超时秒"], "rows": [["检索", "3"], ["重排", "5"], ["生成", "30"]]}
    path = output / "table.json"
    path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    spans = []
    for row_index, row in enumerate(table["rows"]):
        block = Block(
            scope=scope,
            source_sha256=digest(path.read_bytes()),
            block_id=f"table-0/row-{row_index}/col-1",
            text=row[1],
            locator_kind="table_cells",
            table_cell=TableCell(
                table_id="table-0",
                row_index=row_index,
                column_index=1,
                row_header=row[0],
                column_header=table["columns"][1],
            ),
        )
        span = bind_span(block, 0, len(block.text), block.text)
        assert resolve_span(span, block, scope) == row[1]
        spans.append(
            {
                "evidence": span.model_dump(mode="json"),
                "row_header": row[0],
                "column_header": table["columns"][1],
            }
        )
    fixtures.append({"name": path.name, "sha256": digest(path.read_bytes()), "spans": spans})
    (output / "fixtures.json").write_text(
        json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sheet = Image.new("RGB", (1200, 1200), "white")
    d = ImageDraw.Draw(sheet)
    for n, im in enumerate(previews):
        im.thumbnail((390, 330))
        x, y = n % 3 * 400, n // 3 * 400
        d.text((x + 10, y + 5), f"Original {n:02} / partial quote highlight", fill="black")
        sheet.paste(im, (x + 5, y + 30))
    sheet.save(output / "contact-sheet.png")
    report(
        "p01-evidence",
        {
            "status": "automated_pass_visual_review_pending",
            "documents": len(fixtures),
            "spans_verified": sum(len(f["spans"]) for f in fixtures),
            "partial_pdf_spans": 24,
            "rotations": [0, 90, 270],
            "unicode_utf16_verified": True,
            "fixtures": [{"name": f["name"], "sha256": f["sha256"]} for f in fixtures],
            "limitations": [
                "simple text PDFs only",
                "table fixture is structured JSON, not PDF table extraction",
                "no OCR, merged cells, arbitrary rotations or complex layout certification",
            ],
        },
    )


if __name__ == "__main__":
    main()
