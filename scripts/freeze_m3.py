"""Seal the selected Dev configuration before the single formal Test comparison."""

import hashlib
import json
from datetime import datetime, timezone

from citeweave.evaluation.dataset import load_dataset
from citeweave.profiles import DEFAULT_PROFILE, query_profile
from citeweave.settings import ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = ROOT / "docs/reports/m3-quality-freeze.json"
    files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "prompts").glob("*.txt"))
    files += [ROOT / p for p in ("uv.lock", "requirements-models.lock", "requirements-worker.lock")]
    hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in files}
    if target.exists():
        frozen = json.loads(target.read_text(encoding="utf-8"))
        assert frozen["sha256"] == hashes, "frozen_quality_code_changed"
        print("Existing quality freeze verified; do not retune from Test")
        return
    gates = json.loads((ROOT / "docs/reports/m3-gates.json").read_text(encoding="utf-8"))
    assert len(gates["results"]) == 9 and all(g["passed"] for g in gates["results"])
    assert DEFAULT_PROFILE == "m3-context"
    _, dataset_hash = load_dataset()
    journal_path = ROOT / "docs/reports/m3-experiments.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["selection_status"] = "FROZEN_AFTER_DEV_REPEAT_AND_FULL_REGRESSION"
    journal["selected_dev_verification_run"] = "b66bab34-b63b-46fe-b33e-f0f116cf65ba"
    journal["experiments"][1]["verification"] = dict(
        run_id=journal["selected_dev_verification_run"],
        result="24 valid queries/Judges, 7 correctness wins/17 ties/0 losses vs M2; final coverage .5358333333, correctness/completeness .5833333333, 50/50 physical citations. Model variation vs first C2 disclosed.",
    )
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    value = dict(
        at=datetime.now(timezone.utc).isoformat(),
        profile=DEFAULT_PROFILE,
        configuration=query_profile(DEFAULT_PROFILE),
        judge="judge-v4",
        dataset_sha256=dataset_hash,
        selected_dev_run=journal["selected_dev_verification_run"],
        baseline_dev_run="953c5e62-71ae-4393-8e23-89992cb76672",
        original_m2_run="a32e838b-b5c2-4a6c-b8e7-7aabf2e8f944",
        gate_report_sha256=digest(ROOT / "docs/reports/m3-gates.json"),
        gate_report=gates,
        sha256=hashes,
        formal_test_policy="One M2 source-answer replay with judge-v4, one selected C2 Test run; no subsequent quality tuning. Tests/docs/release-only changes may follow and must be revalidated.",
    )
    target.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print("M3 quality candidate frozen before formal Test")


if __name__ == "__main__":
    main()
