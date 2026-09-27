# CiteWeave engineering rules

- Personal, independently implemented evidence RAG. Read only this project's new code/specs for implementation; never read/copy former employer/lab/old RAG code, prompts, data or credentials. Keep `审计私有/` excluded from implementation and publication.
- PostgreSQL is the business authority, Qdrant is a rebuildable index, Redis is a recoverable broker. FastAPI + SQLAlchemy 2/Alembic + Celery; React 19/TypeScript/Vite/Router/TanStack Query/Tailwind/shadcn. Use LocalBlobStore; do not add unrelated infrastructure.
- Pydantic/OpenAPI defines API types. Generate frontend types. Specs and ADRs define invariants; do not silently change frozen evidence offsets, scope, ranking or task semantics.
- Keep adapters separate from domain workflows. All durable schema changes use Alembic. Separate logical Document from immutable DocumentVersion.
- Never expose an index until its durable READY commit. Fence stale attempts and isolate their external index writes. Execution is at least once; prove idempotent effective results.
- Citations resolve authorized, immutable source versions and exact spans; quote validity is not semantic support. Do not expose unverified streamed drafts as final answers.
- Keys come from environment; never print them, full database URLs or provider error bodies. Use generated local configuration and explicit publication allowlists.
- Use original/licensed fixtures; public downloadability does not imply redistribution permission. Preserve third-party attribution.
- Test meaningful risks: migrations, scope, idempotency, state transitions, partial indexing, worker loss, citation identity. Run backend lint/format/tests and frontend lint/typecheck/build. Report real failures/skips and synthetic-data limits.
- Record architecture changes in ADRs with alternatives and migration impact. Avoid unrelated refactors, invented reliability/performance claims, infinite retries and swallowed errors.
- All changes stay here. Preserve old RAGFlow containers/volumes and keep them stopped. Do not run global Docker prune/reset.

## Task navigation

- Start with [current milestone](HANDOFF.md) and the [documentation map](docs/README.md); read only the current task's relevant Spec / ADR, not complete historical archives.
- Current implementation / operations: [architecture](docs/ARCHITECTURE.md) and [quickstart](docs/QUICKSTART.md).
- v0.2 scope / foundation: [Blueprint](docs/V02_BLUEPRINT.md) and [Foundation](docs/V02_FOUNDATION.md). Development / delivery: [Playbook](docs/AI_DEVELOPMENT_PLAYBOOK.md) and [Governance](docs/ENGINEERING_GOVERNANCE.md).
- The v0.2 Blueprint / Foundation / Governance baseline is **ACCEPTED — Human Review incorporated**. Future Architecture, Feature Specs, Evaluation Spec and candidate ADRs remain unaccepted; implementation is NOT_STARTED. Follow the Playbook's bounded-task / Human Gate policy; baseline acceptance does not authorize implementation.
