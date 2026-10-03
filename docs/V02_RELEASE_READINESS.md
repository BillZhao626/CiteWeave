# CiteWeave v0.2.0 — Release Readiness

Status: **REVIEWED RELEASE CANDIDATE — Human PR review pending**. Owner separately authorized review, logical commits, feature push and PR. Merge/auto-merge, tag and release remain outside this task.

## Candidate and release identity

Exact source base: merged PR #19 main `80796e56d98631071ce87333339a13e3cbf40067`.
The initial worktree was clean on local `codex/v02c-release-delivery-m4`; remote main matched and no release branch existed remotely. The local branch was safely renamed to `codex/v02-release-readiness`. The historical `v0.1.0` tag remains `d29a324a06c07799a11ed642e370c5e6d5a2e6db`; `v0.2.0` is not created.

Python project/uv source-package lock, frontend package, FastAPI and both generated OpenAPI artifacts use `0.2.0`. The frontend pnpm lock has no source-package version field and its dependency resolution is unchanged. Installed-component SBOM metadata reads the same pyproject version instead of a historical stage label; its clean output directory is created when absent. Generated TypeScript is rebuilt through `export_openapi.py` / `pnpm generate:api`; metadata-only version changes do not change API schema fields. The future Git tag is `v0.2.0`. Third-party dependency versions are their own identities.

Candidate verification uses an alternate temporary Git index and `git write-tree`, without modifying the real index during the original verification. Subsequent review/delivery has separate commit/push/PR authority. `git archive` exports that candidate tree into an ignored bounded directory. This is an uncommitted candidate export, not a remote fresh clone. Receipt `verification.json` records tree identities, source hashes, environment, commands, results and final-candidate binding. Updating the results narrative changes documentation bytes; final documentation checks and source-manifest comparison bind those changes separately from the exported executable source.

## Provenance and public-data boundary

The author participated in a communication-domain RAG engineering project at Zhejiang University Hangzhou International Science and Technology Innovation Center, kept close technical communication with the mentor/team, and participated in team Gitee engineering organization and migration to team-server/service form. CiteWeave carries forward and deepens that engineering experience.

This public repository is independently maintained, independently implemented and de-identified. It is neither the internal Gitee repository's mirror/publication nor an official institution repository or institutional endorsement of subsequent independent changes. Public demonstrations use public or original data. Internal code, private/proprietary data, confidential documents, commercial materials, credentials and other non-public team assets are excluded. Public downloadability does not establish redistribution permission; [data notices](DATA_NOTICES.md), [corpus](CORPUS.md) and [third-party notices](../THIRD_PARTY_NOTICES.md) retain attribution and license boundaries.

## Three verification tiers

| Tier | Reproducible scope | Explicit exclusions |
| --- | --- | --- |
| A — clean-checkout offline | Locked source dependencies; backend Ruff lint/format, provider-free pytest, generated OpenAPI/TypeScript drift, frontend typecheck/lint/Vitest/build, release/version/docs checks | Existing venv/node_modules/env/runtime, model cache, services, private corpus, historical DB or untracked source |
| B — provider-free service smoke | Existing app Dockerfile and Compose with isolation-only override; real PG18.1/Redis8.2.9/Qdrant1.16.3, startup and repeated Alembic, API readiness/version, static JS/PDF.js/original PDF, image-contained notices, empty worker ping, bounded shutdown | Ingestion tasks, model gateway/inference, DeepSeek, provider keys, GPU, real conversation/semantic answers or recovery fault matrix |
| C — supported full workspace | Windows11 / PowerShell7 / Docker Desktop Linux containers / compatible NVIDIA CUDA12.6, local E5/BGE; user DeepSeek key for separately authorized generation | Full CPU-only/Linux deployment and this task's model/provider execution |

Tier A installs need network to public registries. Checks use offline HF/Transformers flags. The candidate has new venv and node_modules, dedicated uv/pnpm caches, and no copied operator configuration, blobs or databases. The same installation versions as public CI are Python3.12, Node22.20+, pnpm11.19.0, uv0.12.13. Exact host patch versions and commands belong to the receipt.

```powershell
python -m pip install uv==0.12.13
uv sync --frozen
pnpm --dir apps/web install --frozen-lockfile
uv run --frozen python scripts/check_release.py
```

After the frontend build, Tier B is:

```powershell
uv run --frozen python scripts/smoke_release.py
```

Compose2.24.4+ is required for isolation tags. The script generates temporary random credentials and a unique `cw-release-<uuid>` project. Every service has no host port and new project-scoped named volumes; internal network prevents external service egress, model URL points to a closed local port, Key is empty, fault injection is off. Production commands/healthchecks/depends_on are retained. The image build can require registry/network access before isolation. No local `.env` is read, no tasks are enqueued, no existing application/old RAGFlow resources are changed. `finally` performs project-scoped `down --volumes --timeout 20` and verifies no containers, volumes or network remain. An owned build image may remain cached. A safe JSON receipt is written without credentials, complete DB URLs or service error bodies.

Tier C remains `scripts/m1.ps1 -Setup`; this task does not run it. Bootstrap generates local random credentials without overriding existing `.env`. The setup script now pins uv consistently. Defaults do not install a positive Conversation policy: `/health/ready` means durable API readiness, not model/runtime availability. See [QUICKSTART](QUICKSTART.md) for policy/authorization and backup boundaries.

## CI and migration scope

Existing GitHub Actions Windows/Linux offline matrix is retained. A bounded provider-free Linux service job builds the frontend and runs the same real service smoke; no heavy model workflow or new infrastructure is added. Local success is not evidence that the unpublished workflow has already run on GitHub. Static Compose parsing uses `.env.example` with `config --quiet` only.

Alembic has one head, `0014`; this candidate adds no durable schema or migration changes. API startup upgrades the disposable empty PG database; repeat upgrade and empty execution/provider/job/document tables verify initialization/idempotence without dispatch. Prior merged M1/M2 migration and fault regressions remain historical synthetic evidence. Existing application schema/data and populated production backup/upgrade/restore are not tested or changed here.

## Merged engineering evidence and limits

M1 ([PR17](https://github.com/BillZhao626/CiteWeave/pull/17)) supplies durable admission, bounded safe retry, UNKNOWN no-redispatch, cancellation, stale-result fencing, restart/manual reconciliation and Acceptance. M2 ([PR18](https://github.com/BillZhao626/CiteWeave/pull/18)) supplies durable stage/error Trace and bounded recovery inspection/drills. M3 ([PR19](https://github.com/BillZhao626/CiteWeave/pull/19)) supplies frozen concurrency measurement and measured Session/shared-reader contention reduction. See [M1](V02B_RUNTIME_RELIABILITY_M1.md), [M2](V02B_OPERATIONAL_OBSERVABILITY_M2.md), [M3](V02B_CONCURRENCY_PERFORMANCE_M3.md) and ADR0023–0026 for original contracts, alternative designs and migration impact.

Profile A concurrency5 p95 `2824.3 → 1943.7 ms` (-31.2%), successful throughput `1.919 → 2.925 workflow/s` (+52.4%); concurrency10 `12/120 → 120/120`; final concurrency20 `116/120`, measured failure onset / NOT qualified stable capacity. Primary HTTP/PG profile uses synthetic model/retrieval/transport. Separate real-Qdrant profile uses three original points/synthetic2D inference. M2 record timing is inclusive, not a counterfactual marginal overhead. No rerun or tuning in this release task. These are not production QPS/SLA/cloud capacity, universal user concurrency or real DeepSeek/E5/BGE throughput.

At-least-once execution and idempotent effective results do not mean physical exactly-once delivery. Cancellation fences publication but cannot stop upstream computation with certainty. Durable Trace/drills do not establish production monitoring or SLO. Exact authorized citation identity and physical span checks do not establish semantic support. Historical Human v6 21 PASS, UNKNOWN <=0.016110 CNY and ec9 exported PENDING labels stay unchanged; historical grants are consumed/non-transferable.

## Verification results

Verified on Windows11 / Python3.12.8 / PowerShell7.6.5 / Node22.20.0 / pnpm11.19.0 / uv0.12.13 / Docker29.1.3 / Compose2.40.3-desktop.1, running Linux containers. Executable verification exports and the final reviewable tree are bound in the ignored receipt; no ordinary-workspace venv/node_modules/env/runtime/model/database state was used. Docker build reused available pinned image layers; first dependency installs used dedicated new public-registry caches.

| Gate | Result | Exact boundary |
| --- | --- | --- |
| Clean locked install | PASS | Fresh Python tool/source venv and pnpm install; public-registry network required |
| Backend lint / format | PASS | src/tests/scripts/migrations |
| Backend provider-free tests | 613 PASS / 0 FAIL / 142 SKIP | 1191 collected,436 integration deselected; original605 + eight release regressions; not counted as pass |
| Contracts / generated types | PASS | Both OpenAPI JSONs change only info.version; regenerated TypeScript content unchanged |
| Frontend typecheck / lint / build | PASS | Actual clean-export dependencies, static application + PDF.js/notices |
| Frontend Vitest | 42 PASS / 0 FAIL / 0 SKIP | 5 test files; browser E2E not rerun |
| Version / release files / documentation links | PASS | Current 0.2.0 metadata and no stale product prerelease identity |
| Real provider-free service smoke | 13 PASS / 0 FAIL / 0 SKIP | New disposable PG/Redis/Qdrant/API/empty worker, no inference/generation/ingestion |
| Flat installed-component inventory | PASS | 322 installed source/build components; zero unresolved license fields; not a full image/OS/model SBOM |
| Public content / diff / tag audit | PASS | Full532-file tracked-tree contextual audit including original PDF and two product screenshots; no versioned private receipts, v0.1.0 unchanged and no v0.2.0 |

The 142 backend skips are **115 preserved private historical receipt/Human adjudication cases + 27 pinned tokenizer/frozen-specimen cases**. They already fail closed when those non-public/local inputs are absent. No private inputs are copied into the export or public repository to clear skips. Original readiness export had605 PASS /142 SKIP /436 integration deselected. Review added six cleanup and two metadata regressions, producing613 PASS with the same142 SKIP /436 deselected. These public clean-checkout counts differ from the earlier full local747-test evidence; neither142 skips nor436 deselected integration cases are PASS. No historical semantic campaign, browser E2E, integration fault matrix, model inference or live provider is rerun here.

The final smoke verifies HTTP PDF.js LICENSE and generated notices on the built image filesystem. Generated notices are distributed in the image; there is no dedicated root notices HTTP endpoint. Development diagnostics and failure-path reproduction remain in ignored local receipts. Resource ownership is established before cleanup is armed; a container/volume/network collision is rejected without teardown. Shutdown is PASS only after container, volume and network removal is independently verified.

Existing two Python deprecation warnings and Vite >500kB chunk warning remain; the first fresh Python run additionally emitted three jieba syntax warnings, recorded separately. These are not new runtime correctness failures. Local CI-equivalent gates pass. Actual remote results must be read individually from the pushed PR checks; a local result is not a GitHub CI result.

## Independent review and delivery scope

The review started from exact26-file tree `c0eaa346cfdd32f80d81e66c5b384b81190f7174` on the verified base/branch above, with no commit, remote feature branch or PR. The Owner separately authorized blocker fixes and commit/push/PR delivery. Full candidate audit covers every tracked text file, the original synthetic PDF and the two attributed product screenshots. Historical non-technical presentation language was neutralized while technical measurements, thresholds, frozen prompts, fixtures, ledger identities and engineering scope remain intact. Compatibility filenames/IDs and private-file exclusion rules remain engineering metadata. [Development provenance](provenance/independent-development.md) agrees with the canonical README statement.

Two release-smoke defects were proved by failing regressions: teardown after detecting an existing project collision, and prematurely reporting clean shutdown before checking remaining resources. The revised release tooling arms teardown only after an empty namespace is proved and records PASS only after container/volume/network removal is verified. Six new synthetic tests cover all three resource collisions, an unlabelled named-volume collision, cleanup after partial startup failure and a retained-volume failure. They invoke no real service or provider. The real13-check smoke is rerun on the revised source; API startup, Dockerfiles/Compose commands, migrations, runtime retry/UNKNOWN/cancellation/fencing/Acceptance, Trace, citation and benchmark semantics are unchanged. The metadata guard also had a proved scope error: ignored local history could block an otherwise consistent checkout. Git checkouts now scan tracked source; portable exports continue without Git metadata. Two regressions verify ignored history is excluded while tracked obsolete identity remains blocked. No new architecture ADR is required for these release-tooling fixes.

## Remaining release steps

1. Complete the separately authorized review/delivery: logical commits, feature push and PR; inspect both offline CI platforms and the Linux service job.
2. Obtain Human review and separate merge authorization. The repository-wide source review preserves technical history and keeps all raw receipts local.
3. After separately authorized merge, verify a genuine fresh clone of exact main, including locked install and provider-free gates. The local uncommitted export cannot substitute for this step.
4. Only under separate tag/release authorization, bind reviewed source/evidence and publish `v0.2.0` / release notes. Keep `v0.1.0` untouched; do not expand provider/model execution authority.

No production availability, semantic quality, real billing, application-data upgrade or stable concurrency20 qualification is claimed. Provider/model/Judge calls in this task: **0**; new spend: **0 CNY**. Raw neutral receipts remain ignored under `.runtime/release/v0.2/` and are not public assets.
