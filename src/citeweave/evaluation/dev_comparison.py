"""Accepted descriptive sequence and conservative decisions, never automatic winner."""

import hashlib

from citeweave.evaluation.dev_arms import ARM_IDS
from citeweave.evaluation.dev_dataset import DATASET_HASH
from citeweave.evaluation.dev_metrics import QUALITY

SEED = 20260929
OBSERVATIONS = ("DEV_FIRST_6", "DEV_ALL_12", "HARD_ALL_7")


def schedule(views):
    controls = [dict(stage="V0_L1", view=v.id, arm=ARM_IDS[0], repeat=1) for v in views if not v.prefix]
    diagnostics = [dict(stage="R_LOCAL", view=v.id, arm=ARM_IDS[1], repeat=1) for v in views]
    paid = []
    for v in views:
        arms = ARM_IDS[2:] if int(v.family[1:]) % 2 else tuple(reversed(ARM_IDS[2:]))
        paid.extend(dict(stage="DEV_NOT_AUTHORIZED", view=v.id, arm=a, repeat=1) for a in arms)
    blind = sorted(
        paid,
        key=lambda row: hashlib.sha256(
            f"{SEED}|DEV|{row['view'].split('.')[0]}|{row['view']}|{row['arm']}|1".encode()
        ).hexdigest(),
    )
    return dict(
        sequence=["V0_L1", "R_LOCAL", "A/AB0_PAIRED", "HARD", "REG+V0"],
        controls=controls,
        diagnostics=diagnostics,
        paid=paid,
        blind_order=blind,
        seed=SEED,
        repeat=1,
        observation_points=OBSERVATIONS,
    )


def compare_pairs(planned, baseline, candidate):
    pairs = []
    for view in planned:
        left, right = baseline.get(view, {}), candidate.get(view, {})
        row = {}
        for dimension in QUALITY:
            a, b = left.get(dimension), right.get(dimension)
            row[dimension] = (
                "unavailable"
                if not isinstance(a, (float, int)) or not isinstance(b, (float, int))
                else "win"
                if b > a
                else "loss"
                if b < a
                else "tie"
            )
        pairs.append(dict(view_id=view, changes=row))
    missing = any("unavailable" in p["changes"].values() for p in pairs)
    new_failures = [
        v
        for v in planned
        if set(candidate.get(v, {}).get("material_critical_failures", []))
        - set(baseline.get(v, {}).get("material_critical_failures", []))
    ]
    completion_losses = [p["view_id"] for p in pairs if p["changes"]["behavior_completion"] == "loss"]
    return dict(
        pairs=pairs,
        new_material_critical_failure_ids=new_failures,
        completion_loss_ids=completion_losses,
        noninferiority="FAIL" if new_failures or completion_losses else "INCONCLUSIVE" if missing else "PASS",
        status="NOT_RUN"
        if not baseline and not candidate
        else "INCONCLUSIVE"
        if missing
        else "DESCRIPTIVE_ONLY",
        winner=None,
        margin_new_material_failures=0,
    )


def pareto(quality_left, quality_right, cost_left, cost_right, *, fully_reviewed=False):
    if (
        not fully_reviewed
        or not quality_left
        or set(quality_left) != set(quality_right)
        or set(cost_left) != set(cost_right)
    ):
        return "INCONCLUSIVE"
    pairs = [(quality_right[k], quality_left[k]) for k in quality_left] + [
        (cost_left[k], cost_right[k]) for k in cost_left if k != "latency"
    ]
    if any(a is None or b is None for a, b in pairs):
        return "INCONCLUSIVE"
    if all(a >= b for a, b in pairs) and any(a > b for a, b in pairs):
        return "RIGHT_DOMINATES_FINITE_SET"
    if all(a <= b for a, b in pairs) and any(a < b for a, b in pairs):
        return "LEFT_DOMINATES_FINITE_SET"
    return "MATERIAL_SIMILAR" if all(a == b for a, b in pairs) else "INCONCLUSIVE"


def futility(
    observation,
    *,
    irreversible_new_material_failures,
    remaining,
    completion_best_case_can_match,
    similar_cheaper_path,
    reviewed,
):
    if observation not in OBSERVATIONS or remaining < 0:
        raise ValueError("unregistered_observation")
    if not reviewed or similar_cheaper_path is None or completion_best_case_can_match is None:
        return "INCONCLUSIVE"
    # A confirmed new material/critical error cannot be erased by even perfect
    # remaining outputs under the accepted zero-new-failure margin.
    if (
        irreversible_new_material_failures > 0 or not completion_best_case_can_match
    ) and not similar_cheaper_path:
        return "STOP_FUTILITY"
    return "CONTINUE_WITHIN_AUTHORIZATION"


def comparison_report(data, receipts, reviews, *, condition_identity):
    """Common conditions and current hashes must match before any paired claim."""
    from citeweave.evaluation.dev_arms import arm

    if not condition_identity:
        raise ValueError("comparison_condition_identity_required")
    views = {v.id: v for v in data.views}
    runtimes = []
    for receipt in receipts:
        view = views.get(receipt["view_id"])
        config = arm(receipt["arm_id"])
        if (
            not view
            or receipt["view_hash"] != view.sha256
            or receipt["dataset_hash"] != DATASET_HASH
            or receipt["arm_config_hash"] != config.config_hash
            or receipt["split"] != "Development"
            or receipt["repeat"] != 1
        ):
            raise ValueError("comparison_receipt_identity_conflict")
        runtimes.append(receipt["runtime_sources"])
    if runtimes and any(r != runtimes[0] for r in runtimes):
        raise ValueError("comparison_runtime_identity_conflict")
    if receipts and any(
        r["control_conditions"] != receipts[0]["control_conditions"] or r["mode"] != receipts[0]["mode"]
        for r in receipts
    ):
        raise ValueError("comparison_control_conditions_conflict")
    # Deterministic fixtures are not candidate semantic evidence, even if someone
    # hands the report fake gold scores. Never pick a winner from those fixtures.
    eligible = [r for r in receipts if r["execution_kind"] != "FAKE_L1_NOT_DEV"]
    result = {}
    for left, right in zip(ARM_IDS, ARM_IDS[1:]):
        baseline = {
            v: reviews[(v, left)]
            for v in views
            if (v, left) in reviews and any(r["view_id"] == v and r["arm_id"] == left for r in eligible)
        }
        candidate = {
            v: reviews[(v, right)]
            for v in views
            if (v, right) in reviews and any(r["view_id"] == v and r["arm_id"] == right for r in eligible)
        }
        result[f"{left}->{right}"] = compare_pairs(list(views), baseline, candidate)
    return dict(
        dataset_hash=DATASET_HASH,
        condition_identity=condition_identity,
        comparisons=result,
        excluded_fake_l1=len(receipts) - len(eligible),
        winner=None,
    )
