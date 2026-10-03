# ADR0026 — shared locks for read-only Conversation scope guards

Status: Owner-authorized M3 experiment, candidate for Human Implementation Review;
not marked ACCEPTED. 2026-10-03.

The frozen same-KB workload showed exclusive source-row serialization at
concurrency5. ADR0025 removed recursive borrowing and passed the constrained-pool
regressions, but its complete Profile A sweep still had6/120 failures at
concurrency20 before generation. Receipts retain pool acquisition wait, PG source
lock waiters and the existing binding deadline failures. Increasing timeouts or
removing guards would change the benchmark/correctness contract and is rejected.

Conversation scope checks are read-only. Retain the exclusive Conversation lock
and all owner/head/fence/status/deadline and current-version checks. Acquire
`FOR SHARE` on the authorized KB and joined Document/DocumentVersion rows in the
existing KB→document→version order and hold through the same transaction commit.
These locks permit independent readers while still conflicting with non-key
UPDATE, DELETE and exclusive writer locks. This is not `FOR KEY SHARE`, which
would permit some protected non-key changes. No `SKIP LOCKED`, lock elision,
snapshot cache or optimistic stale source permission is introduced.

`authorized_kb(..., lock=True, shared=True)` is explicit only at Conversation
`_scope`. Its default and all existing catalog mutation consumers keep exclusive
locks. The Conversation slot and idempotency mutex remain unchanged. Only the
compatibility between independent readers of the same authorized immutable
source changes; authorization/current source stability remains protected.

Focused real-PG tests first failed reader overlap under exclusive locks while
six writer-order tests already passed. After the change, all7 passed: both
readers can hold scope locks at once; non-key workspace reassignment, active
DocumentVersion switch and Version readiness changes wait until reader commit;
when each writer wins first, the waiting reader rechecks and rejects the changed
scope after commit. Tests observe actual `pg_stat_activity` lock waits rather
than guessing from thread timing. Combined pool/evidence/runtime tests38 passed.
Existing full M1/M2 gates additionally verify cancellation, publication deadline,
immutable citation identity, scope revocation and concurrent idempotency.

Alternatives: a larger connection pool leaves the source mutex and transaction
dependency; looser binding/history deadlines disguise queueing; removing scope
locks permits revocation/publication races; caching source authorization can be
stale. All rejected. No broker, monitoring platform or model/ranking tuning.

There is no schema, migration or OpenAPI change; Alembic0014 remains authoritative.
Rollback restores the former exclusive read guard without altering data. The
same frozen v2 harness must measure this second candidate separately from the
preserved ADR0025-only receipts. `scope_sql_ms` in that harness denotes only
exclusive scope SELECT cursor time, so its disappearance alone is not a speed
claim; total SQL/pool/workflow measurements include shared-lock work. Local
results and residual limits are recorded in [M3](../V02B_CONCURRENCY_PERFORMANCE_M3.md).
