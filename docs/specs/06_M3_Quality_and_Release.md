# M3 — Quality Optimization & Open Source Release

Status: COMPLETE — local open-source release candidate accepted on 2026-09-17. This is the complete M3 scope; stop after acceptance, no M4. See [acceptance](../reports/M3_ACCEPTANCE.md) and the sealed source manifest.

## Frozen inputs and quality discipline

Use `public-standards-v1` unchanged (SHA-256 `3769061016dc8b6ec0009a03e6510fa0722e437a60f10e5011799f1a32c16476`). Baseline EvalRun `a32e838b-b5c2-4a6c-b8e7-7aabf2e8f944` and its saved artifact remain historical records. Import the two submitted Dev assets byte-for-byte and preserve AI-assisted provenance. Validate all 24 memberships, run IDs, frozen question/hash and MD/JSON conclusions before one atomic non-overwriting database transaction. No Test labels.

Tune on Dev only. At most six main candidate experiments, each registered before execution with category, hypothesis, single controlled change, metrics and KEEP/REJECT. Instrumentation, rubric calibration and bug fixes do not count as retrieval candidates. Freeze selected configuration and pass regression gates before the one formal frozen Test comparison. Test is not a parameter-search loop. If bounded experiments cannot establish a reliable improvement, keep M2 and report M3 QUALITY GATE NOT MET.

## Evaluation semantics

Retain legacy @6/@20/@40 metrics; add Hit@5 and Recall/MRR/nDCG @5/@10/@20 using stored stage identities. Undefined denominators stay null. Record actual reranker input, rather than assume raw RRF top 20 after candidate transformations. Gold overlap is finite annotation coverage, not semantic sufficiency. Physical grounding independently resolves immutable PDF/span/boxes. Semantic support must assess factual claims against their cited evidence; do not relabel structural precision as semantic precision.

Human/Judge analysis: exact agreement, disagreement IDs, confusion matrix, by question type and explicitly defined refusal subgroup. Version any revised rubric. Rejudge preserved answers in a separate durable Dev evaluation with the same query IDs, independent cost reservation and no overwrite of previous Judge outputs. Human labels never appear in Judge input. Use the same revised rubric for baseline and candidates. Report both old and calibrated comparisons; these are small-set calibration results, not universal Judge accuracy.

## Configuration and experiments

Allowlisted immutable query profiles are captured by each query and evaluation. M2 remains replayable. Keep line-based immutable chunk IDs, E5-small embedding, version-scoped BM25, RRF k=60, BGE reranker, 40-per-branch recall and 20 reranker slots. New profile selection participates in idempotency; evaluation captures profile and prompt hashes and refuses drift.

C1 first hypothesis: repeated identical text within the same document version consumes RRF's 20 reranker slots. Deduplicate normalized whitespace within that version before cutoff, preserving the first RRF occurrence and logging duplicate-of and actual reranker-input rank. Do not merge different versions or alter citation identity. Primary: reranker-input gold coverage; watch final coverage, answer completeness/correctness, faithfulness, citation grounding, cost and latency. C1 changes only candidate deduplication; final budget and answer-v1 stay unchanged.

Further experiments require evidence from preceding Dev traces. Adjacent line context may be tested if fragmentation persists, preserving each original span rather than changing the indexing contract. Prompt changes require sufficient supplied support and remain a separate experiment. No benchmark IDs, frozen answers or gold text enter production retrieval logic.

## Release and regression boundary

Preserve all M1/M2 reliability, recovery, scope, fencing, cancellation, budget and physical-citation tests. Complete clean installation/migration/startup/build and generated API contract checks. Prepare README, architecture/API/operations/evaluation/benchmark/limitations/provenance, original demo, license inventory/SBOM, secret scan and an explicit public candidate manifest. Exclude .env, private audit, runtime databases, downloaded PDF originals, model weights and caches. Publicly downloadable does not establish redistribution permission.

Release positioning: production-oriented single-user local alpha. No claims of enterprise readiness, general accuracy, QPS, independent annotation or exactly-once. No new OCR/Agent/MCP/RBAC/cloud infrastructure. Complete local release candidate before requesting any new remote publication authorization.

## Accepted outcome

C1 dedup and C3 answer-v2 were rejected. C2 bounded same-page/version original context is the default, retaining the original six seeds, answer-v1, E5/BM25/RRF/BGE and candidate budgets. Judge-v4 was calibrated only on Dev; C2 was independently repeated, regression-tested and source-frozen before one formal Test comparison. Test validation failures, semantic citation limits and latency/cost tradeoffs remain visible. The final archive contains the explicit scanned source set, original demo, evidence reports and notices; remote publication has not occurred.
