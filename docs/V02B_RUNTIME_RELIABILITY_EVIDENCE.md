# v0.2b M1 — engineering evidence

Status: implementation review complete; final provider-free gates pass; Owner-authorized commit/push/PR preparation. Human Implementation Review and merge remain pending.

Champion / direct parent: `8184d40936dd853bfaba0bb3ffcd9ab906daf11c` / tree `03a830dd5a60614ec817ca642271310eeb48e459`. Feature branch `codex/v02b-runtime-reliability-m1`. PR #16 merged Champion with merge commit `dc215c15c56bf101f3e5edffcdcb474a011c0186`; verified `origin/main` contains Champion and has the identical tree. The original34-file working tree, status and index hashes matched the preserved snapshot before review edits. Diff against main contains only M1 changes; no ancestry rewrite is needed. Final ec9 not promoted. Architecture / gap matrix / fault matrix: [milestone](V02B_RUNTIME_RELIABILITY_M1.md); transitions, alternatives and migration impact: [ADR0023](adr/0023-runtime-reliability-and-recovery.md).

## Final review test receipts

| Gate | Collected / selected | Passed | Failed / errors / skipped | Deselected | Exact ignored receipt |
| --- | ---: | ---: | --- | ---: | --- |
| Backend offline release |1130 /731|731|0/0/0|399 integration|review-release-final.xml / .log |
| Complete isolated PG: core/reliability/migration + compatibility/provider/campaign/evidence |303 /303|303|0/0/0|0|review-pg-final.xml / .log |
| Frontend tests; lint/typecheck/build/API drift also pass |41 /41|41|0/0/0|0|review-release-final.log |
| Affected provider/runtime/budget, including review regression |72 /72|72|0/0/0|0|review-provider-final-01.xml / .log; overlaps PG |
| Focused classification/backoff rules |11 /11|11|0/0/0|0|review-rules-final.xml / .log; overlaps offline |

The final combined PG suite has303 distinct collected identities:140 core/new reliability/migration and163 compatibility/provider/campaign/evidence. The populated0012→0013 upgrade test is included once. Focused72/11, prior characterization108, implementation-phase80/71 and other reruns overlap these suites and are not added. Deselected integration tests are not PASS. Backend Ruff lint and format (268 files), generated OpenAPI/TypeScript drift, frontend lint/typecheck/tests/build all pass on the reviewed source. Real service coverage is UUID-isolated PostgreSQL; responses/retrieval/models are synthetic. Application schema0005 and28 document versions remain unchanged, the pre-existing unknown-owned test database is retained, and project PG is stopped after tests. Redis/Celery query restart is N/A.

The initial review gate731/302 passed before the review fix; its receipts remain but are superseded for final-source claims. The new HTTP503+close-error regression first failed (one test; incorrect FAILED), then passed within the final72 and303 receipts. A check also detected mixed line endings from the narrow edit; Ruff normalized only that source file, and final formatting passes. No failed attempt is counted as passing evidence.

Earlier implementation failures are retained in the original receipts: missing-module red collection, outdated event/schema/public-field expectations, fault-hook and cached-engine fixtures, reflected legacy seed missing explicit state/outcome, Trace typing, UTF-8 subprocess decoding, stopped-PG follow-up and an event ordinal assumption. Those are historical diagnostics, not final failures. Existing FastAPI/Starlette deprecations and Vite >500kB chunk warnings remain. No provider/model/Judge call, production throughput, real billing or semantic quality measurement follows from these tests.

## Independent implementation / migration review

| Invariant | Review conclusion and proof |
| --- | --- |
| Admission / restart idempotency | Conversation lock, durable unique key/fingerprint, once-only execution claim and detached replay; sequential/concurrent/new-process HTTP tests enforce one effective result/send. |
| Retry / UNKNOWN | Attempts1–3 require explicit capacity reservation, current attempt/owner/fence/head/scope/deadline and bounded backoff.5xx, partial streams, uncertain dispatch/receipt and output without Acceptance block redispatch. |
| Cancellation | Authenticated workspace/scope checks and the same Conversation lock as Acceptance; both commit orders, local/in-flight/backoff/duplicate cancellation and stale publication are exercised. Cancellation cannot guarantee stopping upstream computation. |
| Recovery | Bounded expired batch delegates to the existing locked state machine. PREPARED/proved no execution→INTERRUPTED; permanent rejection→FAILED; dispatch/completion without Acceptance→UNKNOWN. It never sends or installs automatic recovery. |
| Publication | Atomic bundle/head/Run/fence/events; strict Interpretation/Citation validation; deferred ACCEPTED iff bundle exists, unique result and retained bundles/events. DB time is checked after final flush; injected late writes roll back. |
| Migration0013 | Additive columns/defaults, unique head, repeated and populated upgrade, metadata and legacy/campaign compatibility pass. Limit1 preserves old grants; attempt0 means no new instrumentation, not zero historical calls. No historical row rewrite or application upgrade. Downgrade refuses destructively removing durable receipts: use fix-forward / backup restore under existing governance. |
| API / public data | Pydantic-generated OpenAPI/TS, authorized cancellation/readback and finite accepted-only SSE. Trace exposes bounded typed IDs/classes/integers, not owner/key/raw provider body/prompt. Frontend source changes only its Trace test fixture. |

One genuine blocker was fixed: the transport previously remembered only HTTP200. A connection exception during response cleanup after HTTP503 could therefore overwrite uncertainty as `llm_connection_failed`, permitting retry. Existing coverage tested HTTP200/read failure and direct pre-response connection failure, but did not combine non-200 response and close failure. `llm.py` now records receipt of any HTTP response before branching. `test_http_error_then_close_connection_failure_is_unknown` verifies UNKNOWN, exactly one fake send/attempt, retained reservation, no Acceptance, same-key reuse and rejected explicit retry. No other production/schema change was made during this review. The rest of M1 is independently reviewed without changing frozen semantics.

## Factual claim traceability

| Candidate factual claim | Active implementation / execution | Exact proof in tests/test_runtime_reliability_postgres.py | Measured evidence | Portfolio candidate |
| --- | --- | --- | --- | --- |
| Explicit-key request idempotency survives duplicates/restart | conversation_api.submit → conversations.admit_once → ProductionRuntime | test_http_sequential_completed_and_restart_duplicate_count; test_http_concurrent_and_in_progress_duplicate_count |1 Turn/Run/phase/Acceptance and1 fake send; concurrent202 and real new-process replay | admission/trace screenshots with redacted synthetic IDs |
| Known-safe retry is bounded and durably classified | conversation_runtime.RuntimeCalls → conversation_provider.begin_attempt/fail_attempt/schedule_retry | test_active_http_bounded_retry_or_prohibited_retry; test_retry_exhaustion_persisted_and_no_extra_attempt; test_retry_requires_full_aggregate_reservation |429 permits2 fake sends under explicit cap2; exhaustion stops2; cap1 reserves no phase/send | timeline showing failure/classification/attempt2 and total reservation |
| UNKNOWN blocks automatic redispatch | same HTTP runtime + ledger; core.retry/reconcile_batch | test_timeout_classification_on_active_path; test_success_http_then_connection_error_is_unknown; test_http_error_then_close_connection_failure_is_unknown; test_real_process_kill_restart_reconcile |1 attempt for uncertain failures; UNKNOWN after dispatch/known result without Acceptance; explicit retry rejected | uncertainty/cost-reservation panel based on test Trace |
| Cancellation and late-result fencing are durable | authenticated cancel → conversations.cancel; ledger ownership/attempt; atomic Acceptance | test_cancel_inflight_late_response_never_publishes; test_cancel_completion_race_pg_lock_decides; test_stale_worker_after_recovery_and_new_fence; test_stale_transport_attempt_cannot_complete_new_attempt |cancelled result GET409/no result SSE; both PG commit orders; stale write and old-attempt send rejected | deterministic cancel/late-result walkthrough |
| Restart reconciliation uses PostgreSQL receipts | scripts/reconcile_conversations.py → conversations.reconcile_batch/reconcile_expired | test_real_process_kill_restart_reconcile; test_permanent_failure_survives_crash_before_run_finish; test_recovery_is_bounded_and_idempotent |3 actual killed subprocess boundaries; fresh recovery process; INTERRUPTED/UNKNOWN/FAILED; repeated batch no-op | bounded recovery state diagram and terminal Trace |
| Result publication is transactional | conversations.accept + 0013 deferred PG checks / immutable bundle | test_pg_acceptance_transaction_failure_rolls_back_bundle; test_database_rejects_completed_without_result_and_retains_events; existing conversation_postgres unique-result tests |write failure leaves no bundle/head; SQL contradiction rejected; one effective result | fault matrix + exact JUnit excerpts |

All six claims are VERIFIED only for the stated provider-free active HTTP/PG/operator path. Portfolio candidates are proposed artifacts, not a published demo. Do not infer real billing, semantic support, exactly-once transport, production deployment, throughput or former-internship capabilities. No polished resume bullets are supplied.

## Exact changed files

34 files, compared with Champion8184 and verified equivalent against main:11 REQUIRED_PRODUCT_CHANGE,11 REQUIRED_TEST,1 REQUIRED_MIGRATION,8 REQUIRED_DOC and3 GENERATED_FROM_CONTRACT; no accidental/untracked publication file. The only frontend source edit is its Trace fixture; generated API files follow Pydantic/OpenAPI. Existing migration/semantic/evaluation/prompt source bytes are unchanged; historical test expectations are adapted to the new additive schema and publication constraints.

- `AGENTS.md` — REQUIRED_DOC
- `HANDOFF.md` — REQUIRED_DOC
- `apps/web/openapi.json` — GENERATED_FROM_CONTRACT
- `apps/web/src/conversation-panel.test.tsx` — REQUIRED_TEST
- `apps/web/src/generated/api.ts` — GENERATED_FROM_CONTRACT
- `contracts/openapi.json` — GENERATED_FROM_CONTRACT
- `docs/ARCHITECTURE.md` — REQUIRED_DOC
- `docs/QUICKSTART.md` — REQUIRED_DOC
- `docs/README.md` — REQUIRED_DOC
- `docs/V02B_RUNTIME_RELIABILITY_EVIDENCE.md` — REQUIRED_DOC
- `docs/V02B_RUNTIME_RELIABILITY_M1.md` — REQUIRED_DOC
- `docs/adr/0023-runtime-reliability-and-recovery.md` — REQUIRED_DOC
- `migrations/versions/0013_runtime_reliability.py` — REQUIRED_MIGRATION
- `scripts/reconcile_conversations.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/conversation_api.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/conversation_contract.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/conversation_models.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/conversation_provider.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/conversation_public.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/conversation_runtime.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/conversations.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/domain.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/llm.py` — REQUIRED_PRODUCT_CHANGE
- `src/citeweave/runtime_reliability.py` — REQUIRED_PRODUCT_CHANGE
- `tests/runtime_reliability_worker.py` — REQUIRED_TEST
- `tests/test_conversation_api_postgres.py` — REQUIRED_TEST
- `tests/test_conversation_core.py` — REQUIRED_TEST
- `tests/test_conversation_postgres.py` — REQUIRED_TEST
- `tests/test_conversation_provider_migration.py` — REQUIRED_TEST
- `tests/test_runtime_reliability.py` — REQUIRED_TEST
- `tests/test_runtime_reliability_migration.py` — REQUIRED_TEST
- `tests/test_runtime_reliability_postgres.py` — REQUIRED_TEST
- `tests/test_v02_dev_campaign_postgres.py` — REQUIRED_TEST
- `tests/test_v02_dev_migration_0012.py` — REQUIRED_TEST

## Local receipts / publication boundaries

The original `.runtime/reliability/m1/verification.json` and `candidate.diff` retain implementation-phase source/receipt bindings. New `review-verification.json` / `review-candidate.diff` bind the final reviewed branch, source hashes, exact34-file allowlist and final gate logs/XML. Review lineage, per-file classification and original preserved snapshot are local evidence only. Historical `historical-preservation.json` still verifies397 untouched original artifacts, including rejected ec9 exports and approved Human v6. Historical UNKNOWN reserve<=0.016110 CNY is unchanged; new provider/model/Judge0 and exposure0 CNY.

Owner authorization covers review fixes, logical commits, feature push and PR against the verified main; Human acceptance/merge remains pending. No application migration, live policy/positive real grant, tag/release or website publication. GitHub implementation evidence is the active code/migration/tests plus these public docs; portfolio candidates remain proposed, not built or published. Implementation Truth >= Portfolio Truth >= Resume Claim Truth. Limits remain same-key idempotency, conservative blocking of known output without Acceptance, cancellation that cannot physically stop upstream computation, manually invoked bounded recovery, default unavailable runtime and synthetic fixtures. Real-provider billing/semantics, production-data upgrade, Qdrant, throughput and physical exactly-once are unverified. Stop at Human M1 review; M2 is not started.
