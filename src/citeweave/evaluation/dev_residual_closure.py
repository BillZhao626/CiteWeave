"""Provider-free v6 candidate contract; never a paid authorization."""

import hashlib
from decimal import Decimal

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationInput
from citeweave.costs import maximum_cost
from citeweave.evaluation.dev_dataset import digest
from citeweave.evaluation.dev_provenance import ALLOWLIST, REVISION, canonical_request, uuid_input_bound
from citeweave.evaluation.dev_rc_closure import GENERATION_PROMPT, GENERATION_REVISION, refreeze_closure
from citeweave.llm import completion_payload
from citeweave.runtime_residual_closure import REVISION as FORMAT_REVISION
from citeweave.runtime_residual_closure import format_messages, output_schema


def intervention_identity(root):
    return dict(
        revision=FORMAT_REVISION,
        schema_sha256=digest(output_schema()),
        files={
            p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in (
                "prompts/conversation-interpretation-residual-v6.txt",
                "prompts/conversation-interpretation-rc-v5.txt",
                "src/citeweave/runtime_residual_closure.py",
                "src/citeweave/runtime_rc_closure.py",
                "src/citeweave/runtime_reconciliation.py",
                "src/citeweave/evaluation/dev_state.py",
                GENERATION_PROMPT,
            )
        },
        generation_prompt=GENERATION_PROMPT,
        generation_revision=GENERATION_REVISION,
        semantics="unique validated older-task normal form; exact singleton active-State reference; unchanged generation and shared core",
    )


def refreeze_residual(original, accounting, root):
    value = refreeze_closure(original, accounting, root)
    prior_inputs = value["input_tokens"]
    for probe in value["probes"]:
        if "interpretation" not in probe["dispatch_slots"]:
            continue
        context = InterpretationInput.model_validate(probe["context"])
        slot = next(
            s
            for s in value["slots"]
            if s["case"] == probe["view"] + ":" + probe["arm"] and s["purpose"] == "interpretation"
        )
        body = completion_payload(format_messages(context), "deepseek-flash", slot["output_tokens"])
        bound = uuid_input_bound(body, "interpretation", accounting)
        probe.update(
            interpretation_request=body,
            interpretation_measurement=accounting.measure(body),
            interpretation_provenance_bound=bound,
        )
        slot["input_tokens"] = bound["input_tokens"]
        requests = {
            purpose: digest(
                canonical_request(
                    probe["interpretation_request"]
                    if purpose == "interpretation"
                    else probe.get("generation_request", probe.get("generation_shell")),
                    purpose,
                )[0]
            )
            for purpose in probe["dispatch_slots"]
        }
        probe["semantic_contract_sha256"] = digest(
            dict(revision=REVISION, allowlist=ALLOWLIST, wire_order=probe["wire_order"], requests=requests)
        )
    inputs = sum(s["input_tokens"] for s in value["slots"])
    outputs = sum(s["output_tokens"] for s in value["slots"])
    if len(value["slots"]) != 38 or outputs != 777079:
        raise CoreConflict("dev_residual_frozen_slot_drift")
    value.update(
        input_tokens=inputs,
        output_tokens=outputs,
        total_tokens=inputs + outputs,
        derived_worst_case_yuan=str(maximum_cost(inputs, outputs)),
        maximum_yuan=str(maximum_cost(inputs, outputs)),
        cumulative_hard_ceiling_cny=str(maximum_cost(inputs, outputs) + Decimal("0.016110")),
        interpretation_format_intervention=intervention_identity(root),
        format_input_delta=inputs - prior_inputs,
        authority="PROVIDER_FREE_RESIDUAL_CANDIDATE_NOT_PAID_AUTHORITY",
    )
    value["semantic_contract_sha256"] = digest(
        dict(
            revision=REVISION,
            allowlist=ALLOWLIST,
            slots=value["slots"],
            intervention=value["interpretation_format_intervention"],
            normalized_fact_bytes_cap=value["normalized_fact_bytes_cap"],
            probes=[
                (p["view"], p["arm"], p.get("semantic_contract_sha256", p.get("guard")))
                for p in value["probes"]
            ],
        )
    )
    value["stage_input_max"] = {
        purpose: max(s["input_tokens"] for s in value["slots"] if s["purpose"] == purpose)
        for purpose in ("interpretation", "generation")
    }
    expected = [
        s for s in value["slots"] if not (s["case"].startswith("D4.V1:") and s["purpose"] == "generation")
    ]
    value["expected_path_yuan_upper_bound"] = str(
        maximum_cost(sum(s["input_tokens"] for s in expected), sum(s["output_tokens"] for s in expected))
    )
    return value
