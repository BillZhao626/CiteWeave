"""PostgreSQL accepted-history adapter; production scan/time admission is deferred.

The explicit local L1 permit only works in UUID-named isolated test databases.
Its finite table ceilings and 1000ms statement deadline are test resources, never
product parameters. No provider configuration or external index is involved.
"""

import json
from contextlib import contextmanager
from typing import Literal

from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from citeweave import conversations as core
from citeweave.conversation_contract import CoreConflict, DurableDTO, WorkingState, require_head
from citeweave.conversation_history import (
    MAX_BYTES,
    MAX_ROWS,
    MAX_TRIPS,
    HistoryQuery,
    HistorySelection,
    HistorySource,
    project_state,
    select_history,
)
from citeweave.db import transaction


class LocalHistoryRead(DurableDTO):
    """Explicit opt-in to the separately authorized synthetic L1 test envelope."""

    purpose: Literal["isolated_l1"] = "isolated_l1"


# Metadata filtering examines the bounded test corpus in PG, not a recent Python
# transcript. JSONB lookup metadata lives in immutable acceptance bundles. Each
# branch limits complete connected groups (not arbitrary correction members).
HISTORY_SQL = r"""
WITH RECURSIVE corpus AS MATERIALIZED (
 SELECT a.id, r.fence, t.request->'scope' AS scope,
        coalesce(a.state->'delta'->'signals', '{}'::jsonb) AS signals,
        coalesce(a.state->'delta'->'relations', '[]'::jsonb) AS relations,
        CASE WHEN a.id=:head THEN coalesce(a.state->'entries','[]'::jsonb)
             ELSE '[]'::jsonb END AS entries
 FROM cw5_acceptances a JOIN cw5_turns t ON t.id=a.turn_id
 JOIN cw5_runs r ON r.id=a.run_id
 WHERE a.conversation_id=:conversation AND r.status='ACCEPTED'
), edges AS (
 SELECT c.id AS source, (edge->'target'->>'acceptance_id')::uuid AS target,
        edge->>'kind' AS kind
 FROM corpus c CROSS JOIN LATERAL jsonb_array_elements(
     c.relations) edge
), links AS (
 SELECT source, target FROM edges UNION SELECT target, source FROM edges
), connected(root, member) AS (
 SELECT id, id FROM corpus
 UNION
 SELECT c.root, l.target FROM connected c JOIN links l ON l.source=c.member
), group_map AS (
 SELECT root, min(member::text) AS gid FROM connected GROUP BY root
), recent AS (
 SELECT id FROM corpus ORDER BY fence DESC, id LIMIT 2
), active AS (
 SELECT c.* FROM corpus c WHERE NOT EXISTS (
    SELECT 1 FROM edges e WHERE e.target=c.id AND e.kind='correction')
), matches AS (
 SELECT id, 'A' AS origin FROM recent
 UNION ALL SELECT id, 'explicit' FROM corpus WHERE id::text IN (
    SELECT jsonb_array_elements_text(CAST(:explicit AS jsonb)))
 UNION ALL SELECT id, 'entity_constraints' FROM active
 WHERE signals->>'task'=:task AND :task IS NOT NULL
   AND coalesce(signals->'entities','[]'::jsonb) ?| ARRAY(
       SELECT jsonb_array_elements_text(CAST(:entities AS jsonb)))
   AND CAST(:constraints AS jsonb) <@ coalesce(signals->'constraints','[]'::jsonb)
 UNION ALL SELECT id, 'task' FROM active WHERE signals->>'task'=:task AND :task IS NOT NULL
 UNION ALL SELECT id, 'topic' FROM active WHERE signals->>'topic'=:topic AND :topic IS NOT NULL
   AND (:task IS NULL OR signals->>'task'=:task)
 UNION ALL SELECT id, 'state' FROM corpus WHERE id=:head
 UNION ALL SELECT c.id, 'state_provenance' FROM corpus c WHERE c.id::text IN (
    SELECT item->'introduced_by'->>'acceptance_id' FROM corpus h
    CROSS JOIN LATERAL jsonb_array_elements(h.entries) item
    WHERE h.id=:head AND (item->>'active')::boolean
      AND item->'scope'->>'kb_id'=:kb
      AND item->'scope'->'version_ids' <@ CAST(:versions AS jsonb))
), scoped_matches AS (
 SELECT m.* FROM matches m JOIN corpus c ON c.id=m.id
 WHERE (c.scope->>'kb_id'=:kb
    AND c.scope->'version_ids' <@ CAST(:versions AS jsonb))
    OR m.origin IN ('state', 'explicit', 'state_provenance')
), branch_groups AS (
 SELECT DISTINCT origin, gid FROM scoped_matches m JOIN group_map g ON g.root=m.id
), ranked AS (
 SELECT *, row_number() OVER (PARTITION BY origin ORDER BY gid) AS position FROM branch_groups
), seeds AS (
 SELECT m.* FROM scoped_matches m JOIN group_map g ON g.root=m.id
 JOIN ranked r ON r.gid=g.gid AND r.origin=m.origin WHERE r.position<=8
), wanted AS (
 SELECT DISTINCT c.member AS id FROM connected c JOIN seeds s ON s.id=c.root
), originals AS MATERIALIZED (
 SELECT a.*, t.request FROM cw5_acceptances a JOIN wanted w ON w.id=a.id
 JOIN cw5_turns t ON t.id=a.turn_id
 WHERE (SELECT count(*) FROM wanted)<=:row_cap
), payload AS (
 SELECT coalesce(jsonb_agg(jsonb_build_object(
  'acceptance', jsonb_build_object('id',c.id,'conversation_id',c.conversation_id,
    'turn_id',c.turn_id,'run_id',c.run_id,'result',c.result,'state',c.state,'created_at',c.created_at),
  'request',c.request,
  'origins',coalesce((SELECT jsonb_agg(origin ORDER BY origin) FROM seeds s WHERE s.id=c.id), '[]'::jsonb)
 ) ORDER BY c.id), '[]'::jsonb)::text AS body,
 (SELECT count(*) FROM wanted) AS rows
 FROM originals c
)
SELECT rows, octet_length(body) AS bytes,
 CASE WHEN rows<=:row_cap AND octet_length(body)<=:byte_cap THEN body ELSE NULL END AS body,
 EXISTS(SELECT 1 FROM ranked WHERE position>8 AND origin NOT IN ('A','state')) AS branch_cutoff
FROM payload
"""


def read_history(workspace, conversation_id, query: HistoryQuery, *, permit: LocalHistoryRead | None = None):
    if permit is None or permit.purpose != "isolated_l1":
        return HistorySelection(head=query.expected_head, failure="history_query_disabled")
    counter = [0]
    try:
        return _read_local_history(workspace, conversation_id, query, counter)
    except CoreConflict as exc:
        if str(exc) != "round_trip_cap":
            raise
        return HistorySelection(
            head=query.expected_head,
            failure="search_incomplete",
            search_incomplete=True,
            cutoff=("round_trip_cap",),
            round_trips=counter[0],
        )
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) != "57014":
            raise
        return HistorySelection(
            head=query.expected_head,
            failure="search_incomplete",
            search_incomplete=True,
            cutoff=("statement_timeout",),
            round_trips=counter[0],
        )


@contextmanager
def _bounded_transaction(counter):
    with transaction() as db:
        connection = db.connection()

        def count(connection, cursor, statement, parameters, context, executemany):
            if counter[0] >= MAX_TRIPS:
                raise CoreConflict("round_trip_cap")
            counter[0] += 1

        event.listen(connection, "before_cursor_execute", count)
        try:
            yield db
        finally:
            event.remove(connection, "before_cursor_execute", count)


def _read_local_history(workspace, conversation_id, query, counter):
    with _bounded_transaction(counter) as db:
        # Timeout applies to locks as well as subsequent reads, and resets at commit.
        db.execute(text("SELECT set_config('statement_timeout', '1000', true)"))
        guard = db.execute(
            text("""
            SELECT current_database() ~ '^cw_conversation_test_[0-9a-f]{32}$',
              (SELECT count(*) FROM (SELECT 1 FROM cw5_acceptances LIMIT 513) a),
              (SELECT count(*) FROM (SELECT 1 FROM cw5_turns LIMIT 513) t),
              (SELECT count(*) FROM (SELECT 1 FROM cw5_runs LIMIT 1025) r)
        """)
        ).one()
        if not guard[0] or guard[1] > 512 or guard[2] > 512 or guard[3] > 1024:
            return HistorySelection(head=query.expected_head, failure="local_scan_envelope_exceeded")
        conversation = core._conversation(db, workspace, conversation_id)
        require_head(conversation.head_id, query.expected_head)
        core._scope(db, workspace, query.scope, current=True)
        # 1 deadline + 1 finite-scan guard + 1 conversation + 2 authorization + 1 history = 6 trips.
        result = db.execute(
            text(HISTORY_SQL),
            dict(
                conversation=conversation_id,
                head=query.expected_head,
                kb=str(query.scope.kb_id),
                versions=json.dumps([str(v) for v in query.scope.version_ids]),
                explicit=json.dumps([str(r.acceptance_id) for r in query.explicit + query.mandatory]),
                task=query.signals.task,
                topic=query.signals.topic,
                entities=json.dumps(query.signals.entities),
                constraints=json.dumps(query.signals.constraints),
                row_cap=MAX_ROWS,
                byte_cap=MAX_BYTES,
            ),
        ).one()
        limits = []
        if result.rows > MAX_ROWS:
            limits.append("row_cap")
        if result.bytes > MAX_BYTES:
            limits.append("payload_cap")
        if result.branch_cutoff:
            limits.append("branch_cap")
        sources = tuple(HistorySource.model_validate(v) for v in json.loads(result.body or "[]"))
        sources = tuple(
            s.model_copy(update={"origins": tuple(sorted(set(s.origins) | {"B"}))})
            if set(s.origins) & {"explicit", "entity_constraints", "task", "topic"}
            else s
            for s in sources
        )
        projection = ()
        for source in sources:
            if source.acceptance.id == query.expected_head:
                state = source.acceptance.state
                if isinstance(state, WorkingState):
                    try:
                        projection = project_state(state, query.scope)
                    except CoreConflict as exc:
                        limits.append(str(exc))
        selected = select_history(
            sources,
            query,
            projection,
            incomplete=tuple(limits),
            rows=len(sources),
            payload_bytes=result.bytes if result.body else 0,
            trips=counter[0],
        )
        # Head is returned inside the same bounded payload; no second state read.
        if (
            query.expected_head
            and not limits
            and not any(s.acceptance.id == query.expected_head for s in sources)
        ):
            raise CoreConflict("head_source_unavailable")
        return selected
