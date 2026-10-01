"""Prepare original data review and offline specimen accounting. Never run DEV."""

from pathlib import Path

from citeweave.evaluation.dev_accounting import offline_measurements
from citeweave.evaluation.dev_approval import APPROVAL_SHA256, load_human_gold
from citeweave.evaluation.dev_arms import ARM_IDS
from citeweave.evaluation.dev_comparison import comparison_report, schedule
from citeweave.evaluation.dev_dataset import canonical, load_dev, verify_original_sources
from citeweave.evaluation.dev_execution import execute_l1, frozen_runtime
from citeweave.evaluation.dev_fixtures import FixtureRepository
from citeweave.evaluation.dev_metrics import layered_metrics
from citeweave.evaluation.dev_review import review_plan, review_surface
from citeweave.provider_accounting import DeepSeekAccounting

ROOT = Path(__file__).resolve().parents[1]


def main():
    data, approval, _ = load_human_gold(ROOT)
    _, sha = load_dev(ROOT)
    verify_original_sources(ROOT, data)
    repo = FixtureRepository(data)
    # This is bounded DTO seam verification, not DEV, paid admission or semantic scoring.
    receipts = [execute_l1(ROOT, v.id, a, retriever=repo) for v in data.views for a in ARM_IDS[1:]]
    receipts.append(execute_l1(ROOT, "D2.V1", ARM_IDS[0], retriever=repo))
    for receipt in receipts:
        view = next(v for v in data.views if v.id == receipt["view_id"])
        for call in receipt["calls"]:
            if call["purpose"] == "generation" and "CURRENT_SOURCE_LABEL" in view.reference_answer:
                material = repo.retrieve(repo.workspace, backend_scope(data, view), view.question)
                version = next(s.version_id for s in data.sources if s.id == view.evidence_support[0][0])
                label = next(c.label for c in material.citations if c.document_version_id == version)
                call["reference_output"] = view.reference_answer.replace("CURRENT_SOURCE_LABEL", label)
    accounting = DeepSeekAccounting(
        ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    )
    snapshot = ROOT / ".runtime/evaluation/v02-dev-readiness/official-docs/pricing-cny.html"
    measured = offline_measurements(
        data, receipts, accounting, official_snapshot=snapshot if snapshot.exists() else None
    )
    output = ROOT / ".runtime/evaluation/v02-dev-readiness"
    output.mkdir(parents=True, exist_ok=True)
    report = dict(
        dataset_hash=sha,
        runtime_sources=frozen_runtime(ROOT),
        execution="DEV_NOT_RUN",
        owner_review="APPROVED_FROZEN",
        approval_sha256=APPROVAL_SHA256,
        receipts=receipts,
        review_plan=review_plan(data, approval=approval),
        schedule=schedule(data.views),
        accounting=measured,
        metrics=layered_metrics(data, [(v.id, a) for v in data.views for a in ARM_IDS[2:]], []),
        comparisons=comparison_report(
            data, receipts, {}, condition_identity="OFFLINE_FIXED_FIXTURES_PROVIDER_POLICY_PENDING"
        ),
    )
    (output / "provider-free-report.json").write_bytes(canonical(report))
    surface = review_surface(data, approval=approval)
    surface += "\n## Deterministic L1 guard surface (not candidate quality)\n\n| View | R | A | AB0 |\n| --- | --- | --- | --- |\n"
    for view in data.views:
        cells = []
        for a in ARM_IDS[1:]:
            r = next(r for r in receipts if r["view_id"] == view.id and r["arm_id"] == a)
            cells.append(
                r["status"]
                + " / "
                + r.get(
                    "error_code",
                    r["acceptance"]["result"]["kind"]
                    if r.get("acceptance")
                    else r.get("evaluation_output", {}).get("kind", "none"),
                )
                + (" (STATE INTENT; evaluation only)" if r.get("evaluation_output") else "")
            )
        surface += "| " + view.id + " | " + " | ".join(cells) + " |\n"
    surface += "\n## Factor observability (structural L1, not provider quality)\n\n- V0 → R: D1.V1 recent reference, D4.V1 ambiguity/clarification, D5.V1 scoped inheritance expose history intent absent from the single-turn serializer; V0 output quality is NOT_RUN. D2 and D6 remain single-turn controls.\n- R → A: D1.V2 and D3.V1 change from unresolved/guard failure to State intent plus current-Evidence answer. A has no T1 raw read, old-source coverage or B recovery credit.\n- A → AB0: D1.V2/D3.V1 gain old T1 raw and B coverage (answer success alone need not change). D3.V2 gains complete T1/T4 provenance and an answer instead of incomplete_group. Correction correctness remains a separate Human annotation.\n- D4.V2: T2 remains branch provenance; required candidate/final raw coverage is N/A.\n"
    surface += "\n## Exact interpretation reference snapshots (same LABEL units)\n\nThese gold-derived fixture JSON outputs require Owner review. They do not establish output completeness or provider quality.\n"
    for specimen in measured["per_call"]:
        if specimen["purpose"] == "interpretation" and specimen["arm_id"] in ARM_IDS[2:]:
            surface += f"\n### {specimen['view_id']} / {specimen['arm_id']}\n\nReference hash `{specimen['reference_hash']}`; output {specimen['measurement']['output_tokens']} offline tokens.\n\n```json\n{specimen['reference_output']}\n```\n"
    (ROOT / "docs/V02_DEV_DATA_REVIEW.md").write_text(surface, encoding="utf-8", newline="\n")
    (output / "review-plan.json").write_bytes(canonical(review_plan(data, approval=approval)))
    print("Verified frozen Human Gold; 37 DTO fixtures only; external calls 0; DEV NOT_RUN.")
    print(measured["paid_fixture_ranges"])


def backend_scope(data, view):
    from citeweave.evaluation.dev_arms import arm
    from citeweave.evaluation.dev_execution import DtoBackend

    return DtoBackend(data, view, arm(ARM_IDS[-1])).scope(view.scope)


if __name__ == "__main__":
    main()
