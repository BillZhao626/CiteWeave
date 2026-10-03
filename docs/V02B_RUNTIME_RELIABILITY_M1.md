# v0.2b M1 — Runtime Reliability & Recovery

Current source status: **MERGED** in [PR #17](https://github.com/BillZhao626/CiteWeave/pull/17), main commit `18caafbb`; included in release-readiness base `80796e56d98631071ce87333339a13e3cbf40067`. Historical implementation/review status, gates and stop boundaries below remain records of their original tasks. Current release scope: [v0.2.0 readiness](V02_RELEASE_READINESS.md).

Status: independent implementation review complete; final provider-free gates pass; authorized PR preparation, Human Implementation Review pending. Owner mission, 2026-10-03.

## Lineage closure / Phase 0

Champion `8184d40936dd853bfaba0bb3ffcd9ab906daf11c`, tree `03a830dd5a60614ec817ca642271310eeb48e459`, is the direct implementation parent. Final Challenger `ec9dd2da4cd241bdef7b976cc4d4230927d6921b`, tree `d116644abf0b198e749c323abe1af587deb31b3c`, was NOT PROMOTED. `186d025`, `9f721621`, `ab85e407` are historical evidence only. The Owner explicitly selects Champion retention and exits semantic tuning. Human v6 21 PASS remains the historical live baseline; no new labels, Full24, provider/model/Judge execution or historical authorization reuse. Historical UNKNOWN reserve <=0.016110 CNY remains unchanged.

Full24/Human originals remain in ignored `.runtime/evaluation/final-live-evaluation/`, `.runtime/evaluation/final-residual-closure/`, `.runtime/evaluation/shared-runtime-contract/` and the existing campaign receipts. The new milestone's local preservation manifest records397 files' exact bytes; originals are not rewritten or published. Final ec9 campaign `94e6894f-e991-4242-b0ca-0e0614ed6d39` exported21 COMPLETED/3 FAILED/UNKNOWN0,33 historical provider phases and Human labels PENDING. The current Owner mission decides NOT PROMOTED; it does not retroactively assign Human labels or authorize another campaign.

Blueprint drift check: accepted Blueprint/PR #1 scope includes durable session state and excludes infrastructure expansion. This Owner-authorized milestone addresses duplicate submissions and interrupted execution without changing interpretation, provenance, EvidencePack, retrieval/ranking, source offsets, frozen evaluation or frontend workflow. No live policy is installed. Implementation truth is distinct from real-provider validation and from release promotion.

## Phase 1 — before implementation audit

Actual configured path: authenticated POST Turn → `conversation_api.submit` → `core.admit_once` → `ProductionRuntime.execute` → authorization / bounded PG History → guarded Interpretation → StructuralEvidenceRetriever → generation / RuntimeCalls → ledger DISPATCHED commit → DeepSeekProvider → citation checks → `core.accept` → durable GET / finite SSE snapshot. Default policy remains unavailable. Eval dispatch adapters are separate consumers and do not establish product behavior.

| Capability | Before | Evidence / gap |
| --- | --- | --- |
| Request identity | ACTIVE_AND_VERIFIED | PG unique conversation/key, fingerprint, Conversation lock; API/core sequential/concurrent/reconnect tests |
| Execution ownership | ACTIVE_BUT_INCOMPLETE | owner/fence/head/deadline at dispatch and Acceptance; no explicit once-only local execution claim |
| Provider ledger / grants | ACTIVE_AND_VERIFIED | cw4 phases and cw5 aggregate authorization; commit-before-send; one phase/purpose; synthetic PG runtime tests |
| Retry classification | ACTIVE_BUT_INCOMPLETE | max_attempts=1 on product path; known rejection / UNKNOWN exist; legacy gateway retry logic not authoritative for Conversation |
| Durable cancellation | IMPLEMENTED_BUT_NOT_ON_ACTIVE_PATH | owner-only core.finish CANCELLED exists, prohibits unresolved phases; no public client cancel |
| Late Acceptance fencing | ACTIVE_AND_VERIFIED | Conversation lock + owner/fence/head + post-flush DB clock; PG tests |
| Crash reconciliation | IMPLEMENTED_BUT_NOT_ON_ACTIVE_PATH | explicit one-Conversation reconcile_expired; no bounded operational batch entry |
| Atomic Acceptance | ACTIVE_BUT_INCOMPLETE | atomic bundle/head/Run transaction and unique results; no DB deferred check tying status to result existence |
| Reliability Trace | ACTIVE_BUT_INCOMPLETE | accepted documentary Trace; unsuccessful runs lack durable attempt/classification/recovery events |
| Query Celery dispatch | ABSENT | synchronous HTTP orchestration; Celery only ingestion, no query worker restart claim |
| Query Redis broker | ABSENT | query state/admission in PG; provider circuit uses PG, not Redis; no query Redis failover claim |
| Fault injection | TEST_ONLY | existing mocked HTTP + isolated PG tests; broader active-path cancellation/retry/crash cases needed |

Architecture and transitions: [ADR0023](adr/0023-runtime-reliability-and-recovery.md). Test receipts, preservation manifest, exact changed-file list and machine verification: ignored `.runtime/reliability/m1/`. Final receipts and independent review findings are recorded in the evidence document.

## After implementation audit

ACTIVE_AND_VERIFIED below means exercised on the real authenticated HTTP / ProductionRuntime / PG path with synthetic providers and fake retrieval/model responses, or on the stated operational PG entry. It does not mean default availability, live-provider verification or deployment promotion.

| Capability | After | Concrete behavior |
| --- | --- | --- |
| Admission identity | ACTIVE_AND_VERIFIED | One Turn/Run/phase under sequential, concurrent, in-progress and completed-key replay; actual new-process replay preserves identity |
| Execution claim | ACTIVE_AND_VERIFIED | execution_started_at claims once, immutable in DB; duplicate executor cannot finish the live owner |
| Timeout/retry | ACTIVE_AND_VERIFIED | Only direct no-execution connection failure,429 or circuit-open may retry; explicit1–3 cap, finite deadlines and all capacity pre-reserved; default1 |
| Cancellation | ACTIVE_AND_VERIFIED | authenticated POST cancel; pre-dispatch/local/in-flight/backoff/duplicate/commit-order tests; CANCELLED does not hide unresolved phase |
| Late-result fencing | ACTIVE_AND_VERIFIED | current owner/head/fence/deadline and durable transport attempt; an older attempt cannot redispatch in a scheduled retry gap |
| Restart reconciliation | ACTIVE_AND_VERIFIED | callable32-default/128-maximum expired batch and CLI; nonexpired ownership unchanged; INTERRUPTED/FAILED/UNKNOWN based on receipts, never age alone |
| Atomic consistency | ACTIVE_AND_VERIFIED | deferred PG ACCEPTED iff bundle exists; unique Turn/Run results; immutable Acceptance and Run events; failure rolls back bundle/head |
| Reliability Trace | ACTIVE_AND_VERIFIED | request fingerprint, linked IDs, phase, attempt/fence, transition, classification/error, available latency/usage; at most64 events with truncation flag |
| Query Redis/Celery | ABSENT | stopped broker plus fail-on-use hooks prove query does not depend on them; restart integration is N/A |

## Fault-injection matrix

All tests below are in `tests/test_runtime_reliability_postgres.py` and use UUID-isolated PostgreSQL, original synthetic evidence, authenticated API where applicable and deterministic fake transport. Unit classification/backoff proofs are in `tests/test_runtime_reliability.py`.

| Fault / boundary | Exact pytest function | Proven outcome |
| --- | --- | --- |
| sequential/completed/restarted HTTP duplicate | test_http_sequential_completed_and_restart_duplicate_count |1 Run/1 Turn/1 phase/1 Acceptance/1 fake send; new process replays identity |
| concurrent / in-progress duplicate | test_http_concurrent_and_in_progress_duplicate_count | same identity;202 while held, then one accepted bundle |
| pre/post-dispatch timeout | test_timeout_classification_on_active_path | BEFORE_DISPATCH→FAILED vs UNKNOWN; one durable attempt, no retry |
|429 /503 /401 | test_active_http_bounded_retry_or_prohibited_retry |2 fake sends only for429; UNKNOWN or permanent failure otherwise |
| retry cap / insufficient grant | test_retry_exhaustion_persisted_and_no_extra_attempt; test_retry_requires_full_aggregate_reservation | bounded2; cap1 cannot reserve two attempts, zero sends |
| proved connect failure / HTTP200 then connection loss | test_known_connection_failure_can_retry; test_success_http_then_connection_error_is_unknown; test_http_error_then_close_connection_failure_is_unknown | before success may retry; any received HTTP response prevents a later connection exception from becoming proof of no execution |
| admitted / local / in-flight cancel | test_cancel_before_execution_claim; test_cancel_local_processing_blocks_generation; test_cancel_inflight_late_response_never_publishes | durable CANCELLED; no accepted result or result SSE; unresolved reservation retained |
| cancel during backoff | test_cancel_during_retry_backoff_no_second_send | first rejection remains recorded; no second send |
| cancel vs completion | test_cancel_completion_race_pg_lock_decides | both orders exercised under PG lock; exactly one durable winner |
| old worker / old transport attempt | test_stale_worker_after_recovery_and_new_fence; test_stale_transport_attempt_cannot_complete_new_attempt | stale write/send rejected; fresh fence alone can accept |
| PG bundle write failure / final write past deadline | test_pg_acceptance_transaction_failure_rolls_back_bundle; test_acceptance_final_write_cannot_cross_deadline | no head/bundle; slow final Run/event flush rolls back after deadline; known provider completion conservatively UNKNOWN |
| process termination + fresh-process recovery | test_real_process_kill_restart_reconcile | PREPARED→INTERRUPTED, DISPATCHED→UNKNOWN, COMPLETED without Acceptance→UNKNOWN; no automatic send |
| permanent rejection crash / finite scan | test_permanent_failure_survives_crash_before_run_finish; test_recovery_is_bounded_and_idempotent | FAILED classification preserved; one bounded scan then no-op |
| constraints / scope / once-only claim | test_database_rejects_completed_without_result_and_retains_events; test_cancellation_authentication_and_workspace_scope; test_duplicate_executor_claim_fences_paid_work | SQL contradiction rollback, retained events, no cross-workspace cancellation or duplicate paid work |
| Redis unavailable / Celery | test_active_query_does_not_depend_on_redis_or_celery | fail-on-use hooks untouched; broker/worker restart claim N/A |
| populated schema upgrade | tests/test_runtime_reliability_migration.py::test_populated_0012_upgrade_preserves_rows_and_grant_capacity | original fields unchanged; old limit1/attempt0, no execution claim/event/grant backfill |

## Reproduction and limits

Use the existing Python3.12 environment and project dependency lock. `python scripts/check_release.py` runs backend lint/format/offline tests, generated OpenAPI/TS drift, frontend lint/typecheck/tests/build. For isolated PG only, `CW_RUN_INTEGRATION=1 python -m pytest tests/test_runtime_reliability_postgres.py tests/test_runtime_reliability_migration.py` creates/drops its own databases using a local PostgreSQL administrator; do not migrate the configured application DB manually. Additional legacy/provider/campaign/evidence suites and exact commands are recorded in the local receipts.

Operator recovery: `python scripts/reconcile_conversations.py --workspace <authorized-workspace-uuid> --limit 32`. It performs bounded PG bookkeeping, never provider dispatch; no automatic timer or startup hook is installed. Request cancel: authenticated POST `/v1/conversations/{conversation_id}/runs/{run_id}/cancel`; inspect durable GET result/trace/events afterward. Default runtime remains unavailable without an independently authorized exact policy. New `PhasePlan.max_attempts` defaults1; explicit larger caps permanently reserve calls/input/output/CNY for the full capacity. The original per-call amounts/usage remain per transport; aggregate policy uses the capacity multiplier.

Unknown side effects retain reservation; completed provider output without Acceptance is blocked rather than reconstructed from a raw payload store. Cancellation fences publication but does not physically abort remote computation. Execution is at least once at the infrastructure boundary, with idempotent effective admission/result; physical exactly-once delivery is not claimed. Idempotency is explicit same key + same canonical admission within a Conversation; distinct intentional keys/Turns are not globally deduplicated by question text.

No real-provider inference, model/Judge call, new Human labels, semantic quality measurement, production-data upgrade, Qdrant verification or performance benchmark. Original synthetic fixtures prove state/transaction behavior only. See [evidence and factual claims](V02B_RUNTIME_RELIABILITY_EVIDENCE.md) for final gate counts, failures and exact changed files. The Owner separately authorizes logical commits, push and PR against main containing Champion via baseline-sync PR #16. Final branch evidence is in the evidence document and attached PR; merge requires Human review. M2 is not started.
