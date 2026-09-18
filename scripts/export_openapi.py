import json

from citeweave.api import create_app
from citeweave.settings import ROOT

# OpenAPI generation never opens a database or uses real credentials.
schema = (
    json.dumps(
        create_app(admin_token="schema-generation-only-not-a-secret").openapi(), ensure_ascii=False, indent=2
    )
    + "\n"
)
for relative in ("contracts/openapi.json", "apps/web/openapi.json"):
    (ROOT / relative).write_text(schema, encoding="utf-8")
print("Exported OpenAPI contract")
