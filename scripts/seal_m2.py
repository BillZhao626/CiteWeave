"""Hash explicit publication candidates and check actual local secrets without printing them."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone

from citeweave.settings import ROOT, settings

ALLOWED_DIRS = {
    "src",
    "tests",
    "experiments",
    "deploy",
    "docs",
    "contracts",
    "apps",
    "scripts",
    "migrations",
    "prompts",
    "evals",
}
ALLOWED_FILES = {
    ".dockerignore",
    ".gitignore",
    ".env.example",
    "README.md",
    "AGENTS.md",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
    "requirements-models.lock",
    "requirements-worker.lock",
}
TARGET = "docs/reports/m2-manifest.json"


def main():
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    files = sorted(set(raw.decode("utf-8").split("\0")) - {"", TARGET})
    config = settings()
    secrets = [
        value.encode()
        for value in (
            config.admin_token.get_secret_value(),
            config.db_password.get_secret_value(),
            config.deepseek_api_key.get_secret_value(),
            config.gateway_token(),
        )
        if value
    ]
    hashes = {}
    for name in files:
        if name.split("/")[0] not in ALLOWED_DIRS and name not in ALLOWED_FILES:
            raise RuntimeError("outside_publication_allowlist: " + name)
        path = ROOT / name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError("unsafe_candidate_path: " + name)
        data = path.read_bytes()
        if any(secret in data for secret in secrets):
            raise RuntimeError("local_secret_in_candidate: " + name)
        hashes[name] = hashlib.sha256(data).hexdigest()
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "candidate_files": len(hashes),
        "actual_local_secret_scan": "passed",
        "scan_scope": "exact active admin/DB/model/provider secrets; not a general secret detector",
        "private_runtime_cache_excluded": True,
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "fastapi",
                "pydantic",
                "sqlalchemy",
                "alembic",
                "celery",
                "qdrant-client",
                "pdfplumber",
            )
        },
        "publication": "local candidate manifest only; no remote publication",
        "sha256": hashes,
    }
    (ROOT / TARGET).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"M2: {len(hashes)} candidate files hashed; active local secrets excluded")


if __name__ == "__main__":
    main()
