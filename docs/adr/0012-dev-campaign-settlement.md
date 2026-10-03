# ADR 0012: One bounded DEV campaign and State-only evaluation settlement

Status: **IMPLEMENTATION RECORD — revised, Human Review pending** · 2026-10-01.

The reviewed candidate `4cd7390ee7ed7e5e8b0dea3491de1444b4bcfd9c`
(tree `8c464205299cfbfbb3a14fd81d4af229b09fb549`) remains historical evidence.
Its 0012 was not accepted. The separately authorized provider-free revision
repairs that unaccepted migration in place; it adds no 0013 and no execution
authority. Fresh migration evidence must start from 0011 in a disposable DB;
an old DB reporting head0012 does not prove it contains these revised functions.

The requested accepted database head is 0011. Compatibility tests do not accept
this additional 0012 schema. Current delivery is REMEDIATION_BLOCKED at that
explicit boundary; a future HUMAN policy must separately bind schema acceptance
identity and timestamp. Money/account confirmation alone cannot bypass it.

The Product Owner's Minimal Paid DEV Remediation request authorizes provider-free implementation after BLOCKED checkpoint 5c80f0f. It authorizes neither provider execution nor spending. This is one frozen DEV campaign, not #5d or general production readiness. Gold, prompts, ranking, evidence and product Acceptance semantics remain unchanged.

State-only A D1.V2/D3.V1 intentionally omit older raw Turns. Current bounded State may resolve evaluation intent; product Acceptance still requires its existing provenance contract. Weakening that guard, fabricating raw history or marking a known completed phase UNKNOWN would misrepresent business truth. These targets use the existing cw2_eval_cases terminal/result with EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED; no target product Run, Acceptance or head/state update. Ordinary targets retain the product acceptance adapter. Manual fixed-prefix seeds remain separately identified, not generated technical answers.

One additive 0011→0012 Alembic migration adds cw6_dev_campaigns, an immutable finite permission envelope and prospective review accounting. cw4_provider_phases remains the sole call ledger. Each DEV phase has only evaluation ownership, owner/fence, request hash, accounting/rate identity, exact input count, output reservation, Decimal CNY, expiry, attempt=1 and unique logical stage. New triggers apply only to these campaigns. Existing Query/Conversation ownership and guards remain valid. Fix forward; no destructive downgrade. The configured application DB is untouched: the isolated DEV DB was ingested at 0011 and receives 0012 only for this seam.

0011 supplies per-product-Run authorization, not a database-enforced shared DEV
envelope. Its existing EvalRun JSON, deadlines and EvalCase results could hold
the same concepts: EvalRun JSON + EvalRun row locking + phase aggregation is a
viable application-enforced alternative. Database enforcement of immutable
policy, ownership, receipts and retention would still require additional DDL
or a different restricted-write boundary. The small dedicated table was selected
to separate this one campaign's policy/status/review from legacy retry-oriented
EvalRun semantics while retaining the existing sole call ledger. This is not
the only theoretically possible implementation. State-only settlement already
fits EvalCase.result and is not itself a reason to require a new table. Hash,
expiry/deadline columns intentionally duplicate frozen policy facts for explicit
inspection; their correctness is checked by the application. Schema acceptance
identity/timestamp are in policy JSON, independently of a monetary grant.

Phase INSERT validates NEW DEV ownership and requires an initial PREPARED row,
attempt1, exact logical case/stage key, exclusively evaluation ownership and
non-null accounting identities/positive reservations. UPDATE checks BOTH OLD
and NEW campaign membership. Reservation identity is immutable from creation;
ownership rebinding, including adoption of an existing non-DEV phase into DEV,
is rejected. Fresh insertion is the only admission across that boundary.
Campaign insertion also rejects retroactive adoption of existing cases/phases;
create() flushes the envelope before inserting its cases.

All 32 current ProviderPhase columns have an explicit lifecycle:

| Lifecycle | Actual columns |
| --- | --- |
| Immutable reservation identity from INSERT | id, eval_run_id, case_id, query_run_id, conversation_run_id, logical_key, phase, phase_attempt, owner, fence, authorization_id, authorization_deadline, provider, model, price_revision, prompt_revision, request_hash, input_tokens, output_tokens, reserved_yuan, reserved_at, created_at |
| Transition facts | state, outcome, dispatched_at, updated_at |
| Final receipt observations, written atomically on terminal transition | request_id, usage, estimated_yuan, result_hash, result, error_code |

There are no separate observed-provider/model columns in this table; provider
and model bind reservation identity, while request_id/usage/result carry the
available receipt observations. SQL NULL and JSON null both denote absent
JSON observations before dispatch. The phase state machine permits
PREPARED→DISPATCHED/REJECTED and DISPATCHED→COMPLETED/UNKNOWN/REJECTED.
REJECTED means known_not_executed, UNKNOWN means unknown, and COMPLETED means
known with a result hash. dispatched_at is set only on PREPARED→DISPATCHED and
cannot subsequently change. Same-state fact edits are rejected; exact no-ops
are allowed. Every terminal row (COMPLETED/UNKNOWN/REJECTED) is frozen WHOLE-ROW,
including timestamps, observations, identity and any future columns. There is
no late correction UPDATE; review/fix-forward must retain the original receipt.

DEV EvalCase starts PENDING/attempt0/fence0/max_attempts1, then becomes
RUNNING/attempt1/fence1 with owner/start/deadline, then
COMPLETED/FAILED/OUTCOME_UNKNOWN. Identity/max_attempts cannot change; running
owner/fence/attempt/start/deadline cannot reset; terminal receipts freeze the
whole row. Campaign starts DISABLED/SYNTHETIC/ACTIVE according to policy mode;
ACTIVE or SYNTHETIC may move only to STOPPED or COMPLETE. DISABLED, STOPPED and
COMPLETE cannot transition to another status. Review updates remain permitted
after spending closes; the policy/hash/expiry/deadline stay frozen.

Retention is deliberate: campaign DELETE is rejected; DEV phase and case
DELETE are rejected even before terminal state. Same-ID deletion/reconstruction
cannot reset authority, reservations or attempts. Statement TRUNCATE guards
also reject shared-table truncation while a DEV campaign exists. Ordinary
non-DEV row INSERT/UPDATE/DELETE retains its prior behavior. Transaction ROLLBACK
does not execute DELETE triggers: never committed means no durable reservation
existed. prepare() uses a savepoint for its INSERT/post-flush deadline check,
rolls back the never-committed phase on failure, then persists the stop outside
that savepoint. A committed reservation is permanent in every terminal outcome.

These are shared-table trigger additions, including small conditional lookups
on ordinary writes. CREATE TRIGGER takes DDL locks that can block shared-table
writes; no lock-duration/performance guarantee is claimed. 0012 is currently
required only for the isolated DEV evaluation, not a global product upgrade.
Generic Alembic upgrade-to-head is not a DB-name authorization boundary; only
the dedicated DEV entry point binds the intended database. Acceptance of this
schema/ADR would authorize neither the application DB nor unrelated environments,
provider execution or spending. downgrade() intentionally raises before any
reverse DDL: fix-forward, no supported downgrade or independently proven backup
restore/interrupted-upgrade safety. Privileged DDL/trigger disabling is outside
these ordinary-DML invariants.

The campaign row lock serializes target admission, phase reservation and dispatch. Five aggregate dimensions consume permanent reservations; charges never release allowances. Exact case/stage membership caps execution at 38: 15 interpretation and 23 generation. A guard and four self-contained views remove ten protocol slots before transport; conditional D4 generation slots remain. No other case/repeat/retry/repair/refetch/Judge can reuse a skip. Complete bodies are reserialized/tokenized at PREPARED and before DISPATCHED. The latter commits before the provider's sole POST. Real transport requires the durable row's HUMAN mode, positive finite grant and confirmed account fields; a caller object or SYNTHETIC marker cannot grant I/O.

UNKNOWN, expired dispatched phases, deadline or cancellation prevent another send, preserving reservations and partial observations. Known completion stores response hash/usage and bounded evaluation response atomically. A known target may close after cancellation/deadline without falsely becoming UNKNOWN or enabling another call. Same-key terminal readback returns its immutable receipt. Unfinished targets are not retried; expired dispatch reconciles to UNKNOWN on guarded entry. No background spending worker, automatic resume or budget increase exists.

The real launcher constructs RealDevBackend, StructuralEvidenceRetriever(ModelGateway()) and the existing one-attempt DeepSeek adapter directly, without fixture repository/provider-factory parameters. It verifies clean commit/tree, Gold/PDF/config/prompts/protocol/tokenizer/rate and published real indexes. Preparation only uses local E5/BGE/Qdrant and a zero grant. Complete results close spending before Human review: 24 mandatory OUTPUT, at most12 DISPUTE, 288 future minutes. Historical Gold minutes remain NOT_MEASURED. Review completion is not promotion or a winner.

Alternatives rejected: a second call ledger duplicates accounting; changing product Acceptance violates accepted semantics; UNKNOWN for known completion falsifies outcome; the old retry-capable Eval broker cannot enforce this one-attempt envelope; memory/env-only caps can grow after restart. A small evaluation-only policy table and terminal seam preserve existing durable authorities with no new infrastructure or product API.

Validation and exact candidate/environment identities are in [the authorization packet](../V02_DEV_PAID_EXECUTION_AUTHORIZATION.md). Synthetic zero-grant tests verify mechanics, not billing or semantic support. Real local ingestion/retrieval verifies infrastructure and physical citations, not quality. No external provider/Judge/account API occurs here.
