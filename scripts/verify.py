"""Reproducible gates with explicit CLIs and an isolated PostgreSQL test database."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from uuid import uuid4

from citeweave.settings import ROOT, settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--milestone", choices=["m1", "m2", "m3"], default="m3")
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument(
        "--report-prefix", help="Distinct report filename prefix; preserves historical milestone reports"
    )
    args = parser.parse_args()
    label = args.report_prefix or args.milestone
    if not label.replace("-", "").isalnum():
        raise ValueError("invalid_report_prefix")
    node = shutil.which("node")
    if not node:
        raise SystemExit("node_required")
    config = settings()
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(config.db_url())
    database = "cw_suite_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text('CREATE DATABASE "' + database + '"'))
    url = url.set(database=database)
    env = dict(
        os.environ,
        CW_RUN_INTEGRATION="1",
        CW_DATABASE_URL=url.render_as_string(hide_password=False).replace(
            "postgresql+psycopg://", "postgresql://"
        ),
        PYTHONIOENCODING="utf-8",
    )
    checks = [
        ("pdf_assets", [sys.executable, "scripts/prepare_web.py"], ROOT),
        ("generated_contracts", [sys.executable, "scripts/check_contracts.py"], ROOT),
        (
            "backend_lint",
            [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts", "migrations"],
            ROOT,
        ),
        (
            "backend_format",
            [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts", "migrations"],
            ROOT,
        ),
        (
            "backend_tests",
            [sys.executable, "-m", "pytest", "-q", f"--junitxml=docs/reports/{label}-tests.xml"],
            ROOT,
        ),
        ("frontend_lint", [node, "node_modules/eslint/bin/eslint.js", "."], ROOT / "apps/web"),
        ("frontend_typecheck", [node, "node_modules/typescript/bin/tsc", "--noEmit"], ROOT / "apps/web"),
        (
            "frontend_tests",
            [
                node,
                "node_modules/vitest/vitest.mjs",
                "run",
                "--reporter=json",
                f"--outputFile=../../docs/reports/{label}-frontend-tests.json",
            ],
            ROOT / "apps/web",
        ),
        ("frontend_build", [node, "node_modules/vite/bin/vite.js", "build"], ROOT / "apps/web"),
    ]
    results = []
    if args.backend_only:
        checks = [check for check in checks if not check[0].startswith("frontend")]
    try:
        for name, command, cwd in checks:
            try:
                result = subprocess.run(command, cwd=cwd, env=env, timeout=300)
                results.append(
                    {"gate": name, "exit_code": result.returncode, "passed": result.returncode == 0}
                )
            except subprocess.TimeoutExpired:
                results.append({"gate": name, "error": "timeout", "passed": False})
    finally:
        with admin.connect() as connection:
            connection.execute(text('DROP DATABASE "' + database + '"'))
        admin.dispose()
    (ROOT / f"docs/reports/{label}-{'backend-' if args.backend_only else ''}gates.json").write_text(
        json.dumps({"at": datetime.now(timezone.utc).isoformat(), "results": results}, indent=2),
        encoding="utf-8",
    )
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
