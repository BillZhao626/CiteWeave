# M3 API

API version `0.3.0-alpha.1`. [Generated OpenAPI](../contracts/openapi.json) defines schemas, constraints and errors; `/docs` serves the running API. Authenticate with the local workspace Bearer token or same-origin HttpOnly session cookie. Keep provider credentials server-side. [M1 upload/SSE examples](M1_API_USAGE.md) and [M2 governance endpoints](M2_API_USAGE.md) remain applicable.

| Operation | Contract |
|---|---|
| Query | `POST /v1/queries`, body `{kb_id, question, profile?}`, Idempotency-Key required; default profile `m3-context` |
| Evaluate | `POST /v1/evaluations`, body `{kb_id, dataset_id, split, profile?, judge_profile?, replay_source?}`; defaults `m3-context` / `judge-v4` |
| Compare | `GET /v1/evaluations/{candidate_id}/compare?baseline_id=...`; both must be completed, authorized and use the same dataset hash/split/Judge hash |
| Inspect | `GET /v1/runs/{run_id}` includes stages, candidates, calls, configuration snapshot, validated answer and costs |
| Resolve evidence | `GET /v1/evidence/{evidence_id}?run_id=...`; scoped to an actual accepted citation in that run |
| Export | `GET /v1/evaluations/{id}/artifact` or `/report`; preserves per-case failures and denominators |

Allowed query profiles: `m2`, `m3-dedup`, `m3-context`, `m3-answer`. Only `m3-context` is the selected M3 release configuration; rejected profiles remain explicit experimental history. Judge versions v1–v4 remain replayable. Changing profile/Judge/split under the same idempotency key returns 409. A replay source must be a completed same-workspace, same-KB/dataset evaluation with matching query profile and all requested cases available. Replays reuse query outputs and charge only new Judge calls.

```powershell
.\.venv\Scripts\python.exe scripts/evaluate.py --kb <KB_UUID> --split dev
.\.venv\Scripts\python.exe scripts/evaluate.py --resume <EVAL_UUID>
# Optional historical M2 baseline; creates a new evaluation unless resuming.
.\.venv\Scripts\python.exe scripts/evaluate.py --kb <KB_UUID> --split dev --profile m2 --judge judge-v4
```

SSE `delta` is provisional. Only `final` contains a validated persisted answer; an HTTP 200 stream can end in `error`. A syntactically valid citation is not proof of semantic support. `estimated_yuan=null` indicates an uncertain charge; reservations remain protected and actual provider debit is unavailable. Scope failures return 404, conflicts/capacity 409, schema errors 422, query/budget admission 429. Default query deadline remains 45 seconds; retry/cancellation/breaker rules are documented in M2 architecture.

Generate and check contracts after schema changes:

```powershell
.\.venv\Scripts\python.exe scripts/export_openapi.py
pnpm --dir apps/web generate:api
.\.venv\Scripts\python.exe scripts/check_contracts.py
```

The check compares current OpenAPI against both tracked JSON files and regenerates TypeScript into a temporary directory; it never silently fixes stale tracked contracts.
