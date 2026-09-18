"""Stage an explicit source allowlist, scan it, and create a local source archive."""

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from citeweave.settings import ROOT, settings

DIRECTORIES = {
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
FILES = {
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
    "LICENSE",
    "CONTRIBUTING.md",
    "THIRD_PARTY.md",
}
EXCLUDED_DOCS = {
    "docs/01_调研论证与合规边界.md",
    "docs/02_架构与技术决策.md",
    "docs/03_实施路线与求职交付.md",
    "docs/04_官方参考资料.md",
}
REPORT = "docs/reports/m3-manifest.json"
FORBIDDEN = {".git", ".runtime", ".cache", ".venv", "node_modules", "dist", "__pycache__", "审计私有"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_files():
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    selected = []
    for name in sorted(set(raw.decode("utf-8").split("\0")) - {"", REPORT}):
        relative = Path(name)
        if name in EXCLUDED_DOCS or relative.name.endswith("CHECKPOINT.md"):
            continue
        if relative.parts[0] not in DIRECTORIES and name not in FILES:
            raise ValueError("outside_public_allowlist: " + name)
        if FORBIDDEN.intersection(relative.parts) or (
            relative.name.startswith(".env") and name != ".env.example"
        ):
            raise ValueError("forbidden_candidate_path: " + name)
        if (
            relative.suffix.lower()
            in {".pdf", ".sqlite", ".sqlite3", ".dump", ".safetensors", ".exe", ".whl"}
            and name != "apps/web/public/original-handbook.pdf"
        ):
            raise ValueError("unapproved_binary: " + name)
        path = ROOT / relative
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("unsafe_candidate_path: " + name)
        selected.append(name)
    return selected


def stage():
    directory = ROOT / ".runtime/releases" / uuid4().hex
    source = directory / "source"
    source.mkdir(parents=True)
    config = settings()
    secrets = [
        v.encode()
        for v in (
            config.admin_token.get_secret_value(),
            config.db_password.get_secret_value(),
            config.deepseek_api_key.get_secret_value(),
            config.gateway_token(),
        )
        if v
    ]
    hashes = {}
    for name in candidate_files():
        original = ROOT / name
        data = original.read_bytes()
        if any(secret in data for secret in secrets):
            raise ValueError("active_secret_in_candidate: " + name)
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    return directory, source, hashes


def scan(directory, source, scanner):
    if not scanner.is_file():
        raise ValueError("gitleaks_binary_required")
    version = subprocess.check_output([str(scanner), "version"], text=True, timeout=20).strip()
    report = directory / "gitleaks-redacted.json"
    result = subprocess.run(
        [
            str(scanner),
            "dir",
            str(source),
            "--redact=100",
            "--no-banner",
            "--report-format",
            "json",
            "--report-path",
            str(report),
        ],
        capture_output=True,
        timeout=120,
    )
    findings = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
    reviewed = json.loads((ROOT / "docs/reports/m3-secret-scan-allowlist.json").read_text(encoding="utf-8"))[
        "entries"
    ]
    allowed = {(r["file"], r["rule"], r["line_sha256"]) for r in reviewed}
    unresolved = []
    for finding in findings or []:
        path = Path(finding["File"])
        if not path.is_absolute():
            path = source / path
        path = path.resolve()
        if not path.is_relative_to(source.resolve()):
            raise ValueError("scanner_path_outside_candidate")
        line = path.read_text(encoding="utf-8").splitlines()[finding["StartLine"] - 1]
        identity = (
            path.relative_to(source).as_posix(),
            finding["RuleID"],
            hashlib.sha256(line.encode()).hexdigest(),
        )
        if finding["StartLine"] != finding["EndLine"] or identity not in allowed:
            unresolved.append(identity[:2])
    if result.returncode not in (0, 1) or findings is None or unresolved:
        # Never print scanner output; even a detector can include a sensitive line.
        raise RuntimeError("candidate_secret_scan_failed; inspect redacted local report")
    return dict(
        tool="gitleaks",
        version=version,
        binary_sha256=sha(scanner),
        raw_findings=len(findings),
        reviewed_nonsecret_hash_lines=len(findings),
        unresolved_findings=0,
        scope="allowlisted source directory, default detection rules; no Git history exists",
        actual_local_secret_scan="passed",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--scanner", type=Path, default=ROOT / ".runtime/tools/gitleaks.exe")
    args = parser.parse_args()
    if not args.stage_only:
        from audit_m3_release import main as audit_release

        audit_release()
    directory, source, hashes = stage()
    scan_result = scan(directory, source, args.scanner.resolve())
    report = dict(
        at=datetime.now(timezone.utc).isoformat(),
        candidate_files=len(hashes),
        sha256=hashes,
        secret_scan=scan_result,
        excluded="private audits, initial local review/planning documents, checkpoints, runtime, credentials, raw third-party PDFs, dependency binaries and caches",
        publication="local source candidate; no remote publication",
        status="STAGED" if args.stage_only else "SEALED",
    )
    if not args.stage_only:
        from freeze_m3 import main as verify_freeze

        verify_freeze()
        for required in (
            "m3-gates.json",
            "m3-faults.json",
            "m3-recovery.json",
            "m3-clean-install.json",
            "m3-selected-test.json",
            "M3_ACCEPTANCE.md",
            "m3-sbom.cdx.json",
            "m3-release-audit.json",
            "m3-browser.json",
            "m3-sbom-validation.json",
        ):
            if not (source / "docs/reports" / required).is_file():
                raise ValueError("missing_release_evidence: " + required)
        gates = json.loads((source / "docs/reports/m3-gates.json").read_text(encoding="utf-8"))
        clean = json.loads((source / "docs/reports/m3-clean-install.json").read_text(encoding="utf-8"))
        faults = json.loads((source / "docs/reports/m3-faults.json").read_text(encoding="utf-8"))
        assert (
            len(gates["results"]) == 9
            and all(g["passed"] for g in gates["results"])
            and clean["status"] == "PASS"
            and faults["passed"] == 3
        )
        for name in (
            "m3-release-audit.json",
            "m3-recovery.json",
            "m3-browser.json",
            "m3-sbom-validation.json",
        ):
            evidence = json.loads((source / "docs/reports" / name).read_text(encoding="utf-8"))
            assert evidence["status"] == "PASS", "release_evidence_failed: " + name
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    (directory / "manifest.json").write_text(payload, encoding="utf-8")
    if not args.stage_only:
        (ROOT / REPORT).write_text(payload, encoding="utf-8")
        (source / REPORT).write_text(payload, encoding="utf-8")
        archive = directory / "CiteWeave-0.3.0-alpha.1-source.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    output.write(path, "CiteWeave/" + path.relative_to(source).as_posix())
        (directory / "archive.sha256").write_text(sha(archive) + "  " + archive.name + "\n", encoding="utf-8")
    pointer = ROOT / ".runtime/releases/latest.json"
    pointer.write_text(
        json.dumps(dict(directory=str(directory), source=str(source), status=report["status"]), indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            dict(source=str(source), files=len(hashes), secret_findings=0, status=report["status"]),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
