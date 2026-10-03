"""Run public, provider-free checks from any clean checkout."""

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_release_metadata():
    versions = {
        "pyproject.toml": tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
            "version"
        ],
        "apps/web/package.json": json.loads((ROOT / "apps/web/package.json").read_text(encoding="utf-8"))[
            "version"
        ],
    }
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = [p for p in lock["package"] if p["name"] == "citeweave-rag"]
    if len(packages) != 1:
        raise SystemExit("Expected one source package in uv.lock")
    versions["uv.lock"] = packages[0]["version"]
    for name in ("contracts/openapi.json", "apps/web/openapi.json"):
        versions[name] = json.loads((ROOT / name).read_text(encoding="utf-8"))["info"]["version"]
    for name, version in versions.items():
        if version != "0.2.0":
            raise SystemExit(f"Release version mismatch: {name}")
    obsolete = re.compile(r"\b(?:v?0[.]3[.]0(?:a\d+|-alpha(?:[.]\d+)?)|v0[.]3[.]0)\b")
    if (ROOT / ".git").exists():
        # Ignored operator history is outside the current public source candidate.
        tracked = (
            subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
            .stdout.decode("utf-8")
            .split("\0")
        )
        paths = [
            ROOT / name
            for name in tracked
            if name in {"README.md", "HANDOFF.md", "AGENTS.md"}
            or (name.startswith("docs/") and name.endswith(".md"))
            or (name.startswith(("src/", "scripts/")) and name.endswith(".py"))
        ]
    else:
        # Portable source exports have no Git metadata and contain allowlisted source only.
        paths = [ROOT / "README.md", ROOT / "HANDOFF.md", ROOT / "AGENTS.md"]
        paths += list((ROOT / "docs").rglob("*.md"))
        paths += list((ROOT / "src").rglob("*.py"))
        paths += list((ROOT / "scripts").glob("*.py"))
    for path in paths:
        if obsolete.search(path.read_text(encoding="utf-8")):
            raise SystemExit(f"Obsolete release identity: {path.relative_to(ROOT)}")
    print("Release metadata is consistently 0.2.0", flush=True)


def main():
    check_release_metadata()
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
        "docs/V02_RELEASE_READINESS.md",
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
        ("offline tests", [sys.executable, "-m", "pytest", "-q", "-ra", "-m", "not integration"], ROOT),
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
