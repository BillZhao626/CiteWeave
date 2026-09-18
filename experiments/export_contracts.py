"""Generated schemas are checked in; secrets and local paths are never exported."""

import json
from uuid import UUID

from common import ROOT

from citeweave.api import create_app
from citeweave.evidence import Block, EvidenceSpan

output = ROOT / "contracts"
output.mkdir(exist_ok=True)
schemas = {
    "evidence-span.v0.1.schema.json": EvidenceSpan.model_json_schema(),
    "block.v0.1.schema.json": Block.model_json_schema(),
    "openapi.json": create_app("schema-generation-placeholder-only", UUID(int=1)).openapi(),
}
for filename, data in schemas.items():
    (output / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("Exported evidence, block and implemented M1 OpenAPI contracts")
