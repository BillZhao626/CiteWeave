"""Narrow model-facing contract; v4 provenance and semantic guards stay strict."""

import json
from collections import Counter

from citeweave.conversation_contract import CoreConflict
from citeweave.runtime_reconciliation import FormatDraft, decode_reconciled
from citeweave.runtime_reconciliation import decision_context as reconciled_context
from citeweave.settings import ROOT

REVISION = "interpretation-rc-closure-v5"


def decision_context(context):
    value = reconciled_context(context)
    origins = Counter()
    for entry in context.history.state_projection:
        if entry.active:
            origins[(entry.item.kind, entry.item.value, "state")] += 1
    for group in context.history.selected:
        for source in group.sources:
            signals = source.signals
            for kind, items in (
                ("topic", (signals.topic,)),
                ("task", (signals.task,)),
                ("entity", signals.entities),
                ("constraint", signals.constraints),
            ):
                for item in set(items):
                    if item:
                        origins[(kind, item, "history")] += 1
    # No new identity paths: UUIDs remain in the existing bounded source/State
    # payload. Counts expose whether omission of an origin identity is valid.
    value["origin_catalog"] = [
        dict(kind=kind, value=item, type=origin, available_origins=count)
        for (kind, item, origin), count in sorted(origins.items())
    ]
    value["same_task_pending_selection"] = bool(
        context.previous
        and any(
            entry.active
            and entry.item.kind == "ambiguity"
            and entry.introduced_by.acceptance_id == context.previous.id
            for entry in context.history.state_projection
        )
    )
    return value


def decode_closure(raw, context, *, fact_bytes_cap):
    # No topic/dependency repair, guessed origin, polarity rewrite or retry.
    draft = decode_reconciled(raw, context, fact_bytes_cap=fact_bytes_cap)
    facts = tuple(
        dict.fromkeys(
            (
                *draft.facts,
                *(f for r in draft.references for f in r.candidates),
                *(f for a in draft.ambiguities for f in a.candidates),
            )
        )
    )
    # The generation envelope replaces an empty [] with the serialized list.
    # Pay the comma separators too; the two brackets already exist in its shell.
    insertion_bytes = sum(len(f.model_dump_json().encode()) for f in facts) + max(0, len(facts) - 1)
    if insertion_bytes > fact_bytes_cap:
        raise CoreConflict("closure_normalized_fact_envelope")
    return draft


def format_messages(context):
    from citeweave.evaluation.dev_state import evaluation_messages

    messages = evaluation_messages(context)
    messages[0]["content"] += "\n" + (ROOT / "prompts/conversation-interpretation-rc-v5.txt").read_text(
        encoding="utf-8"
    )
    payload = json.loads(messages[1]["content"])
    payload["output_schema"] = FormatDraft.model_json_schema()
    payload["decision_context"] = decision_context(context)
    messages[1]["content"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return messages
