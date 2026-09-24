# Portfolio alpha E0

`citeweave-portfolio-alpha-e0` is an explicit **post-Holdout development**
runtime identity. It selects `answer-telecom-consistency-v1` for the existing
`telecom-structural-v1` Ask path. Select that retrieval path in React before
submitting a question. Existing historical defaults and prompts remain unchanged.

Prompt SHA256: `00877db7c61eb4f5aea05ee8fba6c05253c41e2a9fe9d855c5f5974e2c3497d4`.
The historical `answer-telecom-v1` SHA256 remains
`4229c840f98099dc4d084a5898f51f45846c644866c787e030925997ddf6a14d`.

Use the existing installed dependencies, frontend production build, PostgreSQL,
Qdrant, Redis and E5/BGE gateway described in CURRENT_OPERATIONS.md. Do not
rebuild the corpus or replace persistent volumes. Start the API and worker in
separate terminals with the same existing database, workspace and blob root:

```powershell
.venv/Scripts/python.exe scripts/portfolio_alpha.py api --database-name <existing-database> --workspace-id <workspace-uuid> --blob-root <existing-blob-directory>
.venv/Scripts/python.exe scripts/portfolio_alpha.py worker --database-name <existing-database> --workspace-id <workspace-uuid> --blob-root <existing-blob-directory>
```

The database argument changes only the database name in the locally configured
connection. Secrets remain in the existing environment configuration. API
defaults to loopback port 18080 and serves the existing React production build.
The release identity, prompt hash, retrieval parameters and provider/model are
persisted with each new Run. Prompt selection does not reinterpret old runs.

The portfolio worker reuses the existing PostgreSQL outbox/recovery supervisor
and Redis/Celery ingestion task. It consumes only `cw-ingestion` and does not
dispatch evaluation jobs. On Windows this profile uses the Celery solo pool.
PostgreSQL remains the job-state authority; this local success-path verification
does not establish production worker-loss or timeout guarantees.

Historical quality statuses remain exactly:

- `STAGE_D2_HOLDOUT_NOT_CONFIRMED`
- `STAGE_D2_POST_HOLDOUT_VISIBLE_HARDENING_ACCEPTED`

The frozen historical T2 candidate is not renamed. The local E0 receipt binds
the final source, runtime configuration, three one-shot public product queries,
durable runs, exact PDF citation checks and one original asynchronous PDF job.
It is product integration evidence, not independent Holdout confirmation,
semantic verification, a quality benchmark or production/security certification.
Actual provider billing is unavailable; reported cost is the recorded estimate.
E1 visual work and public release require a subsequent instruction.
