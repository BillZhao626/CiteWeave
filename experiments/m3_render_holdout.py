"""Reproducible local PDF rendering of hash-pinned public RFC text, not publisher PDFs."""

import hashlib
import json
from uuid import UUID

import httpx
import reportlab
from reportlab.pdfgen import canvas

from citeweave.evidence import Scope
from citeweave.parsing import parse_simple_pdf
from citeweave.settings import ROOT

SOURCES = {
    2606: "b6869c8984701701bc2e6973b6ffc750d497f845cc1a65a106e9301590a13ab0",
    8174: "5ca0e2f90be0bc5928ee465f76518fee316dfa775aed885658a29a419cc293b7",
    7405: "f85c88bcf8ca8035585b39f518adfe274bb095801c95ef665b49a27b61245f17",
}


def main():
    folder = ROOT / ".runtime/evaluation/holdout-corpus"
    folder.mkdir(parents=True, exist_ok=True)
    scope = Scope(workspace_id=UUID(int=1), kb_id=UUID(int=2), revision_id=UUID(int=3))
    manifest = []
    for number, expected in SOURCES.items():
        source = folder / f"rfc{number}.txt"
        url = f"https://www.rfc-editor.org/rfc/rfc{number}.txt"
        if not source.exists():
            response = httpx.get(url, follow_redirects=True, timeout=60)
            response.raise_for_status()
            source.write_bytes(response.content)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
        raw = source.read_text(encoding="ascii")
        target = source.with_suffix(".pdf")
        temporary = source.with_suffix(".rendering.pdf")
        pdf = canvas.Canvas(str(temporary), pagesize=(612, 792), invariant=1)
        pdf.setTitle(f"RFC {number} - local rendering of official plain text")
        pdf.setAuthor("Original RFC authors; typeset locally by CiteWeave")
        for page in raw.split("\f"):
            if not page.strip():
                continue
            lines = page.strip("\r\n").splitlines()
            assert len(lines) <= 67 and max(map(len, lines)) <= 90
            pdf.setFont("Courier", 9)
            for i, line in enumerate(lines):
                pdf.drawString(36, 756 - i * 10.5, line.expandtabs(8))
            pdf.showPage()
        pdf.save()
        if target.exists():
            assert target.read_bytes() == temporary.read_bytes(), "frozen_render_drift"
            temporary.unlink()
        else:
            temporary.rename(target)
        blocks = parse_simple_pdf(target, scope)
        source.with_suffix(".lines.txt").write_text(
            "\n".join(b.block_id + " | " + b.text for b in blocks), encoding="utf-8"
        )
        manifest.append(
            dict(
                source_id=f"rfc{number}",
                filename=target.name,
                canonical_url=f"https://www.rfc-editor.org/info/rfc{number}/",
                text_url=url,
                text_sha256=expected,
                sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                rendering="local-rfc-text-courier9-v1; original RFC pages retained; blank page edges trimmed; raw PDFs excluded",
                reportlab=reportlab.Version,
                pages=max(b.boxes[0].page_index for b in blocks) + 1,
                chunks=len(blocks),
                redistribute_raw=False,
            )
        )
    (folder / "render-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
