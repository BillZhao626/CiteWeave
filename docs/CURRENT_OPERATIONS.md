# Supported local operation

Use the Windows/PowerShell/Python/Node/Docker/CUDA environment stated in README.
The setup script installs frozen Python/frontend/model locks, downloads the
fixed E5/BGE revisions and launches the existing Compose services. It applies
Alembic migrations forward through 0008; never downgrade and replay terminal or
UNKNOWN provider work with an older executor. Back up PostgreSQL and the blob
directory together before upgrades. Do not remove old volumes to upgrade.

Keep generated `.env`, original documents, model caches and runtime reports
private. Set a DeepSeek key only when deliberately running paid generation.
The browser never receives model or database credentials. Existing run, source
and evaluation inspection works without paid generation. The normal product
does not silently substitute mock answers for an unavailable provider.

## Structural corpus

1. Run `python scripts/fetch_public_telecom.py` after activating `.venv`. The
   active manifest contains RFC 9293, RFC 9114, RFC 9110, RFC 9846, RFC 9673,
   RFC 9175 and MQTT 5.0 OASIS Standard. The dataset name is only
   **CiteWeave independent public telecom corpus**.
2. Verify the acquisition report and original notices. Sources stay in
   `.runtime/private/public-telecom`; never copy them into a public package.
3. Create a separate knowledge base via the existing API/workbench. Upload
   verified bytes to `POST /v1/knowledge-bases/{kb_id}/documents` with
   `filename`, an applicable `license`, and
   `ingestion_profile=telecom-protocol-pdf-v1` query parameters, PDF request body
   and a unique `Idempotency-Key`. Do not import raw downloaded documents under
   the UI's original-handbook license. The standard upload UI retains its
   legacy 10 MiB default; target API limits are 32 MiB / 600 pages.
4. Wait for durable READY. Inspect Documents / Structure before Ask. Select
   the structural query path explicitly; mixed/unsupported builds fail closed.
   Scope can select documents and single/compare mode. The legacy path stays
   available for historical knowledge bases.

No corpus re-ingestion is needed to inspect an existing accepted version.
Rebuild uses frozen canonical artifacts. Index GC/rollback must use the
existing authorized operations and preserve historical citations.

## Validation and local candidate

Generate contracts with `python scripts/export_openapi.py`, then
`pnpm --dir apps/web generate:api`. Run backend pytest with an isolated migrated
database, lint/scoped formatting, frontend test/lint/typecheck/build and the
Playwright browser acceptance in `benchmarks/product_acceptance.spec.ts`.
Browser acceptance requires explicitly provided local URLs, an existing token,
accepted run IDs and an isolated mock-generation server. It never fulfills fake
API responses. Runtime records and screenshots are written to the private
output directory supplied by the operator.

`python scripts/public_candidate.py --stage-only` stages a clean local source
candidate and manifest under `.runtime/releases`. Install the checksum-verified
Gitleaks binary locally at `.runtime/tools/gitleaks.exe` or pass `--scanner`.
`--allow-dirty` is diagnostic only. No tag, push or final public release is
created. An explicit document allowlist excludes historical machine-specific
reports and all private audit/runtime material; historical originals remain in
the local repository unchanged.
