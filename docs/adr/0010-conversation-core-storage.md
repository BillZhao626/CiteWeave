# ADR 0010: bounded conversation-core storage representation

Status: **IMPLEMENTATION RECORD — Human Implementation Review pending** · 2026-09-29

## Authority and scope

This records the schema/transaction choices implementing accepted [ADR 0006](0006-conversation-state-and-effective-commit.md) and [ADR 0009](0009-conversation-profile-and-trace.md), under the Product Owner's separate Implementation #1 authorization. It does not amend their semantics or accept a new product architecture. The [Feature](../specs/07_V02_First_Conversational_Slice.md) remains a larger, incomplete slice.

Blueprint drift check against the baseline accepted through PR #1: this change supplies durable conversation identity and effective acceptance for later technical follow-up. PostgreSQL remains authority; documentary scope and source identities remain separate from text. No history selection, Relevance-first policy, prompts, ranking, EvidencePack, provider, infrastructure or retention policy changes. Synthetic control payloads cannot demonstrate conversational quality.

## Representation and alternatives

Four additive `cw5_` tables retain Conversation, immutable Turn request, related Run attempts and immutable acceptance bundles. The bundle ID is simultaneously the accepted result ID, output snapshot ID and Conversation head. Its minimal state contains only the source Turn and predecessor snapshot; it makes no semantic projection. A Turn's expected head is also its immutable input snapshot identity, inherited by all its Runs. Scope captures one explicit KB and a canonical nonempty set of immutable document-version IDs using the existing workspace boundary.

| Choice | Reason / alternative |
| --- | --- |
| Result and output state in one acceptance row | They have one lifecycle in this core. Separate result/state tables would add independently addressable intermediate combinations without a current requirement. A future split must retain bundle identity and atomic publication. |
| Conversation row lock and monotonic fence; partial unique active-Run index | Serializes admission, finalization, cancellation and explicit reconciliation. No Redis lock, queue, distributed lease or event-sourcing framework. |
| Unique Turn acceptance and composite same-Conversation foreign keys | PostgreSQL rejects duplicate effective identity and cross-Conversation head/Turn/Run links. Application guards additionally check authorization, head, owner, fence, deadline and state provenance. |
| Separate core Run receipts; unchanged legacy QueryRun | Existing QueryRun is a documentary execution/answer record with its own reader/cost/evidence assumptions. Fabricating such a record for a pending core/control operation would pretend those stages ran. No legacy backfill, optional documentary execution linkage or new v0.1 fields are needed until separately authorized Evidence integration. |
| Internal Pydantic DTOs and service operations only | A public intermediate finalize endpoint would expose an unsafe incomplete path. No API routes, OpenAPI or frontend changes. |

`conversation-core-v1` is a persistence revision, not a runnable conversation/model profile. It has no provider identity, token budget or execution authorization. Each admission requires an explicit owner and timezone-aware absolute deadline; no pending empirical product limit is silently filled in. The owner/deadline are server execution inputs, excluded from the user-intent fingerprint: replay observes the original ownership/deadline, never extends or transfers it.

## Transactions and recovery

Every service call opens a short transaction; commands and multi-query readback lock the Conversation first. Scope checks lock the existing KB and document/version rows through the transaction. Admission checks exact request fingerprint before checking a moved head or active slot, so response loss can recover the original operation. Same key with changed intent conflicts. New independent requests conflict on stale head or busy state; they never queue/rebase. Explicit retry has its own operation key, a parent Run and a unique successor; it requires the original head/current scope, an unaccepted Turn, no active Run and a known retryable terminal predecessor.

Run states are ADMITTED, ACCEPTED, FAILED, CANCELLED, INTERRUPTED, UNKNOWN and STALE. ADMITTED owns the slot. Terminal rows do not reopen. Acceptance inserts the result/state bundle, advances head, closes the Run and increments the fence in one transaction. Duplicate acceptance is an explicit conflict; readback resolves a lost commit receipt. Late cleanup cannot release a newer owner's slot. Deadline checking rejects acceptance; a still-current owner can record a non-accepted outcome after expiry, including UNKNOWN.

Readback returns current head, active Run, original request, requested attempt and the Turn's accepted outcome if any. It never dispatches. Explicit `reconcile_expired` inspects at most the single active Run and fences only an elapsed DB-clock deadline; it never treats connection loss as proof of owner death. It is idempotent and produces INTERRUPTED, with no automatic continuation/startup scan. UNKNOWN cannot retry through this core. There is no provider dispatch here; future provider integration must persist dispatch/unknown accounting before enabling execution, and must not reinterpret INTERRUPTED as a known provider failure.

The acceptance boundary supports already-produced clarification/evidence-insufficient control text only. It does not validate semantic support or implement clarification policy. Documentary answer input is rejected until Citation/EvidencePack integration exists. No accepted semantic state is inferred from the control text.

## Migration, validation and limits

Alembic `0009` follows `0008`, creates only four new tables/indexes/FKs and registers their metadata. It does not update v0.1 data or rewrite historical migrations. Downgrade explicitly refuses destructive history removal; use a reviewed forward fix or a matching PostgreSQL/blob backup restoration. No TTL/deletion is introduced.

Offline tests exercise transition guards, exact fingerprint/scope normalization, DTO validation, stale/duplicate acceptance, admission replay/conflicts, transaction error propagation and PostgreSQL DDL compilation. The real-PG module creates a UUID-named database, upgrades to `0008`, writes original synthetic v0.1 metadata/Run, upgrades to `0009` twice, compares its reader and schema, and tests races, visibility, rollback and receipt readback. It never migrates the configured application database or uses Qdrant/Redis/providers. Rollback/restore of a real PG/blob backup remains unverified.

Real PostgreSQL L1 is **VERIFIED: 12 passed, 0 failed, 0 skipped** on 2026-09-29 against implementation `3c76e492c85473291c6e54720fdd34c9f103e5e9`, with no code changes needed. Under separate verification authorization, only the existing Compose-owned `citeweave-m0-postgres-1` was started (PostgreSQL 18.1, loopback port 15432, account/application database `citeweave`). The module created and cleaned its own UUID-named database; no configured application database migration was performed. The earlier NOT_RUN was an environment limitation, not a test failure. Offline core tests were rerun: 69 passed. These real-PG results cover the synthetic isolated database and controlled race/fault scenarios only; application-data upgrade, PG/blob backup restoration, provider/runtime behavior and production reliability remain **NOT VERIFIED**. No provider/model/Judge calls or DEV/HARD/REG execution occurred. Current evidence and commands are in [HANDOFF](../../HANDOFF.md); v0.2a remains incomplete.
