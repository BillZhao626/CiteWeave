# Contributing

Start with an issue describing a reproducible problem, a bounded change and its validation. Do not submit former employer/lab code, confidential documents, credentials or model weights. Contributions must be original or accompanied by compatible licensing and attribution; first-party contributions use this repository's MIT license.

Read AGENTS.md and the specs/ADRs before changing scope, source identity, ranking or task semantics. Keep the frontend generated API types aligned with Pydantic/OpenAPI. A prompt/profile change needs its own identity and comparison artifacts. Tune only on Development; do not change the frozen dataset or use Frozen Test to select parameters.

Run `scripts/verify.py --milestone m3` with the local services ready. It creates an isolated PostgreSQL test database and calls local models with a simulated LLM. Never run destructive global Docker cleanup. New critical behavior requires tests of the failure boundary, not tests that merely duplicate the implementation. Report skipped/failed checks honestly.

Before sharing a candidate, run the publication allowlist and secret scanner. Keep `.env`, `.runtime`, `.cache`, private audits and downloaded third-party PDFs out of submissions. A fresh user downloads licensed source material themselves or uses the included original handbook.

No public remote is assumed by these instructions. A maintainer selects and authorizes the actual publication destination.
