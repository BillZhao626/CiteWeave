# ADR 0031 — Read-only publication and reliability inspection

Status: implemented locally; runtime and schema semantics unchanged.

## Context

The existing Conversation API returns accepted answers and safe Trace, but cannot browse Runs or show a Working State summary beside its official answer. Separate head and Run requests can also describe different observation times.

## Decision

Add authenticated read-only Run catalog and inspection endpoints. The catalog selects at most 25 workspace-owned identities in durable creation order, then reuses the existing core reader for every selected Run. Fixed document-version and conversation authorization remain mandatory; an unavailable scope fails closed. A catalog page is a sequence of observations, not a cross-conversation snapshot.

Each detail projection uses one existing core readback under its Conversation lock. Publication requires the same Run to be ACCEPTED and to own the Acceptance. Its answer and state share that immutable Acceptance identity. The current head is shown separately: a historical Acceptance remains published when a later Turn advances the head. A failed attempt never inherits a successful retry's bundle. State summaries expose provenance, persisted topic signal and entry counts; legacy snapshots report absent fields as null.

Reliability decisions and reasons come from the existing OperationalTrace projection. UNKNOWN blocks automatic redispatch even when a provider response was observed but a later local failure prevented Acceptance. The UI must distinguish that case from an uncertain provider transport. Recorded events are shown with their real timestamps; absent events are never reconstructed. Default selection prefers an existing ACCEPTED Run; non-accepted catalog rows summarize reasons and publication/redispatch metadata while retaining access to their complete detail. This surface grants no retry, cancellation, reconciliation or execution authority.

## Alternatives

Combining existing frontend requests avoids an endpoint but cannot expose state summaries and may mix head observations. A new dashboard or receipt importer duplicates product state and could misrepresent historical failures. Full raw state/provider exports would expose unrelated payloads. The small allowlisted projection fits the existing developer workspace.

## Migration and validation

No Alembic migration, state write, provider call or backfill. Pydantic/OpenAPI generates frontend contracts. Targeted PostgreSQL tests verify ownership and version scope, unchanged durable facts, current versus historical head, and failed-attempt/retry identity. Frontend tests cover UNKNOWN reason distinctions, missing events, legacy state and unpublished results. Real local API/database comparisons and browser captures use existing records; no screenshot-driven failure scenarios.
