# v0.2a DEV v3 — Human Gold freeze record

Status: **V02A_DEV_HUMAN_GOLD_FROZEN** · 2026-10-01. Human Product Owner has manually reviewed all 12 views and reported a second cross-check with no material semantic/test-design blocker. This record transcribes that explicit human decision; the assistant does not invent a personal name, review duration or cryptographic signature.

Frozen dataset `citeweave-v02a-development-v3` / version 3 / complete SHA256 `a01953930e2893065dc6f724b6ce896015124744d6614ac14a6354f087636023`. [Dataset bytes](../evals/citeweave-v02a-development-v3.json) are unchanged, including original PENDING proposal fields. Approval is external: [`citeweave-v02a-development-v3-human-gold-20261001`](../evals/approvals/citeweave-v02a-development-v3-human-gold-20261001.json), SHA256 `df55c120f92ee4998083872cb6bea421101fc1c9eb89c3dd730242b064debd66`. No v4 is created to encode approval.

Decision APPROVE; reviewer role Human Product Owner; review date 2026-10-01; completed **12 LABEL units**. Actual minutes are null / **NOT_MEASURED**; personal name is null / not supplied. Earlier revision-review workload and cumulative units/minutes remain separately unreconciled; no pool reset or invented cross-check units. Output reviews remain NOT_RUN; the approval is data review, not provider-output scoring or money authorization.

| View | Approved SHA256 |
| --- | --- |
| D1.V1 | `29e586f7d151f4b64c132de885ee76a8047c13a4997c3e98eda1c0da58207ca0` |
| D1.V2 | `fc69e5c555e50208af48ca441f78ade5c0b9afb0420a1682c9c23b6e683ee48f` |
| D2.V1 | `b68ea9a6bf3e8bfda7194ccda8a168eb85001d96282f89aaabc6c17fcc3dc2c2` |
| D2.V2 | `a9eecff681ed68fe299e83098ace7c837fa7e3fa42dc18a274025783b6c60810` |
| D3.V1 | `a4435cce8a0dd33c7b4ab5e80347fb288b5394c4f5da85891e970edfc177cdc8` |
| D3.V2 | `7cfa37b07e24ab63e686129f515040a0f4403346ba2c3e28a3decac1e29bf415` |
| D4.V1 | `2dc5fb019aa619a00b5230d1f49f889ec8361a5e4144e266ecda379a772b9fab` |
| D4.V2 | `dc59a5f3f0fba8674391250957198526bcc627decad0aa1fdd3e1bee3f741b57` |
| D5.V1 | `512877045386ca55c62a11d771e9fca3186b910973d23c93d936e119b8d60c8d` |
| D5.V2 | `74332f24aab85f87679a03075dc1127a06e4d7e72b0d63f740fea714c432ba79` |
| D6.V1 | `00b192909e42b21c2f56483362cedf5da6178253ab502d38cb6a806f769db862` |
| D6.V2 | `4ded30175f6b605f22d6b02f9d2595fb4769053f2948a5a5ca3bf8ec91a3dba3` |

## Approved boundaries and caveats

D1.V1 continue; D1.V2 return; D3.V1 return. Current focus movement and accepted pending/active semantic State availability are independent dimensions. Ordinary D1.V2/D3.V1 A State intent remains allowed with zero outside-window raw/B credit, no raw rematerialization, and no Evidence authority. D3.V2 requires the complete T1/T4 atomic correction provenance; State cannot replace it. D4.V2 has no required raw-history denominator. Factual answers require only current authorized EvidencePack; History/State is non-Evidence.

This is a 12-view synthetic Development mechanism/failure-mode set, not population-quality evidence. D6.V1 does not prove real long-conversation semantic performance; capacity remains a separate controlled L1 boundary concern. D3.V2 tests correction/provenance integrity alongside correctness, not generic answer accuracy alone. AI-assisted authorship with known arms plus Human review/Test-first audit does not establish independently blinded data. These accepted caveats do not invalidate Gold.

V1/v2 exact manifests, their REVISE histories and both Test-first audits are preserved. The approval pins exact file hashes for these references. V3 pre-freeze [review](V02_DEV_DATA_REVIEW_V3_PRE_FREEZE.md) and [delivery](V02_DEV_READINESS_V3_PRE_FREEZE.md) are also preserved; [current review](V02_DEV_DATA_REVIEW.md) overlays the attestation on the historical proposal surface.

Future defects require retaining v3 and all its results, recording the defect, authoring a new version/hash and obtaining new Human review. Real DEV results must never mutate approved v3. `owner_review=PENDING` within the immutable original is historical; future admission proves APPROVED using the separate attestation.

## Admission and verification

`dev_approval.load_human_gold` is a small provider-free check: literal Development/dataset/approval identities only, full proposal/view/source/protocol validation, exact pinned approval bytes, APPROVE decision, exact version/hash and all twelve view hashes, reviewed label units/date/role, null unmeasured duration/name, no execution grant, plus literal pinned audit/predecessor references. Unknown IDs/REG/Holdout are rejected before file access; missing/drifted approval, mismatched dataset/view/decision or changed audit references fail closed. It performs no discovery, provider dispatch or production workflow change. A future DEV launcher must call this check and separately prove all execution gates; fake L1 remains explicitly fake.

Validation: new approval/review focused tests 16 passed; final readiness suite **62 passed** (overlaps backend count). Full `scripts/check_release.py`: backend **421 passed, 207 integration deselected**, frontend **41 passed/5 files**, required Ruff **216 files**, lint/format/typecheck/build/OpenAPI/generated types passed. Existing two Python deprecations and Vite >500kB warning remain. Real UUID-isolated DEV PostgreSQL **9 passed**, zero skips/failures; own test databases cleaned, application DB not seeded/migrated, project PG stopped afterward, old RAGFlow resources untouched. An initial PG command named a nonexistent supplemental file and ran no tests; corrected DEV PG suite passed. Initial missing-attestation TDD failure was expected and is not passing evidence.

Final hash/source/runtime/reference/42-file allowlist/secret/local-link/whitespace audits passed. Existing frozen-byte Git attributes were extended only to v1/v2/v3 and approval JSON (`-text`); staged/exported bytes match all four original hashes, preventing Windows checkout newline conversion. No production API/runtime/prompt/ranking/schema/frontend behavior changes; no sealed content accessed. **DEV/HARD/REG NOT_RUN; current-task provider/model/Judge calls=0; spend=0; #5d NOT_STARTED.** No push/PR/merge/tag/release.

## Remaining paid-execution blockers

Gold approval closes dataset-label review only. Live input caps after interpretation, reviewed output reserves/margins, combined deadlines/cancellation/history/context bounds and complete per-Run/Turn/Conversation/stage/campaign calls/tokens/CNY reservations remain unfrozen. Finite new monetary authorization and applicable current account/balance/rate/model/alias/environment bindings remain required. New corpus real READY/index/E5/BGE/Qdrant bindings are not verified. No paid DEV entrypoint/positive policy is installed; State-only A is an unpublished evaluation artifact and its future paid execution/publication boundary still requires review. Actual review minutes/prior cumulative workload require reconciliation; future A/AB0 outputs still need their own Human review. Worst-case agreed DEV exposure remains UNKNOWN. Saved fake accounting/reference maxima and the prior consumed smoke grant authorize none of this.

One local checkpoint commit records the complete frozen Gold/readiness allowlist after validation. Exact commit/tree are reported after commit creation; bind them using `git rev-parse HEAD` / `git rev-parse HEAD^{tree}` rather than embedding a self-referential hash in this file. No further action or paid execution is authorized by this checkpoint.
