"""Run public, provider-free checks from any clean checkout."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = {k: v for k, v in os.environ.items() if not k.startswith("CW_")}
    env.update(
        DEEPSEEK_API_KEY="",
        CW_ADMIN_TOKEN="",
        CW_DB_PASSWORD="",
        CW_DATABASE_URL="",
        CW_MODEL_TOKEN="",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        PYTHONIOENCODING="utf-8",
    )
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required; see docs/QUICKSTART.md")
    documents = [
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/README.md",
        "docs/ARCHITECTURE.md",
        "docs/QUICKSTART.md",
        "docs/CORPUS.md",
    ]
    for name in documents:
        path = ROOT / name
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" not in target and not target.startswith("#"):
                if not (path.parent / target.split("#")[0]).is_file():
                    raise SystemExit(f"Missing documentation target in {name}: {target}")
    for name in ("LICENSE", ".env.example", "uv.lock", "apps/web/pnpm-lock.yaml"):
        if not (ROOT / name).is_file():
            raise SystemExit(f"Missing release file: {name}")
    scopes = ["src", "tests", "scripts", "migrations"]
    checks = [
        ("backend lint", [sys.executable, "-m", "ruff", "check", *scopes], ROOT),
        ("backend format", [sys.executable, "-m", "ruff", "format", "--check", *scopes], ROOT),
        ("offline tests", [sys.executable, "-m", "pytest", "-q", "-m", "not integration"], ROOT),
        ("PDF.js assets and notices", [sys.executable, "scripts/prepare_web.py"], ROOT),
        ("generated API contracts", [sys.executable, "scripts/check_contracts.py"], ROOT),
        ("frontend typecheck", [node, "node_modules/typescript/bin/tsc", "--noEmit"], ROOT / "apps/web"),
        ("frontend lint", [node, "node_modules/eslint/bin/eslint.js", "."], ROOT / "apps/web"),
        ("frontend tests", [node, "node_modules/vitest/vitest.mjs", "run"], ROOT / "apps/web"),
        ("frontend build", [node, "node_modules/vite/bin/vite.js", "build"], ROOT / "apps/web"),
    ]
    for label, command, cwd in checks:
        print(f"Checking {label}", flush=True)
        subprocess.run(command, cwd=cwd, env=env, check=True, timeout=300)
    print("Public offline checks passed. Real services/models/provider calls were not tested.")


if __name__ == "__main__":
    main()
