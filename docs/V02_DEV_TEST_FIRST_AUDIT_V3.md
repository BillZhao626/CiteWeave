# v0.2a DEV v3 — Targeted Test-first re-audit

Status: **V02A_DEV_TEST_FIRST_READY_FOR_HUMAN_FREEZE** · 2026-10-01. This is readiness for Human review, not Human Gold approval. DEV/HARD/REG NOT_RUN; provider/model/Judge calls 0. No paid execution authorization is addressed.

Current proposal: `citeweave-v02a-development-v3`, version 3, SHA256 `a01953930e2893065dc6f724b6ce896015124744d6614ac14a6354f087636023`. The [complete unsigned 12-view review](V02_DEV_DATA_REVIEW.md) includes all prefixes, states, questions, sources, scopes, history groups, interpretation references/hashes, support spans, assertions and owner fields.

## Owner clarification and minimal revision

The Owner resolves only D1.V2: **topic_relation = return**. Topic relation describes movement relative to current conversational focus. Pending/active Working State describes continued availability of accepted semantic state. These are separate dimensions: T1/T2 leave D1 valid/pending; T3 changes focus to tray-display; the target explicitly names D1-task inspection and returns to it.

V2 remains byte-preserved: [manifest](../evals/citeweave-v02a-development-v2.json), SHA256 `3b1ef5dc37376cf26b5fb20aa8367d76ed2af5ccf376a312a62fc2d6dbcd20a7`; [review surface](V02_DEV_DATA_REVIEW_V2.md), [delivery](V02_DEV_READINESS_V2.md), [original audit with REVISE conclusion](V02_DEV_TEST_FIRST_AUDIT.md). V1 and its REVISE history also remain preserved. Owner clarification is not full-dataset approval.

V3 changes only D1.V2 `topic_relation`, its reference explanation and corresponding existing behavior assertion, and its view hash. Manifest ID/version/schema/predecessor/clarification/hash update mechanically. Other 11 view objects and hashes, all seven source/version bytes, question wording, Ferrule-Q facts, nine-minute reference answer, support offsets, required/irrelevant history, State eligibility, scope and category membership are identical to v2. Existing proposal regeneration rejects different bytes for an already existing v3 path; historical identities cannot be run through the current loader.

## Targeted arm-independent requirements and consistency

| View | Current focus → target | Topic label | Required semantic information | Independent pass/fail | Decision |
| --- | --- | --- | --- | --- | --- |
| D1.V1 | D1 retained by T2 → D1 | continue | Accepted Ferrule-Q selection and current authorized cooldown evidence | Pass: correct entity, nine minutes, no unrelated standby fact. Fail: guessed/wrong entity, four minutes, unsupported answer or incorrect topic label | KEEP, unchanged |
| D1.V2 | T3 tray-display → explicitly named D1 | return | Still-valid D1/Ferrule-Q intent from available accepted provenance or active bounded State; current cooldown evidence | Pass: return label, Ferrule-Q, nine minutes, current Evidence only; available State stays independently valid. Fail: continue label, Tray-R/four minutes, invalidated/guessed intent, State promoted to Evidence or raw coverage | KEEP for Human review |
| D3.V1 | display focus → explicitly returned D3 latch task | return | Still-active latch/release amber intent and current alignment evidence | Pass: return, amber/three-notch, current Evidence only. Fail: display inheritance, guessed/incorrect release, false raw/B credit for State | KEEP, unchanged |

These requirements remain valid with arm names hidden. D1.V2 no longer conflates task validity with conversational continuity. D1.V1 genuinely has no intervening focus change; D3.V1 uses the same focus-relative return definition as corrected D1.V2. Accepted effective semantic state may remain available across that focus movement in these authored prefixes; this does not assert that all topic-local state in arbitrary conversations survives every shift. No new material inconsistency is found in this targeted re-audit. Other KEEP views were not reopened; exact equality checks verify no changes to them. The same-author/known-arm limitation and finite synthetic coverage findings of the v2 audit remain.

## Structural mapping remains unchanged

| D1.V2 arm | Existing structural result | Topic / State / attribution |
| --- | --- | --- |
| cp-r-v1 | interpretation_source_unavailable | No old T1 or State; cannot establish the inherited entity. No successful interpretation label or answer is invented |
| cp-a-v1 | State-only evaluation answer, not product Acceptance | Interpretation reference now return; active Ferrule-Q item used, no deactivation, no T1 raw input, no old-raw/B credit; factual answer uses current EvidencePack |
| cp-ab0-v1 | Complete B-recovered original source and documentary answer | Interpretation reference now return; T1 B attribution and current Evidence unchanged. Existing acceptance preserves valid Ferrule-Q State while recording return |

No production History/Interpretation/State/Evidence/Runtime behavior or prompt is changed. A remains an explicitly unpublished evaluation artifact; AB0 uses the existing product acceptance seam. The known capability difference comes from information availability, not a desired winner. No real performance is inferred from gold-derived fake outputs.

## Provider-free validation and stop

Focused readiness tests: **48 passed**. Final real UUID-isolated PostgreSQL tests: **9 passed**, zero skips/failures. The ninth test directly verifies D1.V2 AB0 durable return, B old-source recovery and active Ferrule-Q state. A PG checks verify return with active State, no old raw read and zero product publication. DTO tests verify unchanged R/A/AB0 statuses and State/raw/B separation across D1.V1, D1.V2 and D3.V1. These are L1 structural tests, not DEV; no actual model, provider, Judge, E5/BGE or Qdrant call.

Initial new version test failed against v2 before implementation, as intended; it is not counted as passing evidence. Manifest/source checks verify v2 bytes, all eleven unchanged views, exact support and sources, v3 identity and hashes. Complete-reference preparation regenerated only fake DTO specimens/unsigned review, with no provider construction or execution authority. Interpretation references change only for successful D1.V2 A/AB0; R still has no successful draft. Unchanged views retain exact DTO reference hashes. Production/prompt/lockfile and accepted protocol checks remain unchanged. No sealed content was accessed. Only project PostgreSQL was briefly started for own UUID test databases and stopped again; configured application DB and old RAGFlow resources were untouched.

Owner must review the complete 12-view surface and fill decisions, identity/date, exact hashes, reasons and actual workload. Existing cumulative review accounting is preserved without reset. No Human Gold signature is supplied by the assistant. If a later defect is found, preserve v3 and its results, create a new version/hash, and obtain review; do not mutate the accepted identity based on DEV outcomes. Stop here for Human freeze review.
