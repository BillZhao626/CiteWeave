"""Re-freeze both narrow prompt interventions with the existing finite proof."""

import hashlib
from decimal import Decimal

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationInput
from citeweave.costs import maximum_cost
from citeweave.evaluation.dev_dataset import digest
from citeweave.evaluation.dev_dispatch import generation_input_bound
from citeweave.evaluation.dev_provenance import (
    ALLOWLIST,
    REVISION,
    canonical_request,
    generation_shell,
    refreeze,
    uuid_input_bound,
)
from citeweave.llm import completion_payload
from citeweave.runtime_rc_closure import REVISION as FORMAT_REVISION
from citeweave.runtime_rc_closure import FormatDraft, format_messages

GENERATION_PROMPT = "prompts/answer-telecom-rc-v2.txt"
GENERATION_REVISION = "answer-telecom-rc-v2"


def intervention_identity(root):
    return dict(
        revision=FORMAT_REVISION,
        schema_sha256=digest(FormatDraft.model_json_schema()),
        files={
            p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in (
                "prompts/conversation-interpretation-rc-v5.txt",
                "src/citeweave/runtime_rc_closure.py",
                "src/citeweave/runtime_reconciliation.py",
                GENERATION_PROMPT,
            )
        },
        generation_prompt=GENERATION_PROMPT,
        generation_revision=GENERATION_REVISION,
        semantics="explicit inherited subject and same-task selection; supported origin catalog; proposition polarity instructions; unchanged strict v4 validation",
    )


def refreeze_closure(original, accounting, root):
    value = refreeze(original, accounting, root)
    prior_inputs = value["input_tokens"]
    prompt = (root / GENERATION_PROMPT).read_text(encoding="utf-8")
    caps = set()
    for probe in value["probes"]:
        if not probe["dispatch_slots"]:
            continue
        context = InterpretationInput.model_validate(probe["context"])
        requests = {}
        for purpose in probe["dispatch_slots"]:
            slot = next(
                s
                for s in value["slots"]
                if s["case"] == probe["view"] + ":" + probe["arm"] and s["purpose"] == purpose
            )
            if purpose == "interpretation":
                body = completion_payload(format_messages(context), "deepseek-flash", slot["output_tokens"])
                bound = uuid_input_bound(body, purpose, accounting)
                probe["interpretation_request"] = body
                probe["interpretation_measurement"] = accounting.measure(body)
                probe["interpretation_provenance_bound"] = bound
            elif "generation_request" in probe:
                body = probe["generation_request"]
                body["messages"][0]["content"] = prompt
                bound = uuid_input_bound(body, purpose, accounting)
                probe["generation_measurement"] = accounting.measure(body)
                probe["generation_provenance_bound"] = bound
            else:
                bound = generation_input_bound(
                    context, prompt, value["reserves"]["interpretation"], value["tokenizer_certificate"]
                )
                probe["generation_bound"] = bound
                body = generation_shell(context, prompt, slot["output_tokens"])
                probe["generation_shell"] = body
                probe["generation_provenance_bound"] = dict(
                    input_tokens=bound["input_tokens"],
                    provenance_overhead_tokens=0,
                    proof=bound["proof"],
                )
                caps.add(bound["interpretation_insertion_bytes"])
            slot["input_tokens"] = bound["input_tokens"]
            requests[purpose] = digest(canonical_request(body, purpose)[0])
        probe["semantic_contract_sha256"] = digest(
            dict(revision=REVISION, allowlist=ALLOWLIST, wire_order=probe["wire_order"], requests=requests)
        )
    if len(caps) != 1:
        raise CoreConflict("dev_closure_fact_envelope_missing")
    inputs = sum(s["input_tokens"] for s in value["slots"])
    outputs = sum(s["output_tokens"] for s in value["slots"])
    amount = maximum_cost(inputs, outputs)
    if len(value["slots"]) != 38 or outputs != 777079 or amount > Decimal("18.70"):
        raise CoreConflict("dev_closure_human_ceiling_exceeded")
    value.update(
        normalized_fact_bytes_cap=caps.pop(),
        input_tokens=inputs,
        output_tokens=outputs,
        total_tokens=inputs + outputs,
        derived_worst_case_yuan=str(amount),
        interpretation_format_intervention=intervention_identity(root),
        generation_prompt=dict(path=GENERATION_PROMPT, revision=GENERATION_REVISION),
        format_input_delta=inputs - prior_inputs,
        authority="HUMAN_RC_NARROW_CLOSURE_2026_10_02",
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
    # Preserve the existing path bound as a descriptive bound, never a grant.
    expected = [
        s for s in value["slots"] if not (s["case"].startswith("D4.V1:") and s["purpose"] == "generation")
    ]
    value["expected_path_yuan_upper_bound"] = str(
        maximum_cost(sum(s["input_tokens"] for s in expected), sum(s["output_tokens"] for s in expected))
    )
    return value
