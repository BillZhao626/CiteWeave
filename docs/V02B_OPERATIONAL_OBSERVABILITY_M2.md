# v0.2b M2 — Operational Observability & Recovery Drill

Current source status: **MERGED** in [PR #18](https://github.com/BillZhao626/CiteWeave/pull/18), main commit `8da4d177`; included in release-readiness base `80796e56d98631071ce87333339a13e3cbf40067`. Historical implementation/review status, gates and stop boundaries below remain records of their original tasks. Current release scope: [v0.2.0 readiness](V02_RELEASE_READINESS.md).

Status: independent M2 implementation review complete; authorized commit/push/PR delivery, Human review pending. Owner implementation and separate review/delivery missions, 2026-10-03. Stop before merge/auto-merge, tag/release, M3 and performance execution. Original V02B_OPERATIONAL_OBSERVABILITY_M2_COMPLETE receipts are preserved.

## Identity and scope

Verified before edits: branch `codex/v02b-observability-recovery-m2`, clean worktree, HEAD `18caafbb0f43d9b1c0cb851002412e7058893660` (M1 PR17 main baseline). Champion8184 is an ancestor; rejected ec9 is not. Migration0013 and M1 reliability tests exist. Earlier M1 stop-before-M2 navigation is superseded by this explicit Owner mission. Blueprint drift: increment concerns the accepted durable conversation/result boundary and bounded operational recovery; no changes to scope, retrieval/ranking, interpretation/generation prompts, evidence offsets, provider grants or semantic evaluation.

Active path: authenticated `conversation_api.submit` → `admit_once` → `ProductionRuntime.execute/start_execution` → authorization and bounded PG History → local guarded Interpretation (optionally separately authorized provider interpretation) → `produce/StructuralEvidenceRetriever` → `RuntimeCalls/ProductionGenerator` → current-pack citation/result checks → `core.accept` → authorized GET readback/finite SSE snapshot. Default runtime stays unavailable. Test transports/models/retrieval are synthetic and do not constitute live service verification.

## Before / after gap matrix

Labels describe the active product/operator surface, not historical experiment logs. `DURABLE_AND_PUBLIC` means authenticated Conversation Trace; operator-only durable fields are identified explicitly. No new instrumentation was added to unadmitted HTTP requests, SSE delivery time or unrelated workflows.

| Signal | Before change | After change / boundary |
| --- | --- | --- |
| request/idempotency identity | DURABLE_AND_PUBLIC | existing fingerprint; raw idempotency key remains DURABLE_INTERNAL_ONLY |
| conversation_id / turn_id / run_id | DURABLE_AND_PUBLIC | retained linked identity on every Trace |
| provider_phase_id | DURABLE_AND_PUBLIC | event identity + bounded typed provider receipt summary |
| provider purpose | DURABLE_INTERNAL_ONLY | DURABLE_AND_PUBLIC event phase; old provider events derive purpose from their exact ledger row |
| attempt / fence | DURABLE_AND_PUBLIC | retained; historic attempt0 projects unavailable, not zero sends |
| state transition | DURABLE_AND_PUBLIC | Run/provider transitions retained; local stage kinds clearly separate from Run transitions |
| retry classification | DURABLE_AND_PUBLIC | unchanged M1 classifier, event + typed category and policy limit |
| UNKNOWN reason | DERIVABLE_BUT_NOT_EXPOSED | known-result-not-accepted vs uncertain provider vs unavailable legacy reason |
| cancellation | DURABLE_AND_PUBLIC | retained plus unresolved-provider diagnostic and UI |
| reconciliation/recovery | DURABLE_AND_PUBLIC | retained plus read-only predicted target/attention in CLI |
| stale rejection | EPHEMERAL_LOG_ONLY | DURABLE_AND_PUBLIC runtime rejection with attempted/current fence; unrelated direct Core callers do not gain runtime diagnostics |
| error class / precise code | DURABLE_AND_PUBLIC provider codes; local exception class only | stable precise application code + derived operator category; arbitrary bodies/messages replaced with safe code |
| admission to claim latency | DERIVABLE_BUT_NOT_EXPOSED | DB timestamp difference where execution_started exists |
| local History/Interpretation/retrieval | MISSING | monotonic stage facts on ProductionRuntime path |
| generation / final validation | MISSING | monotonic stages, including bounded provider orchestration inside generation |
| provider attempt latency | DURABLE_AND_PUBLIC | retained M1 measurement; summed known observations, partial/UNKNOWN explicitly incomplete |
| publication latency | MISSING | local validation/transaction elapsed until last guarded flush, excluding that flush/commit acknowledgement |
| total Run latency | DERIVABLE_BUT_NOT_EXPOSED | created_at→completed_at DB difference; active incomplete, UNKNOWN/cancelled distinct |
| token usage | DURABLE_AND_PUBLIC completion events / DURABLE_INTERNAL_ONLY partial ledger usage | safe ledger usage as reported; missing values remain null, no imputation |
| estimate / price revision | DURABLE_INTERNAL_ONLY | exact existing receipt estimate + pinned revision, non-billing label |
| retrieval/evidence summary | DURABLE_AND_PUBLIC accepted documentary bundle | unchanged authorized immutable source/evidence identities; failed Runs do not acquire a fabricated bundle |
| final terminal state / Acceptance | DURABLE_AND_PUBLIC | retained; explicit ACCEPTED / NOT_ACCEPTED diagnostic |
| React lifecycle timeline | MISSING (API events already exist) | existing Trace Inspector renders bounded operational projection |

## Minimum operational Trace contract

`conversation-trace-v1` gains optional typed `operational` (`operational-trace-v1`); existing fields and `reliability_events` stay compatible. Pydantic/OpenAPI defines the schemas; both OpenAPI files and TypeScript are generated. `cw5_run_events` remains the only event authority. Alembic0014 only adds nullable phase/current_fence. [ADR0024](adr/0024-operational-trace-and-recovery-inspection.md) records alternatives and migration impact.

Timeline: newest64 facts, displayed ascending `(created_at,id)`, stable across readback/process restart, with truncation flagged. Equal timestamps use UUID ordering, without inferring causality. Fields: event timestamp/kind, local phase/provider purpose, provider identity, attempt, attempted Run fence/current Conversation fence, from/to state, exact error_code and derived category, original retry classification, recorded latency/usage. Local stage RUNNING/COMPLETED/FAILED are not Run states. Terminal events identify the fence invalidating old work; runtime stale rejection identifies the matching current fence. Repeated rejection for the same fence is not duplicated.

Provider summary reads at most two Conversation-owned ledger rows, never Eval/legacy query phases: state, latest transport attempt/limit, dispatch evidence, retry classification, safe exact code/category, usage, estimate and price revision. Dispatch states distinguish no recorded marker, committed marker/send unconfirmed, observed response, and known non-execution. A rejected HTTP request can have an observed response while execution is known not to have occurred. A ledger COMPLETED without Acceptance stays blocked and can become UNKNOWN; no reconstruction or redispatch.

Timing: admission_queue uses DB timestamps; local stage measurements use perf_counter. History covers bounded History read; Interpretation sums both existing local guards and excludes paid interpretation; retrieval covers the documentary adapter; validation covers detach/assembly and final result construction; generation includes provider orchestration/backoff and generator citation checks. Provider latency is the existing attempt measurement, including adapter/dispatch bookkeeping, not pure network time. Publication includes durable final validation/transaction work until its last guarded flush. It excludes that flush and commit acknowledgement. These measurements overlap and must not be summed into a benchmark. Total uses existing DB timestamps; crash/recovery total includes time until reconciliation. Historical local durations are unavailable.

Availability is AVAILABLE / UNAVAILABLE / INCOMPLETE / UNKNOWN / CANCELLED. Null is distinct from measured0. A truncated timeline or missing provider attempt measurement cannot claim complete stage totals. Reversed DB timestamp intervals project null/INCOMPLETE, never synthetic zero. Started stages without completion remain incomplete. Cancellation can leave completed local work plus a CANCELLED Run; this never publishes a result. Missing provider usage/cost is not zero. No P50/P95/QPS/SLO/availability claim follows.

No hidden reasoning, prompts, credentials, raw provider body, arbitrary exception message, authorization grant secret or unrelated history enters new fields. Existing authorized Trace question/evidence fields remain unchanged. Requests rejected before Run admission still have no durable Run timeline.

## Operational taxonomy

The exact application/provider `error_code` remains; `error_category` is a projection. M1 `classify`, allowed attempts, reservation, owner/deadline checks and retry semantics are unchanged. A category never permits retry.

| Category | Primary evidence |
| --- | --- |
| admission | exact runtime request/input/phase authorization codes |
| validation | documentary/interpretation/local validation codes or validation stage |
| database_transaction | SQLAlchemy error → safe database_transaction_failed; historical exact SQL exception classes |
| retrieval | retrieval phase/index/model codes |
| provider_known_safe | existing BEFORE_DISPATCH / RETRYABLE_KNOWN classification; finite policy still required |
| provider_unknown | existing UNKNOWN classification, including HTTP503; no redispatch |
| provider_permanent | existing PERMANENT classification |
| cancellation | cancelled event/cancel intent (provider UNKNOWN remains separately classified) |
| deadline | exact deadline/request-timeout codes outside a stronger provider classification |
| reconciliation | recovered event/expiry code |
| stale_fenced | rejected stale event or owner/head/fence code |
| internal_invariant | remaining safe application codes; unexpected exception bodies become internal_error |

## Recovery inspection

`python scripts/reconcile_conversations.py --workspace <authorized-uuid> --inspect --limit 32`

Optional `--run <uuid>` inspects one scoped Run; `--include-terminal` includes active/accepted/cancelled/stale. Without these, select expired ADMITTED plus UNKNOWN/INTERRUPTED/FAILED. Default32/max128; query limit+1 reports has_more rather than claiming global completeness. Expired active Runs come first, then UNKNOWN, then others, each by created_at/id. Repeatable-read/read-only PG transaction prevents inspection writes and gives a coherent bounded snapshot; explicit local DB/operator authority is required, no new admin API exists. No provider/client transport is instantiated or invoked.

Attention: RECONCILE_EXPIRED (predicted INTERRUPTED/UNKNOWN/FAILED), UNKNOWN_BLOCKED, INTERRUPTED_NEW_AUTH_REQUIRED, PERMANENT_FAILURE, FAILED_REVIEW, ACTIVE_WAIT, NO_ACTION. Prediction uses existing blocks_retry/permanent_failure receipts. Age alone never proves dispatch safety. The usual CLI without --inspect separately invokes M1 bounded reconciliation and never sends. No startup hook, automatic retry or timer. Inspection is not execution authorization; concurrent changes require locked recheck when applying recovery. A cancelled Run needs no Run action while its unresolved provider reservation remains visible/blocked.

## Recovery drill matrix

`tests/test_operational_recovery_drills.py::test_operational_recovery_drill[<id>]` is a16-case suite over M1's exact fault seams. Each local JSON receipt contains initial condition, injected failure, durable events/fences/attempts, final state, dispatch-marker count (not physical-send certification), Acceptance existence, operator interpretation and complete authorized synthetic public Trace. M1 helpers independently assert actual fake transport sends, rollback, no redispatch and process boundaries.

| id / injection | Final state / Acceptance | Redispatch / operator interpretation |
| --- | --- | --- |
| 01_success / none | ACCEPTED / yes |1 fake send, NO_ACTION |
| 02_duplicate / same-key new-process replay | ACCEPTED / one |1 fake send total, same identity, NO_ACTION |
| 03_known_safe_retry /429 then success | ACCEPTED / yes |2 bounded fake sends, NO_ACTION; retry reason visible |
| 04_retry_exhaustion /429 twice | FAILED / no |2 cap, FAILED_REVIEW |
| 05_provider_unknown /503 | UNKNOWN / no |1 send, no retry, UNKNOWN_BLOCKED |
| 06_cancel_before_dispatch | CANCELLED / no |0 sends, NO_ACTION |
| 07_cancel_inflight | CANCELLED / no |1 send, unresolved reservation, NO_ACTION |
| 08_late_after_cancel | CANCELLED / no |1 send, rejected stale receipt/current fence, NO_ACTION |
| 09_stale_fence / old owner after new retry | old INTERRUPTED; fresh ACCEPTED / fresh only |no provider work; fresh fence publishes, stale rejected |
| 10_kill_before_dispatch / PREPARED OS-kill | old INTERRUPTED / no |no send; separate fresh retry only ADMITTED, new authorization required |
| 11_kill_after_dispatch / OS-kill | UNKNOWN / no |1 synthetic dispatch, no redispatch, UNKNOWN_BLOCKED |
| 12_result_without_acceptance / OS-kill | UNKNOWN / no |known receipt, no redispatch, KNOWN_RESULT_NOT_ACCEPTED |
| 13_permanent_rejection / before finish crash seam | FAILED / no |permanent401 preserved, PERMANENT_FAILURE |
| 14_transaction_failure / Acceptance insert flush | UNKNOWN / no |known provider completion; bundle/head rolled back, no redispatch |
| 15_publication_deadline / expired DB deadline injected at final flush | UNKNOWN / no |no partial accepted result; final guard fenced, no redispatch |
| 16_bounded_reconcile / two expired Runs, limit1 | both INTERRUPTED / no |one per batch; repeated no-op; no provider dispatch |

Drills07/08 use the same race seam and assert both cancellation and late rejection; they are not independent fault mechanisms. Only drills10–12 perform OS process kills. Drill13 injects a durable crash boundary, not an OS kill. Synthetic providers do not certify physical network delivery.

## Verification receipts

Original implementation provider-free results, 2026-10-03 (immutable historical receipts; final reviewed-diff rerun below):

| Gate | Exact receipt / command | PASS / failure / error / skip |
| --- | --- | --- |
| Backend release + lint/format + contract generation + frontend checks | `python scripts/check_release.py`; `release-final.log` | backend740 /0/0/0;424 integration deselected, not PASS |
| Final lint/format after integration-fixture updates | `python -m ruff check src tests scripts migrations`; `python -m ruff format --check src tests scripts migrations`; lint-final.log / format-final.log | pass;275 formatted files |
| Isolated PG full M1 compatibility + new M2 | `pg-final.xml` / `.log`; exact16-module argv and328 test IDs in verification.json |328 /0/0/0 (M1 baseline303 + M2 integration25, including16 drills) |
| M2 unit rules | `tests/test_operational_trace.py`, included in release740 |9 /0/0/0; not added again |
| Frontend lint/typecheck/tests/build + OpenAPI/TS drift | included in release-final.log |42 /0/0/0, all other checks pass |
| Production-build Chromium / real HTTP+PG wrapper | `CW_RUN_INTEGRATION=1 python -m pytest -q -s tests/test_conversation_browser.py --junitxml=.runtime/reliability/m2/browser-final.xml`; browser-final.log / .xml | Chromium3 /0/0/0; Python wrapper1 /0/0/0 |
| Deterministic final-flush deadline pair | deadline-deterministic.xml / .log; `pytest tests/test_runtime_reliability_postgres.py tests/test_operational_recovery_drills.py -k 'acceptance_final_write or publication_deadline'` |2 /0/0/0;45 deselected; overlaps PG |

Release checks ran on the final implementation/frontend. Subsequent changes were limited to integration-test head expectations and the deterministic deadline injection, verified by final Ruff and PG gates; offline/frontend tests were not rerun without affected source changes. Final implementation receipts are not summed with overlapping characterization/reproduction runs. The424 tests excluded from offline include328 in the selected PG suite and1 browser wrapper; the remaining95 service/model/index integration tests were not selected here. No inference/real Qdrant verification is claimed.

Receipt SHA256 (relative to ignored `.runtime/reliability/m2/`):

- `release-final.log`: `bb462a7aa16b08bc859012c3f581833c4b87d0e538575b2e42f8049c9d2b1191`
- `pg-final.xml`: `12ee4818f953b05011971503309a1a88423e8864e92b12f2139745b133e7d831`
- `pg-final.log`: `d1a2b921050d9373745fdabec229cef0a8b54c947afe930d6513c5de9429f68f`
- `browser-final.xml`: `0bd7c61cd28a20bcedfcd308ac4e586e977549ce9f5ff398ce950d7cce6d3c80`
- `browser-final.log`: `40655b336a7b56000193eab83e96601dfddacf160c43a422e5d8783816b41b12`

`verification.json` binds the final34-file allowlist/source SHA256, selected test identities, commands,16 drill hashes and resources. Before/after snapshots agree: application schema0005,28 document versions and all pre-existing database names unchanged; UUID test databases cleaned. Only project PG was started, then stopped; all containers are stopped, old RAGFlow volumes/containers untouched. Default runtime not activated. Existing FastAPI/Starlette deprecations and Vite >500kB bundle warning remain.


Failures preserved: initial missing operational module red test; first release gate2 old Core mock failures after an additional event lookup, repaired by passing the already-locked Conversation fence directly. Early M1 PG32 passed but one Windows child-output decoding warning was observed; final runs explicitly set PYTHONUTF8/PYTHONIOENCODING. The first combined PG gate had2 legacy head assertions still expecting0013; those now expect0014. A subsequent combined run had1 intermittent drill15 timing-injection failure (HTTP200); isolated reproduction passed. The final-flush fixture now deterministically injects an expired DB deadline instead of relying on a2-second/2.1-second sleep margin, and the focused M1/M2 pair passes. It proves the final guard/rollback boundary, not a measured slow-transaction or wall-clock result. Product deadline checks are unchanged. Original red receipts remain pg-head-red and pg-deadline-red. No failed run is counted as final PASS.

## Independent implementation review / PR delivery

The separate Owner mission authorizes review fixes, commits, push and a PR against exact main `18caafbb0f43d9b1c0cb851002412e7058893660`; no merge/auto-merge or M3. Before edits, all34 source hashes matched the original verification manifest. HEAD/main/fetched origin/main and merge-base matched that baseline; Champion8184 was an ancestor and rejected ec9 was absent. The original manifest, successful/failed receipts and drill artifacts remain unchanged. New evidence is separate under ignored `.runtime/reliability/m2/review/`.

Review confirms a single retained event authority; Trace/UI are projections. Inspection executes SET/SELECT in a workspace-scoped, bounded, repeatable-read read-only transaction, never constructs transport, and actual reconciliation rechecks facts under the existing lock. Migration0014 follows0013, adds nullable columns without backfill, preserves retention triggers, supports populated/repeated upgrades, and refuses destructive downgrade in favor of fix-forward. No0013, provider ledger/classifier, prompt, Interpretation, ranking, evidence-offset or citation-authority implementation was changed. Phase wrappers preserve operation order and original guards; diagnostics do not grant retry. Database recording failures propagate, without an automatic retry. Timing overlaps are not additive, and publication explicitly excludes final flush/commit acknowledgement.

| Review defect | Why earlier passing tests did not exclude it | Smallest regression / correction |
| --- | --- | --- |
| stage_started added a live-status/deadline guard to observation | prior tests checked workflow outcomes, not observation's lack of decision authority | `test_stage_observation_does_not_add_execution_authority`: observations after expiry/cancel append facts only; original execution_input still rejects; removed extra gate, retained scoped identity lock/check |
| reversed DB timestamps were clamped to measured0 | fixtures used monotone timestamps | `test_reversed_database_timestamps_are_not_measured_zero[admission_queue/total]`: null/not_recorded/INCOMPLETE; genuine equal timestamps remain0 |
| COMPLETED provider phase could show complete latency with an unmeasured earlier attempt | normal synthetic attempts all supplied durations | `test_provider_duration_with_missing_attempt_measurement_is_incomplete`: compare recorded distinct timed attempts against durable latest attempt; retain known0, mark INCOMPLETE |
| every Core.finish conflict could be labeled stale rejection | earlier race tests used genuine cancellation fencing | `test_non_fencing_conflict_is_not_a_stale_rejection`: only stale_owner/run_not_active conflicts append that diagnostic |

New regressions first failed (unit3; PG2), then affected22 passed. The first review release attempt also found mixed-line-ending formatting in the already-modified deadline fixture; formatter repair is confined to that fixture and its failed log is retained. This is not a new runtime behavior. Drill15 reaches the final dirty ACCEPTED Run flush, injects an expired deadline only after earlier guards, and proves final-guard rollback/no bundle/head plus conservative UNKNOWN. It is a deterministic fault seam, not a timed slow database experiment. Drills07/08 share one race;10–12 alone are OS kills; fake sends/markers are not physical exactly-once proof.

Final reviewed-diff gate results and receipt bindings are recorded in the review evidence below. Offline units, PG tests, drill cases and browser wrapper are reported separately without summing overlaps. The five claims remain limited to their active synthetic test paths; no production achievement is inferred.

### Final reviewed-diff evidence

| Gate | Collected / passed / failed / errors / skipped / deselected |
| --- | --- |
| `python scripts/check_release.py` backend offline |1169 /743 /0 /0 /0 /426 |
| same release: frontend tests |42 /42 /0 /0 /0 /0 |
| same16-module M1+M2 isolated PostgreSQL argv as original, new review directory |330 /330 /0 /0 /0 /0 |
| production-build Chromium |3 /3 /0 /0 /0 /0 |
| Python real HTTP+PG browser wrapper |1 /1 /0 /0 /0 /0 |

M2 unit12 are included in743; operational PG10, migration1 and all16 drills are included in330. The remaining95 integration tests are unselected; no skip is disguised as PASS. Backend lint/format (275 files), generated OpenAPI/TypeScript drift, frontend lint/typecheck/build, unique Alembic head0014 and git diff check pass. No production source changes followed these gates. Subsequent edits only finalize documentation/evidence; link/diff hygiene was rechecked. The existing FastAPI/Starlette deprecations and Vite >500kB warning remain.

New receipt SHA256, relative to ignored `.runtime/reliability/m2/review/`:

- `release.xml`: `537d74742a16ab482f0242522137c27f84be8994d830ced577862be3ed8ecec7`
- `release.log`: `512b4ed9087bdad31a0d8814443ca9b229d521fab5103e88721c799f8790131b`
- `pg.xml`: `cce3b20fe027fbf44f43be0d80fc2eaf2b5c625b1184253fe54bf681f71592e5`
- `pg.log`: `c45073cb91946d2592e1006828377e338e5339569a487a43cd3952ec805646b2`
- `browser.xml`: `7fa5296612715198f1435cdb3b0490813141060695651dd87719589852a42d36`
- `browser.log`: `68c1a027ce2c118d05afaaefdb5bfeda9e59403c17dc65796e15afacd7b9d998`

`starting-diff.json` preserves the original34 source identities; `review-verification.json` binds reviewed source hashes, exact test identities, receipt/drill hashes, file classifications and resource snapshots. All16 new drill receipts are separate from originals. Resource inventories before/after match exactly: application schema0005,28 document versions, pre-existing databases unchanged; UUID fixtures cleaned. Only project PostgreSQL was temporarily started and stopped; all containers, including old RAGFlow, remain stopped. Provider/model/Judge calls0; new spend0 CNY; original historical evidence unchanged. PR delivery identity/CI is recorded in the attached GitHub PR and separate ignored delivery receipt; this document does not grant merge authority.

Exact publication classification (34 files; no ACCIDENTAL or LOCAL_EVIDENCE_ONLY file is committed):

| Category | Files |
| --- | --- |
| PRODUCT (10) | `scripts/reconcile_conversations.py`; `src/citeweave/conversation_contract.py`; `conversation_evidence.py`; `conversation_models.py`; `conversation_public.py`; `conversation_runtime.py`; `conversations.py`; `runtime_reliability.py`; `operational_trace.py`; `recovery_inspection.py` (all abbreviated Python names in this row are under `src/citeweave/`) |
| MIGRATION (1) | `migrations/versions/0014_operational_trace.py` |
| FRONTEND (2) | `apps/web/src/conversation-panel.tsx`; `apps/web/src/conversation.css` |
| GENERATED_CONTRACT (3) | `contracts/openapi.json`; `apps/web/openapi.json`; `apps/web/src/generated/api.ts` |
| TEST (12) | `apps/web/e2e/conversation.pw.ts`; `apps/web/src/conversation-panel.test.tsx`; `tests/test_conversation_postgres.py`; `tests/test_conversation_provider_migration.py`; `tests/test_runtime_reliability_migration.py`; `tests/test_runtime_reliability_postgres.py`; `tests/test_v02_dev_campaign_postgres.py`; `tests/test_v02_dev_migration_0012.py`; `tests/test_operational_trace.py`; `tests/test_operational_trace_postgres.py`; `tests/test_operational_trace_migration.py`; `tests/test_operational_recovery_drills.py` |
| DOC (6) | `AGENTS.md`; `HANDOFF.md`; `docs/README.md`; `docs/ARCHITECTURE.md`; `docs/V02B_OPERATIONAL_OBSERVABILITY_M2.md`; `docs/adr/0024-operational-trace-and-recovery-inspection.md` |

Ignored local receipts, XML/logs, resource inventories and helper scripts are LOCAL_EVIDENCE_ONLY. Publication uses an explicit source allowlist. No temporary DB, cache, credential, private audit material, screenshot or local machine path is published.

## Claim traceability and verification scope

Each factual row below is VERIFIED_PROVIDER_FREE only within its stated active-path test/evidence scope; it does not mean production monitoring/billing/quality or public GitHub CI. Only product engineering evidence is recorded. Public implementation/tests/docs are the candidate GitHub evidence; local receipts and demonstration states are separate artifacts.

| Candidate factual claim | Implementation → active path | Exact test → measured evidence | Demonstration candidate |
| --- | --- | --- | --- |
| durable Run lifecycle diagnostics | runtime stage facts + existing events → authorized GET Trace | operational_trace_postgres::test_active_trace_durable_durations_usage_and_restart_inspection → equal Trace/new-process inspection, typed nonnegative measurements and reported73/20 usage | success timeline; drills/01_success.json public_trace |
| structured bounded retry / UNKNOWN diagnosis | M1 ledger + diagnostic taxonomy → RuntimeCalls/Trace | test_failure_taxonomy_usage_absence_and_no_inspection_dispatch[429/503/401] + drills03/04/05 →2 max known-safe sends;1 UNKNOWN send; absent usage stays null | retry / UNKNOWN comparison using03 and05 receipts |
| cancellation and stale-result diagnosis | public cancel + runtime rejection → PG fence + Trace | drills07/08 + M1 cancel-inflight test → CANCELLED, no Acceptance, one current-fence rejection | cancellation timeline using08 receipt |
| bounded operator recovery inspection | inspect_recovery → read-only PG CLI | test_inspection_is_read_only_bounded_scoped_and_predicts_reconciliation + drill16 → SELECT/SET only, workspace isolation, limit/has_more and idempotent batch | inspect output before/after bounded reconciliation |
| durable process recovery | existing reconcile + new readback → new process | drills10/11/12 + M1 real_process_kill test → PREPARED→INTERRUPTED; DISPATCHED/COMPLETED-without-Acceptance→UNKNOWN | recovery states using10/11/12 receipts |

Recreate states: with local PostgreSQL, set CW_RUN_INTEGRATION=1, DEEPSEEK_API_KEY empty, PYTHONUTF8=1, PYTHONIOENCODING=utf-8 and CW_OPERATIONAL_DRILL_DIR=.runtime/reliability/m2/drills; run `python -m pytest -q tests/test_operational_recovery_drills.py`. Tests create/drop UUID databases and use original synthetic inputs. Each receipt's public_trace can be passed unchanged to TraceInspector in a component test/review harness; do not install a positive production policy or seed the application DB for screenshots. The component test demonstrates UNKNOWN/cancellation/fence/truncation/null-vs-zero rendering. Existing Chromium regression covers production-build Trace and citation workflow; the operational fault states are separately covered at component + real HTTP/PG layers. Candidate screenshots: success, bounded retry, UNKNOWN/no-redispatch, cancellation/late-fence, restart recovery. These are reproducible artifact candidates, not screenshots already captured or publication claims.

## Known limits and next gate

Provider/model/Judge calls0, new spend0 CNY. Historical Human v6 21 PASS, exported ec9 labels PENDING and UNKNOWN<=0.016110 CNY remain historical/untouched. Default public runtime remains unavailable. No provider/network billing, semantic support, real Qdrant, production-data upgrade, production monitoring/SLO, performance or physical exactly-once proof. History and publication measurements intentionally exclude some boundaries described above. No durable events exist for unadmitted requests; no exhaustive history UI, live SSE event subscription, raw-output recovery, automatic reconciler or provider cancellation guarantee. Retained store may grow; public timeline bounded64, operator batch bounded128, two provider purposes. Broad indexing/retention policy is a future separately scoped decision.

Next: Human review of the M2 PR and ADR0024. PR NOT MERGED. No auto-merge, M3 or benchmarking is authorized.
