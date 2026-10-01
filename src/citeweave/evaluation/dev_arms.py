"""Evaluation-only factors. Production selector, ranking and state are unchanged."""

from dataclasses import asdict, dataclass

from citeweave.conversation_history import (
    MAX_BYTES,
    MAX_MEMBERS,
    MAX_PROJECTION,
    MAX_ROWS,
    MAX_TRIPS,
    HistorySelection,
    select_history,
)
from citeweave.evaluation.dev_dataset import digest

ARM_IDS = ("EXISTING_V01_CONTRACT", "cp-r-v1", "cp-a-v1", "cp-ab0-v1")
COMMON = dict(
    retrieval="telecom-structural-v1",
    interpretation="conversation-interpretation-v1+evaluation-state-intent-v2",
    serializer="existing-production-components-per-contract",
    correction="atomic-complete-group",
    member_cap=MAX_MEMBERS,
    projection_cap=MAX_PROJECTION,
    rows=MAX_ROWS,
    bytes=MAX_BYTES,
    trips=MAX_TRIPS,
    retry=0,
    refetch=0,
    judge=0,
    clarification="owner-state-intent-review-revise-20261001",
)


@dataclass(frozen=True)
class Arm:
    id: str
    n: int
    state: bool
    b: bool
    c: int = 8
    k: int = 2

    @property
    def common_hash(self):
        return digest(COMMON)

    @property
    def config_hash(self):
        serializer = "answering.stream_answer" if self.id == ARM_IDS[0] else "generation_messages"
        return digest(dict(common=COMMON, factors=asdict(self), serializer=serializer))


def arm(identity):
    if identity not in ARM_IDS:
        raise ValueError("dev_arm_rejected")
    return Arm(identity, 0 if identity == ARM_IDS[0] else 2, identity in ARM_IDS[2:], identity == ARM_IDS[3])


def select_arm(identity, recent, b_roots, query, projection, fetch, *, state_only_intent=False):
    """fetch only receives permitted raw-member IDs; B roots come from metadata.

    Relations are expanded only for AB0, using bounded batches. R/A never ask for
    older member text, even when a relation or current state points to it. The
    existing selector then enforces scope, group integrity, caps and supersession.
    """
    config = arm(identity)
    if len(recent) > config.n:
        raise ValueError("dev_recent_window_mismatch")
    if identity == ARM_IDS[0]:
        return HistorySelection(head=query.expected_head)
    projection = projection if config.state else ()
    roots = set(recent) | (set(b_roots) if config.b else set())
    pending, loaded, trips = set(roots), {}, 0
    closure_from_b = set(b_roots) if config.b else set()
    while pending:
        if trips >= MAX_TRIPS or len(loaded) + len(pending) > MAX_ROWS:
            return HistorySelection(
                head=query.expected_head,
                failure="search_incomplete",
                search_incomplete=True,
                cutoff=("round_trip_or_row_cap",),
                round_trips=trips,
            )
        values = fetch(tuple(sorted(pending, key=lambda r: r.acceptance_id)))
        trips += 1
        if {s.ref for s in values} != pending:
            return HistorySelection(
                head=query.expected_head, failure="source_unavailable", search_incomplete=True
            )
        loaded.update({s.ref: s for s in values})
        pending = set()
        if config.b:
            # Complete undirected group attribution; no outside-window closure
            # is enabled merely because the arm has B configured.
            changed = True
            while changed:
                before = set(closure_from_b)
                for s in loaded.values():
                    for relation in s.relations:
                        if s.ref in closure_from_b or relation.target in closure_from_b:
                            closure_from_b.update((s.ref, relation.target))
                changed = before != closure_from_b
            for s in loaded.values():
                for relation in s.relations:
                    if relation.target not in loaded and (
                        s.ref in closure_from_b or relation.target in recent
                    ):
                        pending.add(relation.target)
    values = tuple(
        s.model_copy(
            update={
                "origins": tuple(
                    label
                    for label, present in (("A", s.ref in recent), ("B", s.ref in closure_from_b))
                    if present
                )
            }
        )
        for s in loaded.values()
    )
    payload = sum(len(s.model_dump_json().encode()) for s in values)
    # Current semantic state need not admit its old raw introducer in ordinary
    # intent views. Atomic relations among admitted raw sources remain enforced.
    selector_projection = projection
    if identity == "cp-a-v1" and state_only_intent:
        selector_projection = tuple(e for e in projection if e.introduced_by in roots)
    selected = select_history(
        values,
        query,
        selector_projection,
        rows=len(values),
        payload_bytes=payload,
        trips=trips,
    )
    return selected.model_copy(update={"state_projection": projection})
