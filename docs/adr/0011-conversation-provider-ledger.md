# ADR 0011: Conversation ownership of the existing provider ledger

Status: **IMPLEMENTATION RECORD — Human Implementation Review pending** · 2026-09-30

## Authority and problem

The Product Owner's #5c-1 Human Review authorizes one additive ledger/recovery increment after the production-runtime accounting stop. Accepted baseline is `3502981`. This implements the durable dispatch/UNKNOWN requirement in [ADR 0010](0010-conversation-core-storage.md) and accounting identity in [ADR 0009](0009-conversation-profile-and-trace.md). It does not authorize production runtime wiring, new API behavior, model execution or spending. It preserves the Blueprint's PG authority, existing adapters and immutable evidence boundaries.

The existing provider ledger belongs to QueryRun/Eval. Conversation acceptance JSON only exists after a successful atomic acceptance, so it cannot retain pre-dispatch reservations or uncertain calls after a crash. Expiry previously produced INTERRUPTED without inspecting provider state, which was valid while Conversation could not dispatch.

## Representation and alternatives

Extend `cw4_provider_phases`; do not create another ledger or fabricate a legacy QueryRun. Migration `0010` adds nullable `conversation_run_id` referencing `cw5_runs`, `provider`, `model`, `price_revision`, `authorization_id`, `authorization_deadline`, `input_tokens`, `output_tokens`, `prompt_revision`, and `request_hash`. No workspace/Turn duplication: both derive through the Run.

Reuse `phase`, `phase_attempt`, `logical_key`, owner/fence, reserved amount/time, dispatch timestamp, state/outcome, request ID, usage, estimated cost, result hash and error code. The Conversation adapter records only result identity; it does not store provider text or expose ledger internals through public Trace. `ProviderEventRow` and legacy retained-result behavior remain unchanged.

Conversation rows must have no QueryRun, Eval or case ownership. Legacy query-only, eval-only and eval+query shapes remain valid. Conditional constraints require explicit non-null Conversation call identity/capacity. A Conversation Run has at most one row per interpretation/generation purpose, attempt 1, and an authorization ID identifies exactly one call. There is no in-Run resend; a known safe failure can use the existing explicit new-Run retry. The legacy two-attempt policy is unchanged.

An immutable-identity trigger prevents reassigning ownership, reservation, prompt/request or pricing identity, including retroactively converting legacy rows into Conversation rows. Legacy ownership transfer is unchanged. Typed internal Pydantic inputs validate hashes, supported provider/model/rate revision, finite positive decimal limits, integer token limits and aware deadlines. There is no untyped authorization JSON or default `0.10` reservation/`1024` output grant.

Alternatives rejected: a second ledger duplicates accounting/recovery; accounting on `cw5_runs` duplicates the phase lifecycle; acceptance-only storage loses non-accepted work; unbound IDs in generic event JSON cannot enforce Run ownership; invented QueryRuns misrepresent documentary execution. Scalar additive columns retain legacy reader compatibility without an owner union schema rewrite.

## Transitions, fencing and recovery

All Conversation adapter operations lock Conversation first, authorize workspace/current document scope, require the original head and current owner/fence/status, and check the PG deadline. Mutations flush and recheck before commit. A phase's authorization deadline cannot exceed its Run deadline. Phase IDs are matched to the supplied Run, never merely trusted from a caller. Legacy mutation helpers explicitly reject Conversation phases.

PREPARED durably reserves a caller-supplied authorization for one call. `dispatch` commits DISPATCHED/unknown before a future transport may send; repeated dispatch fails closed. Receipt readback is not permission to send again. COMPLETED/known records a response hash and any reported usage/request ID. REJECTED/known_not_executed records either local pre-dispatch validation failure or a direct non-execution observation from the gateway's existing allowlist. Timeout/response loss is UNKNOWN, never inferred rejection. UNKNOWN retains its reservation and any partial observation, and prevents dispatch of another prepared phase in that Run. No automatic retry or provider reconciliation is introduced.

| Durable facts at expiry | Run outcome / normal retry |
| --- | --- |
| No dispatched phase, or only directly proven non-execution rejection | INTERRUPTED; explicit retry may proceed under existing scope/head rules |
| DISPATCHED or UNKNOWN without a trustworthy safe outcome | UNKNOWN; normal retry forbidden |
| COMPLETED provider response but no Acceptance | UNKNOWN conservatively; a new paid call is not authorized by successful transport |
| Accepted bundle | ACCEPTED remains authoritative; expiry is a no-op |

Reconciliation updates unresolved DISPATCHED phases and the Run atomically under the same Conversation lock, retaining completed receipts. `finish` cannot hide a possibly executed call under a normally retryable terminal status. Acceptance rejects unresolved phases but retains all existing citation, provenance, owner/head/fence/deadline checks. Receipt loss is recovered by reading PG; this is not exactly-once external execution. No same-response replay/acceptance recovery worker is added.

## Accounting and execution boundary

Each internal authorization supplies the exact Run/purpose, provider/model, price revision, prompt revision, request hash, input/output caps, maximum CNY reservation and expiry. There are no production issuers or caller-facing authorization inputs in this increment. Synthetic positive test grants prove persistence only; current real authority is **0 calls / 0 CNY**. Policy issuance, request-token validation, aggregation across calls/Runs/Conversation/month, balances and the future side-effect boundary remain #5c-2 work. A ledger row is not a spending approval.

Usage is an allowlisted set of strict nonnegative provider-reported integer counts; partial/missing usage remains partial/missing. Known usage, including over-budget observations, is preserved rather than truncated. `costs.py` remains the single price implementation. The pinned rate revision plus durable dispatch timestamp determine its time-sensitive estimate. If the revision is unavailable, cost remains unavailable; no current rate is silently substituted. Estimated CNY is not actual provider billing. This increment does not validate current official prices, model capacity or a production token envelope.

## Migration and verification

One additive `0009 → 0010` migration; historical migrations are unchanged and old rows receive nullable fields without fabricated identity. No destructive downgrade: use a forward fix or reviewed matching backup. The existing `0008` Eval composite FK and attempt check are now included in ORM metadata, without modifying their database semantics.

Tests create/drop UUID-isolated local PG databases. Populated `0009` query-only/eval-only/combined phase shapes and an existing Conversation Run survive upgrade and repeat upgrade. Constraint checks assert the actual rejected constraint, and ORM comparison checks the changed tables. Legacy Eval/provider tests run through an isolated wrapper with mocked transport. Concurrency, rollback, receipt loss, stale scope/owner/fence/deadline, partial usage and safe/unsafe recovery are covered. Existing Core/History/Interpretation/Evidence/API/browser and offline frontend contracts remain regression boundaries; actual counts and limitations are in [HANDOFF](../../HANDOFF.md) and the PR.

Configured application-data migration/backup restoration, Qdrant, external accounting and semantic answer quality remain unverified. Production runtime/history admission stays unavailable/fail-closed. #5c-2 and #5d remain NOT_STARTED; v0.2a is not complete.
