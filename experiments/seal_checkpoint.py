"""Record current independent source hashes and verify the actual local secrets are excluded."""

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from datetime import UTC, datetime

from common import ROOT

allowed = {"src", "tests", "experiments", "deploy", "docs", "contracts", "apps"}
allowed_files = {
    ".dockerignore",
    ".gitignore",
    "README.md",
    "pyproject.toml",
    "uv.lock",
    "requirements-models.lock",
    "requirements-worker.lock",
}
raw = subprocess.check_output(
    ["git", "-c", "core.quotepath=false", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
    cwd=ROOT,
)
files = sorted(set(raw.decode("utf-8").split("\0")) - {""})
secrets = [
    line.split("=", 1)[1]
    for line in (ROOT / ".env").read_text().splitlines()
    if line.startswith(("CW_DB_PASSWORD=", "CW_ADMIN_TOKEN="))
]
hashes = {}
for name in files:
    path = ROOT / name
    if name == "docs/reports/checkpoint-manifest.json":
        continue
    assert name.split("/")[0] in allowed or name in allowed_files, f"not_in_export_allowlist:{name}"
    data = path.read_bytes()
    assert not any(secret.encode() in data for secret in secrets), f"secret_found_in_candidate:{name}"
    hashes[name] = hashlib.sha256(data).hexdigest()
record = {
    "recorded_at_utc": datetime.now(UTC).isoformat(),
    "python": platform.python_version(),
    "platform": platform.platform(),
    "dependencies": {
        name: importlib.metadata.version(name)
        for name in [
            "fastapi",
            "pydantic",
            "psycopg",
            "celery",
            "kombu",
            "redis",
            "qdrant-client",
            "jieba",
            "pdfplumber",
        ]
    },
    "candidate_files": len(hashes),
    "local_secret_scan": "passed",
    "private_audit_and_runtime_excluded": True,
    "git_state": "initialized main; no authored commit or remote publication",
    "sha256": hashes,
}
(ROOT / "docs/reports/checkpoint-manifest.json").write_text(
    json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"Checkpoint: {len(hashes)} independent candidate files hashed; local secrets excluded")
