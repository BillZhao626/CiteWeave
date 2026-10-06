"""Strict interpretation boundary and opt-in, local-only failure diagnostics.

Raw provider text is never application state. Diagnostic failures must not change
the original validation failure or the runtime's durable reliability handling.
"""

import hashlib
import json
import logging
import os
from uuid import UUID

from pydantic import ValidationError

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import InterpretationDraft, InterpretationInput
from citeweave.interpretation_format import FormatDraft, decode_format
from citeweave.settings import ROOT


def production_interpretation_messages(context: InterpretationInput) -> list[dict]:
    # Preserve the current production history selection. In particular, do not
    # use format_messages(), which adds an evaluation-only State intent policy.
    from citeweave.conversation_runtime import interpretation_messages

    messages = interpretation_messages(context)
    messages[0]["content"] = (ROOT / "prompts/conversation-interpretation-product-v2.txt").read_text(
        encoding="utf-8"
    )
    payload = json.loads(messages[1]["content"])
    payload["output_schema"] = FormatDraft.model_json_schema()
    messages[1]["content"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return messages


def parse_interpretation_response(
    raw: str, *, context: InterpretationInput, run_id: UUID
) -> InterpretationDraft:
    try:
        # Deterministic representation conversion only. interpret() still checks
        # every exact origin, semantic dependency, scope and rewrite invariant.
        return decode_format(raw, context)
    except (ValidationError, CoreConflict) as exc:
        record_interpretation_failure(raw, run_id=run_id, exc=exc)
        raise


def record_interpretation_failure(raw: str, *, run_id: UUID, exc: Exception) -> None:
    if os.environ.get("CW_INTERPRETATION_DIAGNOSTICS") == "1":
        try:
            # A fixed Git-ignored directory; no caller-controlled path or
            # request headers/configuration are written into diagnostics.
            folder = ROOT / ".runtime" / "interpretation-diagnostics" / str(UUID(str(run_id)))
            folder.mkdir(parents=True, exist_ok=True)
            content = raw.encode("utf-8")
            with (folder / "provider-output.txt").open("xb") as stream:
                stream.write(content)
            validation = exc if isinstance(exc, ValidationError) else exc.__cause__
            report = {
                "kind": "raw_provider_output_not_application_state",
                "run_id": str(run_id),
                "sha256": hashlib.sha256(content).hexdigest(),
                "errors": validation.errors(include_input=False, include_context=False, include_url=False)
                if isinstance(validation, ValidationError)
                else [{"code": str(exc)}],
                "schema": FormatDraft.model_json_schema(),
            }
            with (folder / "validation.json").open("x", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
        except Exception:
            logging.warning("interpretation_diagnostic_write_failed run=%s", run_id)
