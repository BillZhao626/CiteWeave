"""Single format intervention and frozen envelope, no transport or semantic tuning."""

import copy
import hashlib
from decimal import Decimal

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationInput
from citeweave.costs import maximum_cost
from citeweave.evaluation.dev_dataset import digest
from citeweave.evaluation.dev_provenance import (
    ALLOWLIST,
    REVISION,
    canonical_request,
    refreeze,
    uuid_input_bound,
)
from citeweave.interpretation_format import REVISION as FORMAT_REVISION
from citeweave.interpretation_format import FormatDraft, format_messages
from citeweave.llm import completion_payload


def intervention_identity(root):
    return dict(
        revision=FORMAT_REVISION,
        schema_sha256=digest(FormatDraft.model_json_schema()),
        files={
            p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in (
                "prompts/conversation-interpretation-format-v2.txt",
                "src/citeweave/interpretation_format.py",
            )
        },
        semantics="original validators/decision policies; only tagged origins, quote occurrence and exact rewrite serialization",
    )


def refreeze_p0(original, accounting, root):
    value = copy.deepcopy(refreeze(original, accounting, root))
    prior_inputs = value["input_tokens"]
    for probe in value["probes"]:
        if "interpretation_request" not in probe:
            continue
        context = InterpretationInput.model_validate(probe["context"])
        body = completion_payload(
            format_messages(context), "deepseek-flash", value["reserves"]["interpretation"]
        )
        bound = uuid_input_bound(body, "interpretation", accounting)
        slot = next(
            s
            for s in value["slots"]
            if s["case"] == probe["view"] + ":" + probe["arm"] and s["purpose"] == "interpretation"
        )
        slot["input_tokens"] = bound["input_tokens"]
        probe["interpretation_request"] = body
        probe["interpretation_measurement"] = accounting.measure(body)
        probe["interpretation_provenance_bound"] = bound
        requests = dict(
            interpretation=digest(canonical_request(body, "interpretation")[0]),
            generation=digest(canonical_request(probe["generation_shell"], "generation")[0]),
        )
        probe["semantic_contract_sha256"] = digest(
            dict(revision=REVISION, allowlist=ALLOWLIST, wire_order=probe["wire_order"], requests=requests)
        )
    inputs = sum(s["input_tokens"] for s in value["slots"])
    outputs = sum(s["output_tokens"] for s in value["slots"])
    amount = maximum_cost(inputs, outputs)
    if len(value["slots"]) != 38 or outputs != 777079 or amount > Decimal("18.70"):
        raise CoreConflict("dev_p0_human_ceiling_exceeded")
    value.update(
        input_tokens=inputs,
        output_tokens=outputs,
        total_tokens=inputs + outputs,
        derived_worst_case_yuan=str(amount),
        interpretation_format_intervention=intervention_identity(root),
        format_input_delta=inputs - prior_inputs,
        authority="HUMAN_P0_FULL_RERUN_2026_10_02",
    )
    value["semantic_contract_sha256"] = digest(
        dict(
            revision=REVISION,
            allowlist=ALLOWLIST,
            slots=value["slots"],
            intervention=value["interpretation_format_intervention"],
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
