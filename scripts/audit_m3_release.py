"""Verify current source against quality, clean-install and publication evidence."""

import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from citeweave.settings import ROOT


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((ROOT / "docs/reports" / name).read_text(encoding="utf-8"))


def main():
    checks = []
    freeze = read("m3-quality-freeze.json")
    assert all(sha(ROOT / name) == digest for name, digest in freeze["sha256"].items())
    checks.append("Selected quality source, prompts and locks match pre-Test freeze")
    reviews = read("m3-human-judge-v1.json")
    assert sha(ROOT / "evals/public-standards-v1.json") == freeze["dataset_sha256"] == reviews["dataset_hash"]
    assert all(
        sha(ROOT / "evals/reviews/m2-dev-24" / name) == digest
        for name, digest in reviews["source_files"].items()
    )
    checks.append("Frozen dataset and submitted review bytes unchanged")
    for split in ("dev", "test"):
        comparison = read("m3-selected-" + split + ".json")
        assert comparison["same_versions"] and comparison["dataset_hash"] == freeze["dataset_sha256"]
        assert (
            comparison["candidate"]["evidence"]["final"]["mean"]
            > comparison["baseline"]["evidence"]["final"]["mean"]
        )
        assert comparison["paired"]["correctness"].get("loss", 0) == 0
        physical = comparison["candidate"]["citation"]["micro_grounded"]
        assert physical["passed"] == physical["count"] > 0
        if split == "test":
            for identity in (comparison["baseline_id"], comparison["candidate_id"]):
                artifact = json.loads(
                    (ROOT / ".runtime/evaluation/runs" / identity / "artifact.json").read_text(
                        encoding="utf-8"
                    )
                )
                assert datetime.fromisoformat(artifact["evaluation"]["created_at"]) > datetime.fromisoformat(
                    freeze["at"]
                )
    checks.append(
        "Formal Test created after freeze; same versions/rubric, quality gains and physical grounding preserved"
    )
    gates = read("m3-gates.json")
    assert len(gates["results"]) == 9 and all(g["passed"] for g in gates["results"])
    suite = ET.parse(ROOT / "docs/reports/m3-tests.xml").find("testsuite")
    assert suite is not None and all(int(suite.get(k, "0")) == 0 for k in ("failures", "errors", "skipped"))
    checks.append("Current nine gates and backend tests pass without skips")
    clean = read("m3-clean-install.json")
    assert clean["status"] == "PASS" and all(g["passed"] for g in clean["gates"]["results"])
    assert clean["probe"]["tables_before_migration"] == 0 and clean["probe"]["migration_head"] == "0004"
    assert clean["probe"]["physical_citations"] > 0 and clean["probe"]["status"] == "PASS"
    clean_root = Path(clean["folder"]).resolve()
    assert clean_root.is_relative_to((ROOT / ".runtime").resolve())
    matched = []
    for prefix in ("src", "apps/web/src", "contracts", "deploy", "migrations", "prompts", "tests"):
        for path in (ROOT / prefix).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                name = path.relative_to(ROOT).as_posix()
                assert (clean_root / name).is_file() and sha(path) == sha(clean_root / name), (
                    "clean_source_drift: " + name
                )
                matched.append(name)
    for name in (
        "scripts/m1.ps1",
        "scripts/verify.py",
        "scripts/check_contracts.py",
        "scripts/clean_probe.py",
        "pyproject.toml",
        "uv.lock",
        "requirements-models.lock",
        "requirements-worker.lock",
        "apps/web/package.json",
        "apps/web/pnpm-lock.yaml",
    ):
        assert sha(ROOT / name) == sha(clean_root / name), "clean_setup_drift: " + name
        matched.append(name)
    checks.append(
        "Clean-installed application, frontend, tests, migration, setup and locks match current source"
    )
    faults, recovery = read("m3-faults.json"), read("m3-recovery.json")
    assert faults["passed"] == faults["expected"] == 3 and faults["faults_disabled_after_run"]
    assert (
        recovery["status"] == "PASS"
        and not recovery["production_database_overwritten"]
        and not recovery["old_ragflow_touched"]
    )
    checks.append("Three worker kills and isolated backup/restore passed")
    dependencies, validation = read("m3-dependencies.json"), read("m3-sbom-validation.json")
    assert not dependencies["unresolved"]
    assert all(sha(ROOT / name) == digest for name, digest in dependencies["lock_sha256"].items())
    assert validation["status"] == "PASS" and validation["sbom_sha256"] == sha(
        ROOT / "docs/reports/m3-sbom.cdx.json"
    )
    checks.append("Dependency lock hashes and validated CycloneDX SBOM match")
    browser = read("m3-browser.json")
    assert browser["status"] == "PASS"
    assert all(sha(ROOT / name) == digest for name, digest in browser["screenshots"].items())
    checks.append("Browser checks and saved screenshots recorded")
    result = dict(
        at=datetime.now(timezone.utc).isoformat(),
        status="PASS",
        checks=checks,
        clean_matched_files=sorted(matched),
        backend_tests=int(suite.get("tests")),
        boundary="Same physical Windows machine; public download/package/image caches reused. Formal Test Judge failures and semantic/latency limits remain disclosed. Source directory secret scanning and archive hashing run separately.",
    )
    (ROOT / "docs/reports/m3-release-audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("M3 release evidence audit PASS")


if __name__ == "__main__":
    main()
