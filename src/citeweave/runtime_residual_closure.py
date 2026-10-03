"""Validated normal form for an explicit, uniquely bound older task.

Never derives topic relation from State age, question keywords or case labels.
"""

import json

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_interpretation import interpret
from citeweave.runtime_rc_closure import FormatDraft, decode_closure
from citeweave.runtime_rc_closure import decision_context as closure_context
from citeweave.settings import ROOT

REVISION = "interpretation-residual-v6"


def _unique_old_task(context, draft):
    if (
        draft.dependency != "required"
        or draft.ambiguities
        or draft.corrections
        or draft.put
        or not context.previous
        or any(len(set(r.candidates)) != 1 for r in draft.references)
    ):
        return False
    sources = tuple(s for g in context.history.selected for s in g.sources)
    if any(s.relations for s in sources):
        return False  # Atomic correction groups retain the existing model/core path.
    head_task = context.previous.state.delta.signals.task
    facts = tuple(dict.fromkeys((*draft.facts, *(f for r in draft.references for f in r.candidates))))
    tasks = tuple(f for f in facts if f.kind == "task")
    if len(tasks) != 1:
        return False
    task = tasks[0]
    if (
        task.source is None
        or task.state_item_id is not None
        or task.source.acceptance_id == context.previous.id
        or not head_task
        or task.value == head_task
        or context.request.question.count(task.value) != 1
    ):
        return False
    matching = tuple(s for s in sources if s.signals.task == task.value)
    if len(matching) != 1 or matching[0].ref != task.source:
        return False
    if any(f.source is not None and f.source != task.source for f in facts):
        return False
    entities = tuple(f for f in facts if f.kind == "entity" and f.source == task.source)
    if len({f.value for f in entities}) != 1:
        return False
    if any(f.kind == "entity" and f not in entities for f in facts):
        return False
    if any(f.kind == "topic" and f.value != matching[0].signals.topic for f in facts):
        return False
    # The raw declaration was already continue/required. Exact old task and
    # same-origin entity identify its intent; return is its only valid core form.
    return True


def decode_residual(raw, context, *, fact_bytes_cap):
    try:
        return decode_closure(raw, context, fact_bytes_cap=fact_bytes_cap)
    except CoreConflict as original:
        if str(original) != "reconciliation_topic_return_required":
            raise
        # v5 has already rejected malformed/duplicate JSON, schema, unsupported
        # or ambiguous origins and its existing fact byte cap before this guard.
        value = FormatDraft.model_validate(json.loads(raw))
        if value.topic_relation != "continue":
            raise original
        candidate = value.model_copy(update={"topic_relation": "return"})
        draft = decode_closure(candidate.model_dump_json(), context, fact_bytes_cap=fact_bytes_cap)
        if (
            draft.put
            or draft.corrections
            or any(s.relations for g in context.history.selected for s in g.sources)
        ):
            raise original
        result = interpret(context, draft=draft)  # Validate every existing semantic/provenance invariant.
        if result.mode == "CLARIFY":
            # The shared core checks ambiguity before topic transitions. Preserve
            # the raw relation and its unresolved control action, without choosing
            # a task, issuing a query or publishing a successful return.
            unresolved = draft.model_copy(update={"topic_relation": value.topic_relation})
            if interpret(context, draft=unresolved).mode != "CLARIFY":
                raise original
            return unresolved
        if not _unique_old_task(context, draft):
            raise original
        if result.mode != "USE_REWRITE":
            raise original
        return draft


def decision_context(context):
    value = closure_context(context)
    value["topic_contract"] = dict(
        shift="self-contained new intent; no inherited origins",
        continue_topic="same stable head task",
        return_topic="older intended task with validated origins; State age alone is insufficient",
        state_reference="single exact active State candidate is valid ordinary intent; no raw reconstruction",
        old_task_normal_form="continue/required can normalize only with one exact older History task and same-origin entity, unique current literal, no ambiguity/correction/mutation; all core checks apply",
    )
    return value


def output_schema():
    schema = FormatDraft.model_json_schema()
    # Expose an existing core invariant without replacing the shared DTO.
    schema["allOf"] = [
        {
            "if": {"properties": {"topic_relation": {"const": "shift"}}, "required": ["topic_relation"]},
            "then": {"properties": {"dependency": {"const": "none"}}},
        }
    ]
    return schema


def format_messages(context):
    from citeweave.evaluation.dev_state import evaluation_messages

    messages = evaluation_messages(context)
    messages[0]["content"] += "\n" + (ROOT / "prompts/conversation-interpretation-rc-v5.txt").read_text(
        encoding="utf-8"
    )
    messages[0]["content"] += "\n" + (ROOT / "prompts/conversation-interpretation-residual-v6.txt").read_text(
        encoding="utf-8"
    )
    payload = json.loads(messages[1]["content"])
    payload["output_schema"] = output_schema()
    payload["decision_context"] = decision_context(context)
    messages[1]["content"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return messages
