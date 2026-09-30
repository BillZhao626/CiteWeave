"""Internal intent interpretation, with no provider/runtime or Evidence authority.

Drafts are semantic inputs, not semantic proofs. The guards prove exact source,
scope and structural retention only. No raw-text self-containedness heuristic is
provided. Until independently authorized execution exists, callers supply resolved
drafts or an explicitly injected fake. Nothing here dispatches production work.
"""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID, uuid5

from pydantic import Field, model_validator

from citeweave.catalog import fingerprint
from citeweave.conversation_contract import (
    Acceptance,
    Admission,
    CoreConflict,
    DurableDTO,
    HistoryRelation,
    ProducedResult,
    ResolvedConversationDelta,
    ResolvedSignals,
    Scope,
    SourceRef,
    StateValue,
    WorkingState,
)
from citeweave.conversation_history import (
    MAX_ROWS,
    HistorySelection,
    HistorySource,
    project_state,
    reduce_state,
    within,
)

FactKind = Literal["topic", "task", "entity", "constraint", "document", "version", "time", "negation"]


class TextSpan(DurableDTO):
    # Python code-point offsets in the original question, NOT documentary offsets.
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class CriticalTerm(DurableDTO):
    dimension: FactKind
    value: str = Field(min_length=1)


class IntentFact(DurableDTO):
    kind: FactKind
    value: str = Field(min_length=1)
    span: TextSpan | None = None
    source: SourceRef | None = None
    state_item_id: UUID | None = None

    @model_validator(mode="after")
    def origin(self):
        if (self.span is None) == (self.source is None):
            raise ValueError("exactly_one_intent_origin_required")
        if self.state_item_id is not None and self.source is None:
            raise ValueError("state_source_required")
        return self


class ReferenceDraft(DurableDTO):
    mention: TextSpan
    candidates: tuple[IntentFact, ...] = ()


class Ambiguity(DurableDTO):
    reason: Literal["unresolved_reference", "multiple_candidates", "unresolved_intent", "pending_ambiguity"]
    mention: TextSpan | None = None
    candidates: tuple[IntentFact, ...] = ()


class RetrievalRewrite(DurableDTO):
    text: str = Field(min_length=1)
    scope: Scope
    retained: tuple[CriticalTerm, ...] = ()


class StateCorrection(DurableDTO):
    item_id: UUID
    mention: TextSpan


class InterpretationDraft(DurableDTO):
    topic_relation: Literal["continue", "shift", "return"]
    dependency: Literal["none", "required", "unresolved"]
    facts: tuple[IntentFact, ...] = ()
    references: tuple[ReferenceDraft, ...] = ()
    ambiguities: tuple[Ambiguity, ...] = ()
    rewrite: RetrievalRewrite | None = None
    put: tuple[StateValue, ...] = ()
    corrections: tuple[StateCorrection, ...] = ()


class InterpretationInput(DurableDTO):
    conversation_id: UUID
    turn_id: UUID
    request: Admission
    history: HistorySelection
    previous: Acceptance | None = None
    # Already resolved assertions, never silently extracted with NLP/regex.
    required: tuple[CriticalTerm, ...] = ()


class InterpretationResult(DurableDTO):
    revision: Literal["conversation-interpretation-v1"] = "conversation-interpretation-v1"
    authority: Literal["contextual_intent_not_evidence"] = "contextual_intent_not_evidence"
    mode: Literal["USE_ORIGINAL", "USE_REWRITE", "CLARIFY"]
    input_mode: Literal["supplied_structured_draft", "injected_interpreter"]
    original_question: str
    proposed_rewrite: str | None
    selected_query: str | None
    scope: Scope
    topic_relation: Literal["continue", "shift", "return"]
    sources: tuple[SourceRef, ...]
    bindings: tuple[ReferenceDraft, ...]
    facts: tuple[IntentFact, ...]
    ambiguities: tuple[Ambiguity, ...]
    guard_outcome: Literal["STRUCTURAL_ONLY"] = "STRUCTURAL_ONLY"
    delta: ResolvedConversationDelta
    delta_identity: str
    control_result: ProducedResult | None


class Interpreter(Protocol):
    """Combined interpretation seam; no configured implementation or dispatch."""

    def interpret(self, context: InterpretationInput) -> InterpretationDraft: ...


@dataclass
class FakeInterpreter:
    """One deterministic supplied draft. Only a fixture, never provider quality."""

    draft: InterpretationDraft
    calls: int = 0

    def interpret(self, context: InterpretationInput) -> InterpretationDraft:
        self.calls += 1
        return self.draft


def selected_sources(context: InterpretationInput) -> tuple[HistorySource, ...]:
    history, previous = context.history, context.previous
    if history.failure or history.search_incomplete:
        raise CoreConflict("interpretation_history_unavailable")
    if history.head != context.request.expected_head or history.head != (previous.id if previous else None):
        raise CoreConflict("head_conflict")
    if previous and previous.conversation_id != context.conversation_id:
        raise CoreConflict("interpretation_conversation_conflict")
    projection = (
        project_state(previous.state, context.request.scope)
        if previous and isinstance(previous.state, WorkingState)
        else ()
    )
    if history.state_projection != projection:
        raise CoreConflict("interpretation_projection_conflict")
    sources = {}
    for group in history.selected:
        for source in group.sources:
            if source.acceptance.conversation_id != context.conversation_id:
                raise CoreConflict("interpretation_conversation_conflict")
            if not within(source.request.scope, context.request.scope):
                raise CoreConflict("interpretation_scope_unavailable")
            if source.ref in sources and sources[source.ref] != source:
                raise CoreConflict("provenance_identity_conflict")
            sources[source.ref] = source
    if len(sources) > MAX_ROWS:
        raise CoreConflict("interpretation_source_cap")
    if any(r.target not in sources for s in sources.values() for r in s.relations):
        raise CoreConflict("interpretation_incomplete_provenance")
    return tuple(sources.values())


def _span(context, span):
    if span.start >= span.end or span.end > len(context.request.question):
        raise CoreConflict("interpretation_span_invalid")
    return context.request.question[span.start : span.end]


def _state_kind(kind):
    return kind if kind in {"topic", "entity"} else "constraint"


def interpret(
    context: InterpretationInput,
    *,
    draft: InterpretationDraft | None = None,
    interpreter: Interpreter | None = None,
) -> InterpretationResult:
    sources = {s.ref: s for s in selected_sources(context)}
    if draft is not None and interpreter is not None:
        raise CoreConflict("ambiguous_interpreter_input")
    input_mode = "supplied_structured_draft"
    if draft is None:
        if interpreter is None:
            raise CoreConflict("interpretation_required")
        input_mode = "injected_interpreter"
        draft = interpreter.interpret(context)
    # Validate even injected objects; model_copy is not a validation boundary.
    draft = InterpretationDraft.model_validate(draft.model_dump(mode="json"))
    for term in context.required:
        if term.value not in context.request.question:
            raise CoreConflict("interpretation_required_term_invalid")
    entries = {e.item.id: e for e in context.history.state_projection}
    all_entries = (
        context.previous.state.entries
        if context.previous and isinstance(context.previous.state, WorkingState)
        else ()
    )
    shift_sources = {
        s.ref
        for s in sources.values()
        if isinstance(s.acceptance.state, WorkingState)
        and s.acceptance.state.delta.topic_relation in {"shift", "return"}
        and not any(v.replaces for v in s.acceptance.state.delta.put)
    }
    corrections = [
        r
        for s in sources.values()
        if s.ref not in shift_sources
        for r in s.relations
        if r.kind == "correction"
    ]

    def validate_fact(fact):
        if fact.source is None:
            if _span(context, fact.span) != fact.value:
                raise CoreConflict("interpretation_current_provenance_invalid")
            return
        if fact.source not in sources:
            raise CoreConflict("interpretation_source_unavailable")
        if fact.state_item_id is not None:
            entry = entries.get(fact.state_item_id)
            if entry is None or entry.introduced_by != fact.source:
                raise CoreConflict("interpretation_state_superseded_or_unavailable")
            if (entry.item.kind, entry.item.value) != (_state_kind(fact.kind), fact.value):
                raise CoreConflict("interpretation_state_value_conflict")
            if any(
                r.target == fact.source and (not r.state_item_ids or fact.state_item_id in r.state_item_ids)
                for r in corrections
            ):
                raise CoreConflict("interpretation_source_superseded")
        else:
            # Partially corrected sources must bind a particular still-active item.
            if any(r.target == fact.source for r in corrections) or any(
                not e.active and e.introduced_by == fact.source and e.changed_by not in shift_sources
                for e in all_entries
            ):
                raise CoreConflict("interpretation_source_superseded")
            signals = sources[fact.source].signals
            values = (
                (getattr(signals, fact.kind),)
                if fact.kind in {"topic", "task"}
                else signals.entities
                if fact.kind == "entity"
                else signals.constraints
            )
            if fact.value not in values:
                raise CoreConflict("interpretation_incomplete_provenance")

    facts = list(draft.facts)
    ambiguities = list(draft.ambiguities)
    bindings = []
    mentions = {}
    for reference in draft.references:
        mentions.setdefault(reference.mention, []).extend(reference.candidates)
    for mention, proposals in mentions.items():
        reference = ReferenceDraft(mention=mention, candidates=tuple(proposals))
        _span(context, reference.mention)
        candidates = tuple(dict.fromkeys(reference.candidates))
        for candidate in candidates:
            if candidate.source is None:
                raise CoreConflict("historical_reference_source_required")
            validate_fact(candidate)
        if len(candidates) != 1:
            ambiguities.append(
                Ambiguity(
                    reason="multiple_candidates" if candidates else "unresolved_reference",
                    mention=reference.mention,
                    candidates=candidates,
                )
            )
        else:
            bindings.append(reference.model_copy(update={"candidates": candidates}))
            facts.extend(candidates)
    for ambiguity in ambiguities:
        if ambiguity.mention is not None:
            _span(context, ambiguity.mention)
        for candidate in ambiguity.candidates:
            validate_fact(candidate)
    for fact in facts:
        validate_fact(fact)
    facts = list(dict.fromkeys(facts))
    correction_ids = set()
    for correction in draft.corrections:
        _span(context, correction.mention)
        if correction.item_id not in entries or correction.item_id in correction_ids:
            raise CoreConflict("interpretation_correction_unavailable")
        correction_ids.add(correction.item_id)
    if draft.topic_relation != "shift" and any(
        e.item.kind == "ambiguity" and e.item.id not in correction_ids for e in entries.values()
    ):
        ambiguities.append(Ambiguity(reason="pending_ambiguity"))
    if draft.dependency == "unresolved" and not ambiguities:
        ambiguities.append(Ambiguity(reason="unresolved_intent"))

    used = {f.source for f in facts if f.source is not None}
    used.update(f.source for a in ambiguities for f in a.candidates if f.source is not None)
    put, deactivate = draft.put, set(correction_ids)
    signals = ResolvedSignals()
    control = None
    if ambiguities:
        mode, selected, bindings = "CLARIFY", None, []
        # Discard ALL proposed resolved mutations. Publish only typed ambiguity.
        deactivate = {e.item.id for e in entries.values() if e.item.kind == "ambiguity"}
        payload = fingerprint([a.model_dump(mode="json") for a in ambiguities])
        put = (
            StateValue(
                id=uuid5(context.turn_id, "ambiguity:" + payload),
                kind="ambiguity",
                key="interpretation",
                value=AmbiguityBundle(items=tuple(ambiguities)).model_dump_json(),
            ),
        )
        control = ProducedResult(
            kind="clarification", text="请明确当前问题的指代或意图；尚未选择候选，也未生成文档答案。"
        )
    else:
        if draft.topic_relation in {"shift", "return"} and (
            draft.corrections or any(v.replaces for v in put)
        ):
            # A combined correction + topic transition is unresolved in this
            # bounded contract; never label a correction recoverable retirement.
            raise CoreConflict("shift_correction_requires_separate_resolution")
        if draft.topic_relation == "shift":
            if used:
                raise CoreConflict("topic_shift_inheritance")
            deactivate.update(entries)
        if draft.topic_relation == "return" and not used:
            raise CoreConflict("topic_return_provenance_required")
        if draft.topic_relation == "return":
            retained_items = {f.state_item_id for f in facts if f.state_item_id is not None}
            deactivate.update(set(entries) - retained_items)
        if draft.topic_relation != "return" and any(
            f.source is not None
            and f.state_item_id is None
            and any(not e.active and e.introduced_by == f.source for e in all_entries)
            for f in facts
        ):
            raise CoreConflict("inactive_topic_requires_return")
        topics = tuple(dict.fromkeys(f.value for f in facts if f.kind == "topic"))
        tasks = tuple(dict.fromkeys(f.value for f in facts if f.kind == "task"))
        if len(topics) > 1 or len(tasks) > 1:
            raise CoreConflict("interpretation_signal_conflict")
        if draft.topic_relation == "continue":
            old_topics = {
                e.item.value
                for e in entries.values()
                if e.item.kind == "topic" and e.item.id not in correction_ids
            }
            old_task = (
                context.previous.state.delta.signals.task
                if context.previous and isinstance(context.previous.state, WorkingState)
                else None
            )
            if (topics and old_topics and set(topics) != old_topics) or (
                tasks and old_task is not None and tasks[0] != old_task
            ):
                raise CoreConflict("topic_relation_conflict")
        signals = ResolvedSignals(
            topic=topics[0] if topics else None,
            task=tasks[0] if tasks else None,
            entities=tuple(dict.fromkeys(f.value for f in facts if f.kind == "entity")),
            constraints=tuple(
                dict.fromkeys(f.value for f in facts if f.kind not in {"topic", "task", "entity"})
            ),
        )
        for value in put:
            if value.kind == "ambiguity" or not any(
                (_state_kind(f.kind), f.value) == (value.kind, value.value) for f in facts
            ):
                raise CoreConflict("interpretation_state_provenance_missing")
            if not set(value.replaces) <= correction_ids:
                raise CoreConflict("interpretation_correction_provenance_missing")
        if any(
            f.source is not None
            and any(
                e.item.id in correction_ids
                and e.introduced_by == f.source
                and (f.state_item_id is None or f.state_item_id == e.item.id)
                for e in entries.values()
            )
            for f in facts
        ):
            raise CoreConflict("corrected_binding_cannot_reactivate")
        inherited = tuple(dict.fromkeys(f.value for f in facts if f.source is not None))
        if draft.dependency == "none":
            if used or bindings:
                raise CoreConflict("independent_query_inheritance")
            mode, selected = "USE_ORIGINAL", context.request.question
        else:
            if not inherited or draft.rewrite is None:
                raise CoreConflict("rewrite_required")
            rewrite = draft.rewrite
            if rewrite.scope != context.request.scope:
                raise CoreConflict("rewrite_scope_conflict")
            # Conservative completion-only form: no free-form additions/deletions.
            expected = context.request.question + "\n" + "\n".join(inherited)
            if rewrite.text != expected or rewrite.retained != context.required:
                raise CoreConflict("rewrite_fidelity_conflict")
            mode, selected = "USE_REWRITE", rewrite.text

    replaced = {i for value in put for i in value.replaces}
    targets = deactivate | replaced
    relations = []
    for identity in sorted(targets):
        entry = entries[identity]
        if entry.introduced_by not in sources:
            raise CoreConflict("interpretation_correction_source_unavailable")
        relations.append(
            HistoryRelation(target=entry.introduced_by, kind="correction", state_item_ids=(identity,))
        )
    relations.extend(
        HistoryRelation(target=ref, kind="dependency")
        for ref in sorted(used, key=lambda r: (r.acceptance_id, r.turn_id))
    )
    delta = ResolvedConversationDelta(
        source_turn_id=context.turn_id,
        previous_snapshot_id=context.request.expected_head,
        signals=signals,
        put=put,
        deactivate=tuple(sorted(deactivate - replaced)),
        relations=tuple(relations),
        topic_relation=draft.topic_relation if not ambiguities else None,
    )
    # Reuse the authoritative reducer for all provisional validation. This source
    # is never published; acceptance supplies the real immutable bundle identity.
    reduce_state(
        context.previous,
        SourceRef(acceptance_id=uuid5(context.turn_id, "validation-only"), turn_id=context.turn_id),
        context.request.scope,
        delta,
    )
    all_used = used | {r.target for r in relations}
    return InterpretationResult(
        mode=mode,
        input_mode=input_mode,
        original_question=context.request.question,
        proposed_rewrite=draft.rewrite.text if draft.rewrite else None,
        selected_query=selected,
        scope=context.request.scope,
        topic_relation=draft.topic_relation,
        sources=tuple(sorted(all_used, key=lambda r: (r.acceptance_id, r.turn_id))),
        bindings=tuple(bindings),
        facts=tuple(facts) if not ambiguities else (),
        ambiguities=tuple(ambiguities),
        delta=delta,
        delta_identity=fingerprint(delta.model_dump(mode="json")),
        control_result=control,
    )


class AmbiguityBundle(DurableDTO):
    """Stored as a typed JSON value in the existing unresolved-state item."""

    items: tuple[Ambiguity, ...]
