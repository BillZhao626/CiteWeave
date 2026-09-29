"""Deterministic intent memory mechanics. No text interpretation or Evidence types."""

from hashlib import sha256
from typing import Literal
from uuid import UUID

from pydantic import Field

from citeweave.conversation_contract import (
    Acceptance,
    Admission,
    CoreConflict,
    DurableDTO,
    HistoryRelation,
    ResolvedConversationDelta,
    ResolvedSignals,
    Scope,
    SourceRef,
    StateEntry,
    WorkingState,
)

# Accepted conservative implementation defaults, not measured optima.
N, C, K = 2, 8, 2
MAX_ROWS, MAX_BYTES, MAX_TRIPS, MAX_MEMBERS, MAX_PROJECTION = 64, 128 * 1024, 8, 8, 16
REASONS = ("explicit", "correction", "entity_constraints", "task", "topic")


def within(source: Scope, current: Scope) -> bool:
    return source.kb_id == current.kb_id and set(source.version_ids) <= set(current.version_ids)


def reduce_state(
    previous: Acceptance | None, source: SourceRef, scope: Scope, delta: ResolvedConversationDelta
) -> WorkingState:
    """Only the acceptance transaction supplies the new source identity.

    Inherited entries retain their original scope/provenance. No old snapshot is
    edited; inactive entries stay in this durable snapshot (projection is separate).
    """
    if delta.previous_snapshot_id != (previous.id if previous else None):
        raise CoreConflict("head_conflict")
    if delta.source_turn_id != source.turn_id:
        raise CoreConflict("snapshot_identity_conflict")
    entries = list(previous.state.entries) if previous and isinstance(previous.state, WorkingState) else []
    indexed = {e.item.id: e for e in entries}
    puts = [v.id for v in delta.put]
    targets = list(delta.deactivate) + [i for v in delta.put for i in v.replaces]
    if len(set(puts)) != len(puts) or set(puts) & indexed.keys():
        raise CoreConflict("state_identity_conflict")
    if len(set(targets)) != len(targets) or any(i not in indexed or not indexed[i].active for i in targets):
        raise CoreConflict("state_reference_unavailable")
    for relation in delta.relations:
        if relation.kind == "dependency" and relation.state_item_ids:
            raise CoreConflict("invalid_dependency_items")
        if any(
            i not in indexed or indexed[i].introduced_by != relation.target or not indexed[i].active
            for i in relation.state_item_ids
        ):
            raise CoreConflict("correction_item_unavailable")

    def corrected(entry):
        return any(
            r.kind == "correction"
            and r.target == entry.introduced_by
            and (not r.state_item_ids or entry.item.id in r.state_item_ids)
            for r in delta.relations
        )

    for value in delta.put:
        for identity in value.replaces:
            old = indexed[identity]
            if (old.item.kind, old.item.key) != (value.kind, value.key):
                raise CoreConflict("supersession_identity_conflict")
            if not corrected(old):
                raise CoreConflict("correction_provenance_missing")
    replaced = {i for v in delta.put for i in v.replaces}
    if any(not corrected(indexed[i]) for i in delta.deactivate):
        raise CoreConflict("correction_provenance_missing")
    output = []
    for entry in entries:
        change = None
        if entry.active and (entry.item.id in replaced or corrected(entry)):
            change = "superseded"
        if entry.item.id in delta.deactivate:
            change = "deactivated"
        elif entry.active and not within(entry.scope, scope):
            change = "scope_narrowed"
        if change:
            entry = entry.model_copy(update={"active": False, "changed_by": source, "change": change})
        output.append(entry)
    output.extend(StateEntry(item=v, introduced_by=source, scope=scope) for v in delta.put)
    active_keys = [
        (e.item.kind, "topic" if e.item.kind == "topic" else e.item.key) for e in output if e.active
    ]
    if len(set(active_keys)) != len(active_keys):
        raise CoreConflict("active_state_conflict")
    return WorkingState(
        source_turn_id=source.turn_id,
        previous_snapshot_id=delta.previous_snapshot_id,
        source=source,
        scope=scope,
        entries=tuple(output),
        delta=delta,
    )


def project_state(state: WorkingState, scope: Scope) -> tuple[StateEntry, ...]:
    entries = tuple(e for e in state.entries if e.active and within(e.scope, scope))
    if len(entries) > MAX_PROJECTION:
        raise CoreConflict("state_projection_cap")
    return entries


class HistoryQuery(DurableDTO):
    expected_head: UUID | None
    scope: Scope
    signals: ResolvedSignals = Field(default_factory=ResolvedSignals)
    explicit: tuple[SourceRef, ...] = ()
    mandatory: tuple[SourceRef, ...] = ()


class HistorySource(DurableDTO):
    acceptance: Acceptance
    request: Admission
    origins: tuple[str, ...] = ()

    @property
    def ref(self):
        return SourceRef(acceptance_id=self.acceptance.id, turn_id=self.acceptance.turn_id)

    @property
    def relations(self) -> tuple[HistoryRelation, ...]:
        state = self.acceptance.state
        return state.delta.relations if isinstance(state, WorkingState) else ()

    @property
    def signals(self):
        state = self.acceptance.state
        return state.delta.signals if isinstance(state, WorkingState) else ResolvedSignals()


class SourceEdge(DurableDTO):
    source: SourceRef
    relation: HistoryRelation


class HistoryGroup(DurableDTO):
    identity: tuple[UUID, ...]
    sources: tuple[HistorySource, ...]
    origins: tuple[str, ...]
    reasons: tuple[str, ...]
    edges: tuple[SourceEdge, ...]
    superseded: tuple[SourceRef, ...]
    partially_superseded: tuple[SourceRef, ...] = ()
    mandatory: bool
    # Full original request is retained; hashes refer to its unchanged UTF-8 bytes.
    request_hashes: tuple[str, ...]


class Rejection(DurableDTO):
    identity: tuple[UUID, ...]
    reason: str


class HistorySelection(DurableDTO):
    authority: Literal["contextual_intent_not_evidence"] = "contextual_intent_not_evidence"
    head: UUID | None
    a_inputs: tuple[SourceRef, ...] = ()
    branch_matches: dict[str, tuple[SourceRef, ...]] = Field(default_factory=dict)
    union_before_dedup: int = 0
    union_after_dedup: int = 0
    union_groups: tuple[tuple[UUID, ...], ...] = ()
    candidates: tuple[HistoryGroup, ...] = ()
    selected: tuple[HistoryGroup, ...] = ()
    rejected: tuple[Rejection, ...] = ()
    state_projection: tuple[StateEntry, ...] = ()
    search_incomplete: bool = False
    cutoff: tuple[str, ...] = ()
    failure: str | None = None
    materialized_rows: int = 0
    payload_bytes: int = 0
    round_trips: int = 0


def match_reasons(source: HistorySource, query: HistoryQuery) -> tuple[str, ...]:
    reasons = []
    if source.ref in query.explicit or source.ref in query.mandatory:
        reasons.append("explicit")
    a, b = source.signals, query.signals
    # An entity in another task must not leak through topic or entity branches.
    applicable = a.task == b.task and a.task is not None
    if applicable and set(a.entities) & set(b.entities) and set(b.constraints) <= set(a.constraints):
        reasons.append("entity_constraints")
    if applicable:
        reasons.append("task")
    if a.topic is not None and a.topic == b.topic and (b.task is None or applicable):
        reasons.append("topic")
    return tuple(reasons)


def select_history(
    sources: tuple[HistorySource, ...],
    query: HistoryQuery,
    projection: tuple[StateEntry, ...] = (),
    *,
    incomplete: tuple[str, ...] = (),
    rows: int = 0,
    payload_bytes: int = 0,
    trips: int = 0,
) -> HistorySelection:
    """Input contains complete connected provenance groups from the PG adapter.

    A is candidate context only; it receives no implicit relevance. Any incomplete
    search fails closed, since a missing correction can invalidate a found source.
    """
    base = dict(
        head=query.expected_head,
        materialized_rows=rows,
        payload_bytes=payload_bytes,
        round_trips=trips,
        state_projection=projection,
    )
    limits = list(incomplete)
    for failed, name in (
        (rows > MAX_ROWS, "row_cap"),
        (payload_bytes > MAX_BYTES, "payload_cap"),
        (trips > MAX_TRIPS, "round_trip_cap"),
        (len(projection) > MAX_PROJECTION, "state_projection_cap"),
    ):
        if failed:
            limits.append(name)
    if limits:
        return HistorySelection(
            **base, search_incomplete=True, cutoff=tuple(limits), failure="search_incomplete"
        )
    by_id = {}
    for source in sources:
        identity = source.acceptance.id
        if identity in by_id:
            prior = by_id[identity]
            if prior.model_copy(update={"origins": ()}) != source.model_copy(update={"origins": ()}):
                raise CoreConflict("provenance_identity_conflict")
            source = source.model_copy(update={"origins": tuple(sorted(set(prior.origins + source.origins)))})
        by_id[identity] = source
    required = set(query.explicit + query.mandatory) | {e.introduced_by for e in projection}
    refs = {s.ref for s in by_id.values()}
    if not required <= refs:
        return HistorySelection(**base, failure="mandatory_source_unavailable", search_incomplete=True)
    adjacent = {i: set() for i in by_id}
    all_edges = []
    for source in by_id.values():
        for relation in source.relations:
            if relation.target not in refs:
                return HistorySelection(**base, failure="incomplete_group", search_incomplete=True)
            adjacent[source.acceptance.id].add(relation.target.acceptance_id)
            adjacent[relation.target.acceptance_id].add(source.acceptance.id)
            all_edges.append(SourceEdge(source=source.ref, relation=relation))
    all_edges = sorted(
        set(all_edges),
        key=lambda e: (
            e.source.acceptance_id,
            e.relation.target.acceptance_id,
            e.relation.kind,
            e.relation.state_item_ids,
        ),
    )
    groups, rejected, visited = [], [], set()
    union_groups, before_dedup = [], 0
    branch_matches = {reason: [] for reason in REASONS if reason != "correction"}
    for identity in sorted(by_id):
        if identity in visited:
            continue
        todo, component = [identity], set()
        while todo:
            current = todo.pop()
            if current not in component:
                component.add(current)
                todo.extend(adjacent[current] - component)
        visited |= component
        members = tuple(by_id[i] for i in sorted(component))
        ids = tuple(sorted(component))
        union_groups.append(ids)
        before_dedup += len(
            {
                o
                for s in members
                for o in s.origins
                if o in {"A", "explicit", "entity_constraints", "task", "topic"}
            }
        )
        if len(members) > MAX_MEMBERS:
            return HistorySelection(**base, failure="group_member_cap", search_incomplete=True)
        if any(not within(s.request.scope, query.scope) for s in members):
            if any(s.ref in required for s in members):
                return HistorySelection(**base, failure="mandatory_scope_unavailable", search_incomplete=True)
            rejected.append(Rejection(identity=ids, reason="scope_unavailable"))
            continue
        edges = tuple(e for e in all_edges if e.source.acceptance_id in component)
        superseded = tuple(
            sorted(
                {
                    e.relation.target
                    for e in edges
                    if e.relation.kind == "correction" and not e.relation.state_item_ids
                },
                key=lambda r: r.acceptance_id,
            )
        )
        partial = tuple(
            sorted(
                {
                    e.relation.target
                    for e in edges
                    if e.relation.kind == "correction"
                    and e.relation.state_item_ids
                    and e.relation.target not in superseded
                },
                key=lambda r: r.acceptance_id,
            )
        )
        reasons = set()
        for member in members:
            matches = match_reasons(member, query)
            if member.ref in superseded or member.ref in partial:
                # Old turn-level tags cannot prove which signals survived a partial
                # correction; resolved state provenance can still require this group.
                matches = tuple(r for r in matches if r == "explicit")
            reasons.update(matches)
            for match in matches:
                branch_matches[match].append(member.ref)
        mandatory = any(s.ref in required for s in members)
        if mandatory:
            reasons.add("explicit")
        if not reasons:
            rejected.append(Rejection(identity=ids, reason="no_active_relevance"))
            continue
        if superseded or partial:
            reasons.add("correction")
        groups.append(
            HistoryGroup(
                identity=ids,
                sources=members,
                origins=tuple(sorted({o for s in members for o in s.origins})),
                reasons=tuple(r for r in REASONS if r in reasons),
                edges=edges,
                superseded=superseded,
                partially_superseded=partial,
                mandatory=mandatory,
                request_hashes=tuple(sha256(s.request.question.encode("utf-8")).hexdigest() for s in members),
            )
        )
    groups.sort(key=lambda g: (not g.mandatory, min(REASONS.index(r) for r in g.reasons), g.identity))
    base.update(
        a_inputs=tuple(sorted({s.ref for s in sources if "A" in s.origins}, key=lambda r: r.acceptance_id)),
        branch_matches={
            k: tuple(sorted(set(v), key=lambda r: r.acceptance_id)) for k, v in branch_matches.items()
        },
        union_before_dedup=before_dedup,
        union_after_dedup=len(union_groups),
        union_groups=tuple(union_groups),
    )
    if sum(g.mandatory for g in groups) > C:
        return HistorySelection(**base, failure="mandatory_exceeds_C")
    candidates = tuple(groups[:C])
    for group in groups[C:]:
        rejected.append(Rejection(identity=group.identity, reason="C_cutoff"))
    if sum(g.mandatory for g in candidates) > K:
        return HistorySelection(**base, candidates=candidates, failure="mandatory_exceeds_K")
    for group in candidates[K:]:
        rejected.append(Rejection(identity=group.identity, reason="K_cutoff"))
    return HistorySelection(
        **base,
        candidates=candidates,
        selected=candidates[:K],
        rejected=tuple(rejected),
        cutoff=tuple(
            n for n, hit in (("C_cutoff", len(groups) > C), ("K_cutoff", len(candidates) > K)) if hit
        ),
    )
