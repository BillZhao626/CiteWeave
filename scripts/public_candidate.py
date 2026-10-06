"""Stage and scan an explicit local source candidate; never publish or tag."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
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
    "corpus",
    "benchmarks",
    ".github",
}
FILES = {
    ".dockerignore",
    ".gitignore",
    ".env.example",
    "README.md",
    "AGENTS.md",
    "HANDOFF.md",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
    "requirements-models.lock",
    "requirements-worker.lock",
    "LICENSE",
    "CONTRIBUTING.md",
    "THIRD_PARTY.md",
    "THIRD_PARTY_NOTICES.md",
    ".gitattributes",
}
EXCLUDED_DOCS = {
    "docs/01_调研论证与合规边界.md",
    "docs/02_架构与技术决策.md",
    "docs/03_实施路线与求职交付.md",
    "docs/04_官方参考资料.md",
}
REPORT = "docs/reports/m3-manifest.json"
PUBLIC_REVIEW_FIXTURES = {
    "evals/reviews/m1-baseline-human.json",
    "evals/reviews/m2-dev-24/M2_Dev24_人工复核.md",
    "evals/reviews/m2-dev-24/M2_Dev24_人工复核_已填写.md",
    "evals/reviews/m2-dev-24/M2_Dev24_人工复核_标签.json",
    "evals/reviews/m2-dev-24/m2-dev-24-review-template.json",
}
FORBIDDEN = {".git", ".runtime", ".cache", ".venv", "node_modules", "dist", "__pycache__", "审计私有"}

# Explicit reviewed documentation, never an automatic recursive docs publication.
PUBLIC_DOCS = {
    "docs/ADR_C3_STRUCTURAL_QUERY_EVIDENCE.md",
    "docs/ADR_C4_DURABLE_EVALUATION.md",
    "docs/ADR_C5_PRODUCT_INSPECTION.md",
    "docs/ADR_PUBLIC_TELECOM_CORPUS_DELTA.md",
    "docs/ADR_PUBLIC_TELECOM_FINAL_REPLACEMENT.md",
    "docs/ADR_STRUCTURAL_GLYPH_GROUPS.md",
    "docs/ADR_STRUCTURAL_INGESTION.md",
    "docs/AI_DEVELOPMENT_PLAYBOOK.md",
    "docs/API.md",
    "docs/ARCHITECTURE.md",
    "docs/CORPUS.md",
    "docs/CURRENT_ARCHITECTURE.md",
    "docs/CURRENT_OPERATIONS.md",
    "docs/DATA_NOTICES.md",
    "docs/ENGINEERING_GOVERNANCE.md",
    "docs/M1_API_USAGE.md",
    "docs/M2_API_USAGE.md",
    "docs/M2_LIMITATIONS.md",
    "docs/M3_API_USAGE.md",
    "docs/PROVENANCE.md",
    "docs/QUICKSTART.md",
    "docs/README.md",
    "docs/V02B_CONCURRENCY_PERFORMANCE_M3.md",
    "docs/V02B_OPERATIONAL_OBSERVABILITY_M2.md",
    "docs/V02B_RUNTIME_RELIABILITY_EVIDENCE.md",
    "docs/V02B_RUNTIME_RELIABILITY_M1.md",
    "docs/V02_0012_REVISION_REVIEW.md",
    "docs/V02_BLUEPRINT.md",
    "docs/V02_COMPARISON_PROTOCOL.md",
    "docs/V02_CONVERSATIONAL_CALIBRATION_PLAN.md",
    "docs/V02_CONVERSATIONAL_RAG_ARCHITECTURE.md",
    "docs/V02_DEV_CAMPAIGN_IDENTITY_REVIEW.md",
    "docs/V02_DEV_DATA_REVIEW.md",
    "docs/V02_DEV_DATA_REVIEW_V1.md",
    "docs/V02_DEV_DATA_REVIEW_V2.md",
    "docs/V02_DEV_DATA_REVIEW_V3_PRE_FREEZE.md",
    "docs/V02_DEV_HUMAN_GOLD_FREEZE.md",
    "docs/V02_DEV_PAID_EXECUTION_AUTHORIZATION.md",
    "docs/V02_DEV_READINESS.md",
    "docs/V02_DEV_READINESS_BLOCKER.md",
    "docs/V02_DEV_READINESS_V1.md",
    "docs/V02_DEV_READINESS_V2.md",
    "docs/V02_DEV_READINESS_V3_PRE_FREEZE.md",
    "docs/V02_DEV_TEST_FIRST_AUDIT.md",
    "docs/V02_DEV_TEST_FIRST_AUDIT_V3.md",
    "docs/V02_DYNAMIC_PROVENANCE_CONTRACT.md",
    "docs/V02_FOUNDATION.md",
    "docs/V02_LOCAL_CALIBRATION_EXECUTION_PLAN.md",
    "docs/V02_P0_INTERPRETATION_REPAIR.md",
    "docs/V02_PROVIDER_OBSERVATION_REMEDIATION_REVIEW.md",
    "docs/V02_RC_NARROW_CLOSURE.md",
    "docs/V02_RELEASE_READINESS.md",
    "docs/V02_RESIDUAL_ROOT_CAUSE_CLOSURE.md",
    "docs/V02_RUNTIME_RECONCILIATION.md",
    "docs/V02_RUNTIME_STABILIZATION.md",
    "docs/adr/0005-runtime-convergence.md",
    "docs/adr/0006-conversation-state-and-effective-commit.md",
    "docs/adr/0007-memory-and-documentary-evidence.md",
    "docs/adr/0008-bounded-conversational-context.md",
    "docs/adr/0009-conversation-profile-and-trace.md",
    "docs/adr/0010-conversation-core-storage.md",
    "docs/adr/0011-conversation-provider-ledger.md",
    "docs/adr/0012-dev-campaign-settlement.md",
    "docs/adr/0013-dev-campaign-execution-namespace.md",
    "docs/adr/0014-interpretation-wire-format.md",
    "docs/adr/0015-interpretation-runtime-stabilization.md",
    "docs/adr/0016-selective-runtime-reconciliation.md",
    "docs/adr/0017-rc-narrow-closure.md",
    "docs/adr/0018-residual-runtime-normal-form.md",
    "docs/adr/0023-runtime-reliability-and-recovery.md",
    "docs/adr/0024-operational-trace-and-recovery-inspection.md",
    "docs/adr/0025-acceptance-evidence-session.md",
    "docs/adr/0026-shared-conversation-scope-readers.md",
    "docs/adr/0027-production-interpretation-wire-origins.md",
    "docs/adr/0028-bounded-accepted-history-projection.md",
    "docs/adr/0029-explicit-candidate-history-relevance.md",
    "docs/adr/0030-read-only-runtime-observations.md",
    "docs/adr/0031-read-only-publication-and-reliability-inspection.md",
    "docs/adr/0032-read-only-context-observations.md",
    "docs/assets/product/context-inspection.png",
    "docs/assets/product/multiturn-followup.png",
    "docs/assets/product/product-workspace.png",
    "docs/data/public_telecom_sources.md",
    "docs/history/ARCHITECTURE_IMPLEMENTATION_RECORDS.md",
    "docs/images/answer-evidence.png",
    "docs/images/pdf-location.png",
    "docs/provenance/independent-development.md",
    "docs/provenance/third-party.md",
    "docs/specs/07_V02_First_Conversational_Slice.md",
    "docs/specs/08_V02_Conversational_Evaluation.md",
}


def check_content(name, data):
    if Path(name).suffix.lower() in {".png", ".pdf"}:
        return
    value = data.decode("utf-8", errors="strict")
    # Match concrete machine paths, not portable examples or regex definitions.
    if re.search(
        r"[A-Za-z]:[\\/](?:Users|TEMP|Projects|Material)[\\/]|/(?:Users|home)/[A-Za-z0-9_.-]+/", value
    ):
        raise ValueError("private_machine_path: " + name)
    if re.search(r"-{5}BEGIN (?:RSA )?PRIVATE KEY-{5}", value):
        raise ValueError("private_key_material: " + name)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_files():
    raw = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    selected = []
    for name in sorted(set(raw.decode("utf-8").split("\0")) - {"", REPORT}):
        relative = Path(name)
        if relative.parts[0] == "docs" and name not in PUBLIC_DOCS:
            continue
        if name.startswith("evals/results/") or (
            name.startswith("evals/reviews/") and name not in PUBLIC_REVIEW_FIXTURES
        ):
            continue
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
        check_content(name, data)
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
    # Reviewed source metadata (upstream revision / SHA-256), pinned by full line hash.
    allowed = {
        (
            "src/citeweave/provider_accounting.py",
            "generic-api-key",
            "06567a2dd726f6e961a2582f616dc0d5946448f337b8180809cd8bf9b89aabd8",
        ),
        (
            "evals/m3-revisit-selection.json",
            "generic-api-key",
            "5d7481065de05501208d604c8b4840d402650eeb6ccc6f8928e49d793754c49a",
        ),
        (
            "evals/m3-revisit-selection.json",
            "generic-api-key",
            "5afbcf82fb9aaf3cbde7afb41f9c5484b35593d537274d88aca4900a77997774",
        ),
    }
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
        scope="allowlisted source directory, default detection rules; Git history is not included in the candidate",
        actual_local_secret_scan="passed",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-only", action="store_true", help="local candidate only; no publication")
    parser.add_argument(
        "--allow-dirty", action="store_true", help="diagnostic candidate, never release evidence"
    )
    parser.add_argument("--scanner", type=Path, default=ROOT / ".runtime/tools/gitleaks.exe")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    from benchmarks.manifest import source_identity

    identity = source_identity()
    if identity["dirty"] and not args.allow_dirty:
        raise ValueError("candidate_requires_clean_tree")
    directory, source, hashes = stage()
    result = scan(directory, source, args.scanner.resolve())
    report = dict(
        at=datetime.now(timezone.utc).isoformat(),
        source=identity,
        candidate_files=len(hashes),
        sha256=hashes,
        secret_scan=result,
        path_scan="PASS",
        documentation_allowlist=sorted(PUBLIC_DOCS),
        lockfiles={name: digest for name, digest in hashes.items() if name.endswith((".lock", "lock.yaml"))},
        publication="local candidate; no archive, Git history, tag or remote publication",
        excluded="private audits, historical reports/images, runtime, credentials, raw third-party PDFs, private evaluation exports and dependency binaries",
        status="DIAGNOSTIC" if identity["dirty"] else "LOCAL_CANDIDATE",
    )
    (directory / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            dict(
                status=report["status"],
                directory=str(directory),
                files=len(hashes),
                secret_scan="PASS",
                path_scan="PASS",
            )
        )
    )


if __name__ == "__main__":
    main()
