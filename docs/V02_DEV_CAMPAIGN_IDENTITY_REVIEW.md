# DEV campaign identity repair — paid admission rejected

Status: **V02A_DEV_EXECUTION_NOT_STARTED**. Provider-free repair candidate; conditional paid eligibility **FAIL**. Human authorization allows evaluation-only repair, but expressly requires frozen request bytes, hashes and tokenizer measurements. No new HUMAN campaign, authorization or provider dispatch was created.

Starting accepted Observation repair: commit `be12e0797b7908cd42ba03aa53e079593db053f4`, tree `3a2ae99a176edcbebe566f2696cc40a51d5562a8`. New exact commit/tree and full local evidence are recorded after commit in ignored `.runtime/evaluation/campaign-identity-repair/candidate.json`. This candidate is not a paid execution result or an accepted change to the frozen request contract.

## Collision repair and its limit

`RealDevBackend` / `PgBackend` accept an optional campaign UUID. The paid launcher passes its durable policy campaign ID. The evaluation conversation key combines this UUID and a digest of the existing semantic key; repeated resolution within one campaign remains stable. Unscoped local callers retain their existing key construction. Shared Conversation/Acceptance code, prompts, retrieval, DTOs and migration0012 are unchanged. [ADR0013](adr/0013-dev-campaign-execution-namespace.md) records the decision, alternatives and zero migration impact.

All 24 A/AB0 cases resolve distinct conversations across campaigns and stable identities within a campaign. Cases with target product Runs receive separate Run IDs. State-only A and its pre-provider guard preserve their no-target-Run/no-product-Acceptance boundary. The old FAILED target is not reopened; same-campaign FAILED recovery still rejects retry. Existing durable campaign/provider regressions retain UNKNOWN and no-redispatch behavior.

However, a new conversation seeds new prefix Turn/Acceptance/State UUIDs. These are serialized in interpretation history and working state; they are not merely local execution metadata. With identical prompts, questions and non-UUID data, the production serializer therefore produces different request bytes. UUID normalization in the counterexample is diagnostic only and is never used for dispatch or validation.

The final provider-free D1.V1/A counterexample uses the pinned official offline tokenizer and the original output reserve1561:

| Specimen | Input tokens | Production request SHA256 |
| --- | ---: | --- |
| Frozen accepted | 1811 | `3aa1e273d7e1b0be8a1ed03845fa18816d77e5f74438a65541a3ebf3bc74e56a` |
| Isolated test campaign 1 | 1815 | `717db9ea859c034571850eaaed8e5f5ef2be0b956bf09c0c83328470d2042e41` |
| Isolated test campaign 2 | 1824 | `61cab3e70b0e39628d4ecff0520baa84260837e3a4e9d3dabcf6364a59b1d890` |

These synthetic execution UUIDs and measured counts are counterexamples, not new frozen specimens or replacement bounds. Earlier isolated samples1818/1826 likewise differed. Random UUID tokenization prevents inferring a safe constant from one sample. Conditional authorization requirements5–7 cannot be proven; the explicit HUMAN_STOP for changing request bodies/hash/token bounds applies before any paid dispatch. No hash, reserve or allowance was rewritten.

## Preservation and verification

Read-only audits verify all seven accepted PG/Qdrant/blob bindings and physical citation spans, accepted0012 function definitions, Gold/dataset hashes and the application database at0005/28 versions. Full historical campaign/UNKNOWN phase/case rows match preserved terminal evidence. All DEV Conversation/Turn/Run/Acceptance rows are snapshotted before and after regression checks. There is one historical HUMAN campaign, zero ACTIVE HUMAN campaigns and one historical ProviderPhase; no new rows were added to that runtime.

Historical campaign `73bd8f72-dcda-4c79-8458-d19e3a5da07e`, UNKNOWN phase `5c649ca0-b6a7-4a26-92c5-2bdfe1fc0b59` and FAILED Run `cc869813-1d8f-404d-82c1-9dc60d7d268a` remain evidence. Historical actual usage/bill remains unavailable, with unresolved exposure≤0.016110 CNY; it is never counted as zero or reused as a completed output.

The frozen38 slots and proposed ceilings remain calls38/input6196897/output777079/total6973976/CNY18.610426; historical exposure would make cumulative maximum18.626536. No new positive grant was constructed. New-task physical provider/model/Judge calls0, provider input/output0/0, new spend0 CNY. Offline tokenizer counts are not provider usage. The modified evaluation file changes the candidate runtime fingerprint; old candidate config receipts are not falsely reused.

Focused regression: **300 passed, zero failures/skips**, including26 new isolation/counterexample cases and normal non-DEV Conversation tests. Release backend452 passed/353 integration deselected; frontend41 passed/5 files. Ruff lint/format235 files, generated contracts, frontend lint/typecheck/build all passed. Counts overlap; deselection is not PASS. Full validation is recorded in the ignored `release.log`; no live model/provider, real answer quality or real billing is established by these tests. Test databases are disposable; the accepted isolated runtime and normal application database were read-only. Only the approved project PostgreSQL/Qdrant services were started; unrelated/RAGFlow resources remain stopped and preserved.

One audit script initially queried a nonexistent `mode` column; corrected to the durable policy JSON field and rerun read-only. The failed query created no campaign, phase or provider side effect. Existing warnings and release deselections remain explicitly recorded. No push/PR/merge/tag/release or #5d implementation.

## Human decision needed

Proceeding requires a reviewed resolution of campaign isolation versus frozen wire provenance identity. Reusing the old conversation, remapping serialized SourceRefs, or changing immutable prefix ownership would not satisfy the current conditions. This task does not choose or authorize such a contract change. No real24-target output packet exists, no winner is inferred, and spending remains stopped.
