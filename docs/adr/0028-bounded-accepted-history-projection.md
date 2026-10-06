# ADR 0028 — Bounded accepted-history read projection

Status: local E2.4 implementation; not released. The real two-turn gate is not certified.

## Observed problem and consumer audit

The real accepted first turn produced a 206,083-byte PostgreSQL history payload,
over the existing 131,072-byte boundary. Its accepted result was 204,700 bytes,
including answer 176,640 (citations 175,055), EvidencePack 24,122, snapshot 1,829,
answer text 1,240 and trace 730 bytes. Field sizes use `jsonb::text`; enclosing
keys/separators add overhead and nested sizes must not be summed twice.

`HistorySource.ref`, `relations` and `signals` use accepted identity and state.
`select_history` uses these, request/scope, correction edges, and active state
provenance. `selected_sources`/`interpret` validate identity, scope, retained state
and source facts. Interpretation messages send source refs, previous questions,
signals/relations and active state. Generation assembles bounded intent from this
selection alongside freshly retrieved current Evidence. None reads the old result.

The Acceptance transaction also compares caller history to durable rows. Its
comparison must use the same explicit projection, without removing the durable
lookup or current documentary-result validation. Legacy evaluation receipts contain
full Acceptance objects and must remain readable and reproducible unchanged.

## Decision

Add the internal typed `AcceptedHistory`: acceptance/conversation/turn/run IDs,
full versioned StateSnapshot or WorkingState, and created_at. `HistorySource`
retains the complete Admission (original question, scope and expected head) and
origins. Full state is deliberately retained: inactive entries and relations are
needed for supersession and topic-return guards. No string or structured JSON is
truncated. The complete projected payload can still fail the existing byte cap.

The production PostgreSQL read explicitly selects these columns and builds the
projection before measuring or returning the JSON body. It never selects `result`
in that payload CTE. Candidate ordering, connected groups, correction edges,
N/C/K, scope filters, row/byte/trip/member/state limits and deadlines are unchanged.
Required-field or malformed projection validation remains fail-closed.

`HistorySource.acceptance` also reads legacy full Acceptance for frozen in-memory
and serialized evaluation callers. Production SQL only emits the compact type;
the compact type rejects extra result/evidence/geometry fields. Legacy data is
neither rewritten nor silently discarded. At Acceptance, a compact caller source
is compared field-for-field to a projection of the durable Acceptance; legacy
callers retain the existing full comparison. A missing or mismatching source still
raises `interpretation_durable_provenance_conflict`.

No migration or public API change. Stored accepted results, failed/UNKNOWN Runs,
provider grants, interpretation wire fix, prompts and current-evidence validation
are unchanged. History remains contextual intent, not factual authority.

## Alternatives and validation

Raising MAX_BYTES, silently truncating JSON, retaining just recent answers, or
rewriting accepted data are rejected. An optional answer summary has no consumer
and would introduce new interpretation semantics, so none is included.

Tests cover the actual large Citation/boxes shape with an original isolated fixture,
identity/scope/state preservation, missing fields, extra heavy fields, multi-row
byte overflow, deterministic reads, legacy receipts and forged projected provenance
at commit. Existing history and reliability suites are retained. The large fixture
is inserted during test setup, not an update to an immutable accepted row; it is
not a demonstration of the physical validator accepting duplicate geometry.

Read-only execution over the real accepted row now returns 1,371 bytes with all
persisted Acceptance bytes unchanged. This establishes the size fix, not multi-turn
quality. The default query still has no resolved relevance signals or explicit
source and the accepted head has no State entries. Recent A alone remains
`no_active_relevance`; interpretation consequently receives empty history/state.
Providing an automatic semantic candidate-selection path is a separate decision.
The projection does not invent that relevance, force the head into selected history,
retroactively populate old state, or treat its prior answer as evidence.
