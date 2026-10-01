# Migration 0012 revision — Human review packet

Status: **V02A_0012_REVISED_READY_FOR_HUMAN_REVIEW** · 2026-10-01.
Schema/ADR acceptance remains PENDING. Provider/model/Judge calls and monetary
authority for this revision are zero. Paid DEV remains blocked; #5d NOT_STARTED.

Historical reviewed candidate: commit
`4cd7390ee7ed7e5e8b0dea3491de1444b4bcfd9c`, tree
`8c464205299cfbfbb3a14fd81d4af229b09fb549`. It is preserved unchanged in Git;
its ignored candidate/environment/contracts receipts are not overwritten.
The revised local commit/tree are recorded after commit in the separate ignored
`.runtime/evaluation/0012-revision/candidate.json` and final delivery, avoiding
embedding a commit's own identity in its tracked contents.

## Exact delta

- [Unaccepted 0012](../migrations/versions/0012_dev_campaign_envelope.py) is revised
  in place. No 0013, new table/column/index/FK or backfill beyond the reviewed
  nine-column cw6_dev_campaigns definition; no old data rewrite.
- Three DEV functions are revised. Their three row triggers now cover
  INSERT/UPDATE/DELETE; three statement TRUNCATE guards are added. Shared-table
  TRUNCATE intentionally fails while a DEV campaign exists. Ordinary non-DEV
  row workflows retain their prior rules; DDL lock/performance costs are unmeasured.
- OLD/NEW membership protects phase/case UPDATE. Ownership rebinding and adoption
  of existing non-DEV rows are rejected; admission is validated fresh INSERT.
  Campaign INSERT rejects retroactive case/phase adoption; create flushes the
  envelope before its cases.
- Reservation identity, including logical_key/reserved_at/created_at, freezes.
  Phase: PREPARED→DISPATCHED/REJECTED; DISPATCHED→COMPLETED/UNKNOWN/REJECTED.
  dispatched_at is set once at dispatch. COMPLETED requires known/result hash;
  UNKNOWN requires unknown; REJECTED requires known_not_executed. Final receipt
  observations can be written atomically at terminal transition, then the whole
  row freezes. Exact no-ops are permitted; same-state fact edits are rejected.
- Case: PENDING/attempt0/fence0/max1→RUNNING/attempt1/fence1→
  COMPLETED/FAILED/OUTCOME_UNKNOWN. Identity/max-attempt cannot change; running
  owner/fence/attempt/start/deadline cannot reset; terminal whole row freezes.
- Campaign starts DISABLED/SYNTHETIC/ACTIVE according to policy; only
  ACTIVE/SYNTHETIC→STOPPED/COMPLETE. Frozen policy/hash/expiry/deadline stay frozen;
  review can continue after spending closes.
- Campaign, DEV phase and DEV case DELETE are rejected. Committed reservations
  remain permanent in all outcomes. Transaction rollback does not execute DELETE
  triggers: never committed means no durable reservation existed. prepare rolls
  back its failed post-flush INSERT via savepoint, then persists the stop outside
  that savepoint; it no longer calls db.delete(phase).
- ORM declares the DDL review server default as well as its Python default.
  Alembic reflection includes cw6. The dedicated audit compares types/nullability/
  defaults/PK/FK/check/index and all persisted DEV function/trigger definitions.

[ADR0012](adr/0012-dev-campaign-settlement.md) enumerates every actual phase column
by lifecycle and records EvalRun JSON + row-locking as a feasible application-level
alternative. DB-enforced immutability/retention still needs additional DDL or a
different restricted-write boundary. The envelope is a chosen separation, not
the only possible implementation. State-only settlement itself needs no new table.

## Fresh evidence

[Direct SQL regression module](../tests/test_v02_dev_migration_0012.py): **94 cases**
cover ownership nulling/moving, INSERT validation, reservation identity, allowed/
invalid transitions, terminal receipts, DELETE/TRUNCATE, case attempts/identity,
rollback, permanent budget, recovery, non-DEV compatibility, status/policy guards
and schema audit. Existing campaign tests cover both State-only A targets,
UNKNOWN/global stop, five budgets, cancel/expiry, fencing and synthetic/zero grant.

- Fresh disposable DB starts at **0011** with original synthetic non-DEV Run/Case/
  Phase rows. Revised0012 preserves them; two migrate-to-head calls succeed.
  Unsupported downgrade raises and leaves head0012. Server-default metadata
  comparison is clean; all three function bodies and six trigger definitions
  are audited. A separate fresh schema receipt captures their complete definitions.
- Migration/campaign/Core/provider/budget/runtime PG regression: **211 passed,
  0 failed, 0 skipped** (38.93s), including the 94 new cases. Results overlap.
- Full release: **443 backend passed/322 integration deselected**, **41 frontend
  passed/5 files**. Ruff lint/format233 files, OpenAPI/generated TS, frontend lint/
  typecheck/build pass. Two existing Python deprecations and Vite >500kB warning
  remain; deselected tests are not passing tests.
- Read-only audit rechecks **7/7** historical PG READY/PUBLISHED bindings, original
  PDF/canonical blobs/tree/membership hashes, exact Qdrant children/payloads and
  saved physical citations. App DB remains **0005/28 versions**, with **zero of
  the seven frozen DEV versions**, before/after. Verification scripts prohibit
  model/provider constructors. All generated test databases are dropped.

Ignored evidence is under `.runtime/evaluation/0012-revision/`: fresh-schema.json,
persisted-bindings.json and post-commit candidate.json. The old corpus DB and its
old0012 functions are retained unchanged, NOT used as revised schema proof or a
revised paid runtime. No re-ingestion, model inference or fresh retrieval was run.
Physical citations do not establish semantic support/quality. Future execution
must first prepare an explicitly approved revised-schema runtime and rebind the
candidate/environment. Old zero-authority receipts cannot become a Human grant.

Development failures are not counted PASS: initial PL/pgSQL CASE syntax caused96
setup errors; result conversion, guard/error expectations, JSON bind handling
and SQL-vs-JSON-null handling were corrected before the final suites. Binding
audit corrected an assertion confusing zero frozen DEV versions with zero total
app versions; no database changes were used to satisfy it.

## Human boundary

| Concern | Evidence | Remaining risk / decision boundary |
| --- | --- | --- |
| DB invariants | SQL counterexamples, fresh definitions/metadata | Ready for review; not schema acceptance |
| Product/non-DEV | Populated0011 preservation/product PG regression | Shared lookups and deliberate TRUNCATE restriction |
| State-only | Existing zero Acceptance/head regression | Physical validity is not semantic support |
| Rollback | Pre-commit reservation rollback tested | No downgrade; no kill/restart, interrupted-DDL or backup-restore proof |
| Old0012 DB | Read-only binding audit | Head alone cannot distinguish definitions; do not silently reuse |
| Authorization | No Human grant; disabled/synthetic guards unchanged | Schema acceptance is separate from monetary/provider permission |

Scope is only migration/ADR0012 for isolated DEV. No application/other environment
migration, provider/model/Judge/spending, #5d, push/PR/merge/release is authorized.
Fix-forward/no downgrade remains explicit. Stop at Human review.
