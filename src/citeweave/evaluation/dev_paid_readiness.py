"""Offline paid-DEV proposal measurements. No live policy, grant or provider.

Fixture message identities are preserved as specimens, never advertised as real
PG identities, future interpreter outputs or real retrieval upper bounds.
"""

from decimal import Decimal

from citeweave.costs import maximum_cost
from citeweave.evaluation.dev_approval import load_human_gold
from citeweave.evaluation.dev_arms import ARM_IDS, arm
from citeweave.evaluation.dev_dataset import DATASET_HASH, digest, verify_original_sources
from citeweave.evaluation.dev_execution import DtoBackend, execute_l1, frozen_runtime
from citeweave.evaluation.dev_fixtures import FixtureRepository
from citeweave.evaluation.dev_review import review_plan
from citeweave.llm import completion_payload

CHECKPOINT_COMMIT = "c905bb55489108aa118e669d576e037ba5c81ca1"
CHECKPOINT_TREE = "b6dadc84fd530bdc7fd2a22bb453b4058669d3b3"


def bounded_totals(calls, *, limits=None):
    """Pure proposal arithmetic; missing bounds fail, never fall back to references.

    This is not a durable reservation or execution admission implementation.
    """
    for call in calls:
        if any(type(call.get(k)) is not int or call[k] < 0 for k in ("input_tokens", "output_tokens")):
            raise ValueError("readiness_unbounded_tokens")
    inputs = sum(c["input_tokens"] for c in calls)
    outputs = sum(c["output_tokens"] for c in calls)
    result = dict(
        calls=len(calls),
        input_tokens=inputs,
        output_tokens=outputs,
        total_tokens=inputs + outputs,
        yuan=maximum_cost(inputs, outputs),
    )
    if limits is not None:
        for field in ("calls", "input_tokens", "output_tokens", "yuan"):
            limit = limits.get(field)
            valid = (
                isinstance(limit, Decimal) and limit.is_finite() and limit >= 0
                if field == "yuan"
                else type(limit) is int and limit >= 0
            )
            if not valid:
                raise ValueError("readiness_budget_unbounded")
            if result[field] > limit:
                raise ValueError("readiness_budget_exceeded:" + field)
    return result


def build_readiness(root, accounting):
    data, approval, approval_sha = load_human_gold(root)
    source_count = verify_original_sources(root, data)
    repository = FixtureRepository(data)
    attempts, specimens = [], []
    for view in data.views:
        for arm_id in ARM_IDS[2:]:
            receipt = execute_l1(root, view.id, arm_id, retriever=repository)
            purposes = [c["purpose"] for c in receipt["calls"]]
            guard = receipt["status"] == "GUARD_FAILURE" and not purposes
            conditional_interpretation = int("interpretation" in purposes)
            conditional_generation = int(not guard)
            attempts.append(
                dict(
                    view=view.id,
                    view_sha256=view.sha256,
                    arm=arm_id,
                    arm_sha256=arm(arm_id).config_hash,
                    hard=view.hard,
                    prefix_turns=len(view.prefix),
                    expected_purposes=purposes,
                    expected_status=receipt["status"],
                    guard=receipt.get("error_code"),
                    expected_clarification=view.outcome == "clarification",
                    state_only_evaluation=view.state_only_intent and arm_id == "cp-a-v1",
                    protocol_interpretation=1,
                    protocol_generation=1,
                    conditional_interpretation=conditional_interpretation,
                    conditional_generation=conditional_generation,
                    conditional_calls=conditional_interpretation + conditional_generation,
                    expected_calls=len(purposes),
                )
            )
            for call in receipt["calls"]:
                output = call.get("reference_output", view.reference_answer)
                if "CURRENT_SOURCE_LABEL" in output:
                    scope = DtoBackend(data, view, arm(arm_id)).scope(view.scope)
                    material = repository.retrieve(repository.workspace, scope, view.question)
                    version = next(s.version_id for s in data.sources if s.id == view.evidence_support[0][0])
                    label = next(c.label for c in material.citations if c.document_version_id == version)
                    output = output.replace("CURRENT_SOURCE_LABEL", label)
                count = len(accounting.tokenizer.encode(output, add_special_tokens=False).ids)
                body = completion_payload(call["messages"], "deepseek-flash", count)
                specimens.append(
                    dict(
                        view=view.id,
                        arm=arm_id,
                        purpose=call["purpose"],
                        body=body,
                        measurement=accounting.measure(body),
                        reference_output=output,
                        reference_sha256=digest(output),
                        reference_output_tokens=count,
                        output_reserve=None,
                        live_input_upper_bound=None,
                        dynamic_interpretation=call["purpose"] == "generation"
                        and "interpretation" in purposes,
                        kind="EXACT_FIXTURE_REFERENCE_SPECIMEN_NOT_LIVE_REQUEST_OR_RESERVE",
                    )
                )
    per_arm = {}
    for arm_id in ARM_IDS[2:]:
        rows = [r for r in attempts if r["arm"] == arm_id]
        per_arm[arm_id] = dict(
            logical_attempts=len(rows),
            protocol=sum(r["protocol_interpretation"] + r["protocol_generation"] for r in rows),
            conditional=sum(r["conditional_calls"] for r in rows),
            expected=sum(r["expected_calls"] for r in rows),
            interpretation=sum(r["conditional_interpretation"] for r in rows),
            conditional_generation=sum(r["conditional_generation"] for r in rows),
            expected_generation=sum("generation" in r["expected_purposes"] for r in rows),
        )
    protocol_calls = sum(p["protocol"] for p in per_arm.values())
    if protocol_calls > 48:
        raise ValueError("readiness_protocol_call_ceiling_exceeded")
    return dict(
        status="V02A_DEV_PAID_READINESS_BLOCKED",
        campaign_id="citeweave-v02a-dev-v3-paid-01-PROPOSAL",
        dataset_id=data.dataset_id,
        dataset_sha256=DATASET_HASH,
        approval_id=approval["approval_id"],
        approval_sha256=approval_sha,
        checkpoint_commit=CHECKPOINT_COMMIT,
        checkpoint_tree=CHECKPOINT_TREE,
        approved_view_hashes=approval["approved_views"],
        protocol_sha256=data.protocol_sha256,
        original_pdf_count_verified=source_count,
        sources=[s.model_dump(mode="json") for s in data.sources],
        runtime_sources=frozen_runtime(root),
        execution={s: "NOT_RUN" for s in ("DEV", "HARD", "REG")},
        actual_external_calls=0,
        actual_paid_yuan="0",
        paid_views={"V0": [], "R": [], "A": [v.id for v in data.views], "AB0": [v.id for v in data.views]},
        logical_attempts=len(attempts),
        calls=dict(
            protocol=protocol_calls,
            conditional=sum(p["conditional"] for p in per_arm.values()),
            expected=sum(p["expected"] for p in per_arm.values()),
            judge=0,
            retry=0,
            refetch=0,
        ),
        per_arm=per_arm,
        attempts=attempts,
        specimens=specimens,
        specimen_fixed_input_sum=sum(s["measurement"]["input_tokens"] for s in specimens),
        specimen_interpretation_input_sum=sum(
            s["measurement"]["input_tokens"] for s in specimens if s["purpose"] == "interpretation"
        ),
        specimen_no_interpretation_generation_input_sum=sum(
            s["measurement"]["input_tokens"]
            for s in specimens
            if s["purpose"] == "generation" and not s["dynamic_interpretation"]
        ),
        input_token_ceiling=None,
        output_token_ceiling=None,
        total_token_ceiling=None,
        expected_path_yuan_ceiling=None,
        protocol_yuan_ceiling=None,
        proposed_authorization_yuan=None,
        review_plan=review_plan(data, approval=approval),
        blockers=[
            "OUTPUT_RESERVES_AND_JUSTIFIED_MARGIN_NOT_ACCEPTED",
            "REAL_REQUEST_IDENTITIES_AND_DYNAMIC_INPUT_BOUNDS_NOT_CLOSED",
            "ACCOUNT_CNY_APPLICABILITY_AND_ALIAS_LIMITATION_OWNER_GATE",
            "REAL_DEV_READY_PUBLISHED_CORPUS_INDEX_NOT_BOUND",
            "PAID_STATE_ONLY_A_DURABLE_SETTLEMENT_NOT_IMPLEMENTED",
            "CAMPAIGN_ATOMIC_RESERVATIONS_DEADLINES_CANCELLATION_NOT_INSTALLED",
            "CUMULATIVE_REVIEW_CAPACITY_UNRECONCILED",
            "EXPLICIT_PAID_AUTHORIZATION_ABSENT",
        ],
    )
