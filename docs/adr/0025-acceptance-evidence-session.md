# ADR0025 — reuse the Acceptance session for immutable evidence reads

Status: Owner-authorized M3 experiment; candidate for Human Implementation Review,
not marked ACCEPTED. 2026-10-03.

## Problem and measured trigger

The frozen local Conversation benchmark holds the existing source/authorization
locks through atomic Acceptance. `validate_durable_result(db, ...)` currently
creates a StructuralRepository whose builds/atoms/children methods open separate
transactions. With the default six-connection pool, competing requests can hold
all connections while the lock owner needs another connection to finish its
validation. Pool timeouts cannot release the locked transaction before its own
timeout, and fail-safe runtime bookkeeping can require still more connections.
The real HTTP/PG baseline first exposes this failure at concurrency10; concurrency5
already shows source-lock serialization. This is pool starvation from recursive
borrowing, not evidence of provider/model latency or insufficient infrastructure.

## Bounded decision

Give StructuralRepository and `citation_for` an optional caller-owned SQLAlchemy
Session. Their read contexts use that Session without beginning, committing, rolling back or closing
it; the caller owns all transaction lifecycle. Existing retrieval consumers omit
the Session and retain their independent short transactions. Only durable
Conversation Acceptance validation supplies its existing `db` Session to both
structural and citation reads. No cache,
global Session, raw-output recovery or cross-request connection reuse is added.

All existing structural build/profile/source checks, child/parent membership,
exact atom/span resolution, citation binding, scope/current-version locks,
Interpretation/Acceptance checks and final-flush DB deadline remain in place.
Acceptance validation requires one checked-out connection instead of recursively
borrowing a second while holding source locks. This also keeps those validation
reads within the caller's transaction; it does not weaken durable authority.

This Session-reuse change does not change lock modes. The subsequent separately
measured scope-reader optimization is documented in [ADR0026](0026-shared-conversation-scope-readers.md).
Provider markers, finite attempts, UNKNOWN no-redispatch, cancellation/fence,
recovery and atomic publication semantics are unchanged. Event recording remains
enabled and durable. No Pydantic/OpenAPI, schema or migration change is needed;
Alembic0014 remains the unique head. Applying the change has no data migration or
historic-row impact. Rollback restores the source behavior without schema work.

## Alternatives and residual limits

Increasing the pool masks recursive borrowing and creates more source-lock
waiters; it does not remove the dependency. Disabling source checks or events
changes correctness/durability and is rejected. Moving validation before the
Acceptance transaction leaves an authorization/scope race and is rejected.
Sharing Sessions globally violates per-request lifecycle and is rejected.
Changing scope locks to shared reads addresses a separate serialization cost,
with its own race proofs and measurement in ADR0026; it is not part
of this Session-reuse experiment. Redis/Celery/monitoring infrastructure does not solve the
transaction dependency and is not added.

The six-connection pool still bounds concurrent DB work. Source locks and frequent
durable SQL/event transactions can still limit throughput after the dependency is
removed. That residual performance is measured rather than assigned a target.
The repository's legacy QueryRun path retains its existing transaction behavior;
M3 concerns the active Conversation Acceptance path only.

## Verification contract

A focused real-PG regression accepts a fully validated documentary result with
pool_size1/max_overflow0; a second regression occupies all six slots before
parallel Acceptance. Both failed before the change. The first repository-only
experiment still failed both because `citation_for` also opened a transaction;
that failed31-case focused receipt is retained. Completing Session propagation
to citation reads passed31/31, including both regressions and durable identity
readback. Existing M1/M2 physical identity,
scope, atomic rollback, final-flush deadline, cancellation, retry, UNKNOWN and
worker-loss/recovery regressions must pass. Keep the optimization only if the
same frozen Profile A/harness demonstrates a defensible improvement with no
correctness failure. Local synthetic and real-Qdrant-with-fake-model boundaries
remain explicit in [M3](../V02B_CONCURRENCY_PERFORMANCE_M3.md).
