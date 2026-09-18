"""Original M0 fixtures only; disabled by default."""

import json
from uuid import UUID

from fastapi import HTTPException
from fastapi.responses import FileResponse

from citeweave.evidence import Block, EvidenceSpan, resolve_span


def install_lab(app, lab_root):
    # This optional lab reads only fixed original-fixture paths; disable lab_root outside local development.
    if lab_root is not None:

        def fixtures():
            path = lab_root / ".artifacts/p01/fixtures.json"
            if not path.is_file():
                raise HTTPException(503, "run_p01_first")
            return json.loads(path.read_text(encoding="utf-8"))[:8]

        @app.get("/lab/fixtures")
        def lab_fixtures():
            return fixtures()

        @app.get("/lab/evidence/{identity}")
        def lab_evidence(identity: UUID):
            for page_index, fixture in enumerate(fixtures()):
                blocks = {b["block_id"]: Block.model_validate(b) for b in fixture["blocks"]}
                for data in fixture["spans"]:
                    span = EvidenceSpan.model_validate(data)
                    if span.id == identity:
                        block = blocks[span.block_id]
                        resolve_span(span, block, block.scope)  # fixed original, explicitly public lab scope
                        return {"span": span, "block": block, "page_image": f"/lab/pages/{page_index}"}
            raise HTTPException(404, "evidence_not_found")

        @app.get("/lab/pages/{page}")
        def lab_page(page: int):
            if page not in range(8):
                raise HTTPException(404, "page_not_found")
            path = lab_root / f".artifacts/p01/render-{page:02}.png"
            if not path.is_file():
                raise HTTPException(404, "page_not_found")
            return FileResponse(path, media_type="image/png")

        @app.get("/lab/reports")
        def lab_reports():
            result = {}
            for key in ["p01-evidence", "p02-retrieval", "p03-recovery"]:
                path = lab_root / "docs/reports" / f"{key}.json"
                result[key] = (
                    json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"status": "not_run"}
                )
            return result
