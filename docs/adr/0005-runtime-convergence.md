# Runtime convergence and deadline foundations

PostgreSQL owns document, job, query and evaluation state. Redis Open Source 8.2.9 is the Celery transport. A broker notification contains identifiers only; a task must claim eligible work in PostgreSQL before execution. No retrieval cache is added.

The official Redis Alpine image is pinned by its registry digest in Compose. It runs unmodified, using the AGPLv3 licensing option. The service name and protocol stay `broker` and `redis://broker:6379/0`. Redis uses a new `redis_brokerdata` volume, AOF, noeviction, a 128 MiB memory ceiling and a 256 MiB container limit. The prior `brokerdata` volume is retained for a compatible rollback; never mount its Valkey persistence files into Redis.

Celery consumes `cw-ingestion` and `cw-evaluation` with concurrency one, late acknowledgements, worker-loss rejection, prefetch one, JSON and no result backend. Ingestion soft/hard limits are 1800/1860 seconds; evaluation limits are 180/210 seconds. Redis visibility timeout is 2100 seconds. PostgreSQL reconciliation precedes dispatch. Broker sends run outside database transactions; ambiguous sends can duplicate notifications, and durable claims fence their effects.

Migration 0005 only adds nullable fields. New legacy-profile ingestion jobs receive a configurable total deadline (900 seconds by default), including queue time. The future large-document profile must supply its 7200-second budget when implemented. Claim, heartbeat, stage changes, network adapters and READY publication enforce eligibility. Unfinished pre-migration jobs receive a created-at-based deadline; historical terminal rows keep null fields. Old active versions and published citations are unchanged.

New queries receive a PostgreSQL-clock deadline, owner, fence and runtime policy identity. Admission uses the existing PostgreSQL advisory lock and a configurable global capacity, default one; eight remains a later validation target. Expiry releases admission without refunding uncertain provider cost. Idempotent requests replay terminal results. External adapters check remaining time and ownership; stale owners cannot save candidates, usage, results or citations. Cancellation discards late results.

This is the compatibility foundation. The complete evaluation attempt/outbox/provider-phase recovery state machine is intentionally reserved for its later implementation batch. Existing provider retry semantics remain until that phase; no exactly-once provider guarantee is claimed here.

## Upgrade and rollback

Drain application work and stop this project's API/worker before switching. Back up PostgreSQL and content-addressed blobs. Keep Qdrant and the old broker volume. Apply the forward migration, start Redis, verify INFO server reports Redis 8.2.9, then start the compatible API/worker. Empty queues recover eligible jobs/cases from PostgreSQL. Do not blindly downgrade new durable state or automatically replay terminal work. Never use global Docker cleanup.

## Verification

Run `test_runtime_broker_contract.py`, `test_query_admission.py` and existing database, provider reliability, ingestion and citation regressions against isolated infrastructure. `tests/runtime_worker_fixture.py` is a test-only Celery entry point that mocks paid answer/judge providers while retaining the real pipeline. It is never imported by the product worker. Runtime acceptance additionally requires task IDs correlated with PostgreSQL state, duplicate delivery, empty-broker recovery and PostgreSQL restart durability. Engineering mocks do not demonstrate answer quality or eight-session capacity.
