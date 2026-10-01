# ADR 0012: One bounded DEV campaign and State-only evaluation settlement

Status: **IMPLEMENTATION RECORD — Human Review pending** · 2026-10-01.

The requested accepted database head is 0011. Compatibility tests do not accept
this additional 0012 schema. Current delivery is REMEDIATION_BLOCKED at that
explicit boundary; a future HUMAN policy must separately bind schema acceptance
identity and timestamp. Money/account confirmation alone cannot bypass it.

The Product Owner's Minimal Paid DEV Remediation request authorizes provider-free implementation after BLOCKED checkpoint 5c80f0f. It authorizes neither provider execution nor spending. This is one frozen DEV campaign, not #5d or general production readiness. Gold, prompts, ranking, evidence and product Acceptance semantics remain unchanged.

State-only A D1.V2/D3.V1 intentionally omit older raw Turns. Current bounded State may resolve evaluation intent; product Acceptance still requires its existing provenance contract. Weakening that guard, fabricating raw history or marking a known completed phase UNKNOWN would misrepresent business truth. These targets use the existing cw2_eval_cases terminal/result with EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED; no target product Run, Acceptance or head/state update. Ordinary targets retain the product acceptance adapter. Manual fixed-prefix seeds remain separately identified, not generated technical answers.

One additive 0011→0012 Alembic migration adds cw6_dev_campaigns, an immutable finite permission envelope and prospective review accounting. cw4_provider_phases remains the sole call ledger. Each DEV phase has only evaluation ownership, owner/fence, request hash, accounting/rate identity, exact input count, output reservation, Decimal CNY, expiry, attempt=1 and unique logical stage. New triggers apply only to these campaigns. Existing Query/Conversation ownership and guards remain valid. Fix forward; no destructive downgrade. The configured application DB is untouched: the isolated DEV DB was ingested at 0011 and receives 0012 only for this seam.

The campaign row lock serializes target admission, phase reservation and dispatch. Five aggregate dimensions consume permanent reservations; charges never release allowances. Exact case/stage membership caps execution at 38: 15 interpretation and 23 generation. A guard and four self-contained views remove ten protocol slots before transport; conditional D4 generation slots remain. No other case/repeat/retry/repair/refetch/Judge can reuse a skip. Complete bodies are reserialized/tokenized at PREPARED and before DISPATCHED. The latter commits before the provider's sole POST. Real transport requires the durable row's HUMAN mode, positive finite grant and confirmed account fields; a caller object or SYNTHETIC marker cannot grant I/O.

UNKNOWN, expired dispatched phases, deadline or cancellation prevent another send, preserving reservations and partial observations. Known completion stores response hash/usage and bounded evaluation response atomically. A known target may close after cancellation/deadline without falsely becoming UNKNOWN or enabling another call. Same-key terminal readback returns its immutable receipt. Unfinished targets are not retried; expired dispatch reconciles to UNKNOWN on guarded entry. No background spending worker, automatic resume or budget increase exists.

The real launcher constructs RealDevBackend, StructuralEvidenceRetriever(ModelGateway()) and the existing one-attempt DeepSeek adapter directly, without fixture repository/provider-factory parameters. It verifies clean commit/tree, Gold/PDF/config/prompts/protocol/tokenizer/rate and published real indexes. Preparation only uses local E5/BGE/Qdrant and a zero grant. Complete results close spending before Human review: 24 mandatory OUTPUT, at most12 DISPUTE, 288 future minutes. Historical Gold minutes remain NOT_MEASURED. Review completion is not promotion or a winner.

Alternatives rejected: a second call ledger duplicates accounting; changing product Acceptance violates accepted semantics; UNKNOWN for known completion falsifies outcome; the old retry-capable Eval broker cannot enforce this one-attempt envelope; memory/env-only caps can grow after restart. A small evaluation-only policy table and terminal seam preserve existing durable authorities with no new infrastructure or product API.

Validation and exact candidate/environment identities are in [the authorization packet](../V02_DEV_PAID_EXECUTION_AUTHORIZATION.md). Synthetic zero-grant tests verify mechanics, not billing or semantic support. Real local ingestion/retrieval verifies infrastructure and physical citations, not quality. No external provider/Judge/account API occurs here.
