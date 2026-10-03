"""Offline measurements of FIXTURE/reference bytes, never execution authority."""

import hashlib
from decimal import Decimal
from importlib.metadata import version

from citeweave.costs import RATE_CARD
from citeweave.evaluation.dev_arms import ARM_IDS
from citeweave.evaluation.dev_dataset import digest
from citeweave.llm import completion_payload
from citeweave.provider_accounting import ACCOUNTING_REVISION, TOKENIZER_SHA256

OFFICIAL_IDENTITY = dict(
    accessed_utc="2026-10-01T01:29:46.546664+00:00",
    url="https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
    sha256="5a7b1832592387340f2fc456399b34b89b05f3fa167c2e35909e2fa4afe021e3",
    model_version="DeepSeek-V4.1-Flash",
    alias="deepseek-flash",
    context=1000000,
    output_maximum=384000,
    peak_noncache_input_cny_per_million="2",
    peak_output_cny_per_million="8",
    note="Published alias/version, not immutable served-weight identity. Owner acceptance pending. No new rate-card revision or billing authorization.",
)


def offline_measurements(data, receipts, accounting, *, official_snapshot=None):
    verified = False
    if official_snapshot is not None:
        verified = hashlib.sha256(official_snapshot.read_bytes()).hexdigest() == OFFICIAL_IDENTITY["sha256"]
        if not verified:
            raise ValueError("dev_official_identity_mismatch")
    measurements = []
    for receipt in receipts:
        view = next(v for v in data.views if v.id == receipt["view_id"])
        for call in receipt["calls"]:
            # Interpretation JSON is gold-derived fake output, not provider usage.
            output = call.get("reference_output", view.reference_answer)
            count = len(accounting.tokenizer.encode(output, add_special_tokens=False).ids)
            # Reference length solely makes an exact, valid accounting specimen.
            # This is not an output cap/reserve or a dispatchable request grant.
            body = completion_payload(call["messages"], "deepseek-flash", count)
            measured = accounting.measure(body)
            measurements.append(
                dict(
                    view_id=view.id,
                    arm_id=receipt["arm_id"],
                    purpose=call["purpose"],
                    measurement=measured,
                    body=body,
                    reference_output=output,
                    reference_hash=digest(output),
                    kind="FIXTURE_REFERENCE_REQUEST_NOT_AUTHORIZED_POLICY",
                    max_tokens_meaning="reference specimen only, NOT reserve or generation grant",
                )
            )
    paid = [m for m in measurements if m["arm_id"] in ARM_IDS[2:]]
    paid_receipts = [r for r in receipts if r["arm_id"] in ARM_IDS[2:]]
    complete_matrix = {(r["view_id"], r["arm_id"]) for r in paid_receipts} == {
        (v.id, a) for v in data.views for a in ARM_IDS[2:]
    }
    interp = sum(m["purpose"] == "interpretation" for m in paid)
    generation = sum(m["purpose"] == "generation" for m in paid)
    guarded = sum(r["status"] == "GUARD_FAILURE" and not r["calls"] for r in paid_receipts)
    gen_max = len(paid_receipts) - guarded if complete_matrix else None
    conditional = interp + gen_max if complete_matrix else None
    ranges = {}
    for purpose in ("interpretation", "generation"):
        values = [m["measurement"]["input_tokens"] for m in paid if m["purpose"] == purpose]
        outputs = [m["measurement"]["output_tokens"] for m in paid if m["purpose"] == purpose]
        ranges[purpose] = dict(
            fixed_fixture_input_min=min(values) if values else None,
            fixed_fixture_input_max=max(values) if values else None,
            fixed_fixture_input_sum=sum(values),
            proposed_reference_output_max=max(outputs) if outputs else None,
            fixture_specimens=len(values),
            live_input_cap=None,
            live_output_reserve=None,
        )
    return dict(
        accounting_revision=ACCOUNTING_REVISION,
        tokenizer_sha256=TOKENIZER_SHA256,
        tokenizers_library=version("tokenizers"),
        provider="deepseek",
        model="deepseek-flash",
        model_revision="ALIAS_NOT_PINNED_OWNER_ACCEPTANCE_PENDING",
        rate_revision=RATE_CARD,
        current_rate_verified=verified,
        official_identity=OFFICIAL_IDENTITY,
        provider_limit_conditional_token_cost_ceiling=dict(
            per_call_cny=str((Decimal(1000000) * 2 + Decimal(384000) * 8) / 1000000),
            protocol_48_calls_cny="243.456",
            fixed_manifest_calls_cny=str(Decimal(conditional) * Decimal("5.072"))
            if conditional is not None
            else None,
            status="CONDITIONAL_TECHNICAL_CEILING_NOT_EXECUTION_ENVELOPE" if verified else "NOT_VERIFIED",
            derivation="Separate official input/context and output maxima, conservatively summed; peak noncache CNY rates. No arbitrary margin. Not a selected conversation output reserve; does not establish affordable or authorized DEV.",
        ),
        per_call=measurements,
        paid_fixture_ranges=ranges,
        actual_external_calls=0,
        actual_provider_tokens=0,
        actual_paid_cost_yuan=0,
        worst_case_dev_yuan=None,
        token_envelope_status="DEFERRED_OWNER_REFERENCE_AND_RESERVE",
        calls=dict(
            protocol_maximum=48,
            interpretation_maximum=24,
            generation_maximum=24,
            fixed_manifest_conditional_maximum=conditional,
            fixed_manifest_interpretation_maximum=interp if complete_matrix else None,
            fixed_manifest_generation_maximum=gen_max,
            expected_fixture_generation=generation,
            expected_fixture_interpretation=interp,
            judge=0,
            retry=0,
            refetch=0,
        ),
        deadlines=dict(
            campaign_attempt_absolute_seconds=45,
            existing_generation_seconds=35,
            existing_transport_seconds=25,
            new_live_combined_policy="NOT_FROZEN",
        ),
        limits=[
            "Conditional ceiling requires the complete fake A/AB0 matrix, fixed interpretation skip rules and the A correction guard. Clarification may incorrectly become generation. State-only output is an evaluation artifact, not product acceptance. Global bound remains 48; saved calls not reallocated.",
            "Inputs after real interpretation depend on the model output. Fixture input maxima are not live upper bounds.",
            "Reference outputs require owner review; reference maxima are not completeness guarantees or reserves.",
            "The published CNY rates match the existing rate identity; snapshot validation does not grant money or pin served weights. Rebind applicable billing/account/remaining balance and accept alias limitation before execution.",
            "Per-Run/Turn/Conversation/stage/campaign token and CNY reservations, finite authorization and balance remain mandatory before dispatch.",
        ],
    )
