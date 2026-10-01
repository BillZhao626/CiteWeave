# v0.2a Provider Observation contract remediation

Status: **READY FOR HUMAN REVIEW — provider-free candidate, not paid-authorized** · 2026-10-01.

The Product Owner authorized only this response-side repair after campaign
`73bd8f72-dcda-4c79-8458-d19e3a5da07e` stopped with phase
`5c649ca0-b6a7-4a26-92c5-2bdfe1fc0b59` UNKNOWN. The starting accepted candidate is
commit `0af752d3f7b6cc2178d2fac7a52e2e55f26690cc`, tree
`6264028b6c1f5412c26ae5216c581189a6ab870e`. Schema acceptance is
`d0048834-cae6-4aa7-8ec0-faedc63be9bd`, recorded at
`2026-10-01T10:31:09.670489Z`. Ignored accepted-runtime receipts supersede the
older navigation's pending schema status; they do not grant this new code money.

## Root cause and repair

Direct source audit and a mock HTTP stream prove that `llm.DeepSeekProvider`
emits `text`, `provider_id` (from the response `id`), `usage`, `model` and
`uncertain_retry`. DEV `Calls.call` previously forwarded `provider_id` and renamed
`model` to `observed_model`. The strict shared `Observation` accepts only
`request_id`, `result_hash` and `usage`; both extra keys cause `extra_forbidden`.
This affected known completion and partial-observation error handling. The real
failed call's transient response/usage was not retained, so this reproduction is
source-level evidence, not recovered billing or proof of its transport outcome.

Only `src/citeweave/evaluation/dev_launcher.py` changes executable behavior:

- Translate stream `provider_id` to existing durable `request_id`, matching the
  production conversation adapter. Persist the local result SHA256 and supported
  provider-reported usage through the unchanged `campaign.observe` transaction.
- Exclude served-model/other diagnostic fields from Observation. The phase's
  immutable `provider=deepseek` / `model=deepseek-flash` identify the reserved
  provider and alias. A served-weight revision is not thereby established.
- Include known observation persistence in the existing guarded error path.
  Unsupported observation values still raise; a durably DISPATCHED phase becomes
  UNKNOWN with its reservation retained. Invalid values are not coerced into
  usage. If the partial receipt validates, preserve it; otherwise persist an
  empty UNKNOWN observation. No retry, repair or redispatch is enabled.
- Keep `decode_output` after durable known completion. Invalid local JSON/schema
  after complete transport keeps COMPLETED accounting and can close a FAILED
  target; it does not become a new paid opportunity.

The shared Observation/Usage DTO, `_observation`, ProviderPhase columns and
migration 0012 are unchanged. Expanding the DTO or adding served-model columns
would create a shared contract/schema change without a demonstrated requirement;
matching the existing production adapter is the smaller repair. No ADR or
migration change is required. Storage/ownership/whole-row terminal immutability
remain as accepted in [ADR0012](adr/0012-dev-campaign-settlement.md).

Blueprint drift check: this bounded bug fix preserves evidence identity, scope,
ranking, Relevance-first and product Acceptance. It adds no product capability,
infrastructure or runtime authority and does not implement #5d.

## Request and financial invariance

Dataset/Gold and original sources were reverified unchanged. Request construction
and the before-send section of `Calls.call` have identical ASTs to the accepted
candidate. Frozen runtime/config, prompts, provider serializer, accounting,
retrieval/ranking/EvidencePack paths, schema and seven-source environment retain
their exact accepted identities. Neither local gateway inference nor external
model/provider/Judge/account APIs were used for this verification.

Using the pinned official tokenizer and actual production dictionary order,
all 15 interpretation and 8 independent generation concrete requests retain
their full measurements/request hashes. All 36 older reference specimens also
recount unchanged; those specimens remain observations, not live bounds. The
other generation inputs depend on interpretation and retain their unchanged
symbolic bound and mandatory per-dispatch recount. No claim that all future
dynamic bodies are already known is made.

| Proposed fresh campaign dimension | Unchanged maximum |
| --- | ---: |
| Physical calls / population | 38 slots / 24 A–AB0 targets / repeat 1 |
| Input tokens | 6,196,897 |
| Output tokens | 777,079 |
| Total tokens | 6,973,976 |
| CNY | 18.610426 |

Interpretation/generation output reserves remain 1,561 / 32,768. Absent/saved
slots are not transferable. Judge/retry/repair/refetch remain zero. These are
proposed bounds under the frozen rate/account assumptions; no positive grant
was created or renewed.

Historical unresolved exposure is **≤0.016110 CNY**, actual bill/usage unavailable.
A future separately authorized full campaign would add **≤18.610426 CNY**;
maximum cumulative exposure would be **≤18.626536 CNY**. The historical call is
not zero and is outside the future campaign. This remediation adds zero spending.

## Historical preservation and verification

Read-only full-row comparison with the saved final reconciliation proves the
historical campaign, UNKNOWN phase and case unchanged. The original phase
request identity, 1,811 input / 1,561 output reservation, timestamps and empty
usage/request-id/result observations remain intact. It is not reconciled as
known, retried, redispatched, deleted or rewritten. The accepted isolated
runtime remains OID 440292/head0012, and all three installed trigger-function
hashes match the accepted schema. Seven PG/source/index/blob/physical-citation
bindings were reverified against frozen original sources and saved retrieval
receipts, without fresh retrieval or model inference. Physical validity does
not prove semantic support. The normal application remains head0005/28 versions.

Regression fixtures use mock HTTP or fake streams and SYNTHETIC zero-grant
campaigns in disposable UUID PostgreSQL databases. They reproduce both forbidden
keys; verify DISPATCHED before fake send, mapping, COMPLETED fields and reserved
model identity, diagnostic exclusion, known-invalid output, partial usage and
UNKNOWN; reject malformed receipts and same-key redispatch; and exercise SQL
whole-row UNKNOWN immutability. Existing production/provider, State-only
settlement, accounting, budget, recovery and migration regressions are included.
They prove mechanisms, not real provider latency, billing or answer quality.

Final combined focused validation: **222 passed, 0 failed, 0 skipped** (35.09s),
including the migration/whole-row retention and relevant production PG regressions.
Full `scripts/check_release.py`: backend **452 passed /327 integration deselected**,
frontend **41 passed /5 files**; Ruff lint/format (234 Python files), generated
OpenAPI/TypeScript, frontend lint/typecheck/build passed. Counts overlap and are
not additive; deselection is not PASS. Existing two Python deprecation warnings
and Vite chunk>500kB/plugin-timing warnings remain. After validation the full
historical rows and seven bindings were read back unchanged again. Project PG
and Qdrant were used only for read-only binding audits and UUID test databases;
the model gateway stayed stopped. No RAGFlow operation or normal-app migration.

Validation receipts and final candidate identity are recorded in the ignored
`.runtime/evaluation/provider-observation-remediation/` receipts; the delivery
reports the exact commit/tree after the local checkpoint. Initial red tests
reproduced three observation validation failures. A read-only audit comparison
initially rejected numeric-string versus JSON-number representations of the
same reservation; normalizing Decimal representations corrected the comparison,
with no historical data mutation. Failed runs are not counted as passing runs.

## Human gate

Review the response mapping and conservative malformed-receipt behavior at the
new exact candidate commit/tree. It is not paid-authorized. Any future execution
requires independent authorization for that new identity, fresh finite campaign
identity/expiry/deadline, available account budget including the historical
unresolved exposure, and revalidated isolated bindings. The old stopped HUMAN
policy is immutable historical evidence and cannot be reused. No winner,
promotion, push/PR/merge/tag/release or #5d is authorized here.
