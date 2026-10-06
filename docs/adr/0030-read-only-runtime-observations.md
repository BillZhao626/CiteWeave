# ADR 0030 — Read-only runtime observations

Status: implemented locally for the product-evidence reconstruction; no schema or execution-policy change.

## Context

The System surface already reads durable jobs, runs and model-gateway state, but it does not join a usable document version to its actual Qdrant collection or show whether a Celery worker answers. An API-success indicator alone cannot establish readiness of those separate services.

## Decision

Add one authenticated `/v1/runtime/operations` projection. PostgreSQL supplies owner-scoped READY versions and the latest Job and Conversation Run. Short Redis PING, Celery PING, Qdrant collection reads and model-gateway health reads observe the configured local services. They do not submit jobs, run inference, contact the LLM provider or issue a Conversation grant. Each component reports available, unavailable or not checked; absent measurements remain null. Collection reads are capped at 30 durable versions with two-second HTTP timeouts and no retries.

Only allowlisted fields are returned. URLs, credentials, provider bodies, locks, owners and authorization payloads remain outside this projection. A configured provider key is reported as configuration, never as live provider health. Qdrant point counts describe the observed collection's unit; they are not document-span counts or capacity measurements. READY usability remains a durable PostgreSQL decision.

## Alternatives

Retaining separate `/v1/system` and broker views avoids another contract but leaves index identity and worker replies disconnected in the product. A monitoring stack could provide longer histories but introduces unrelated infrastructure and is unnecessary for these bounded local observations. Returning raw upstream JSON would be simpler but could leak configuration and weaken the API contract.

## Migration and validation

No Alembic migration, backfill, broker setting, ingestion transition, retrieval ranking or Conversation Acceptance change is needed. Pydantic/OpenAPI generates the frontend type. Unit tests cover authentication, scoped collection reads and safe failed probes; a UUID-isolated PostgreSQL test proves business scope and unchanged durable states. Real local readback verifies service replies and both existing READY collection bindings separately from the synthetic tests.
