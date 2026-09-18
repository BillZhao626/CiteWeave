"""Fail on generated-contract drift without rewriting tracked files."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from citeweave.api import create_app
from citeweave.settings import ROOT


def main():
    schema = create_app(admin_token="schema-generation-only-not-a-secret").openapi()
    for relative in ("contracts/openapi.json", "apps/web/openapi.json"):
        if json.loads((ROOT / relative).read_text(encoding="utf-8")) != schema:
            raise SystemExit("OpenAPI drift: " + relative)
    node = shutil.which("node")
    if not node:
        raise SystemExit("node_required")
    (ROOT / ".runtime").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="contract-", dir=ROOT / ".runtime") as folder:
        output = Path(folder) / "api.ts"
        subprocess.run(
            [node, "node_modules/openapi-typescript/bin/cli.js", "openapi.json", "-o", str(output)],
            cwd=ROOT / "apps/web",
            check=True,
            timeout=60,
        )
        if output.read_text(encoding="utf-8") != (ROOT / "apps/web/src/generated/api.ts").read_text(
            encoding="utf-8"
        ):
            raise SystemExit("Generated TypeScript drift")
    print("OpenAPI and generated TypeScript contracts match")


if __name__ == "__main__":
    main()
