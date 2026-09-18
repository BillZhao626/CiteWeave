# M3 — quality re-evaluation (owner requested)

Status: IN PROGRESS. This continues M3; it is not M3.1/M4. No remote publication is authorized. Historical 0.3.0-alpha.1 reports/artifacts/manifest/archive remain unchanged; new reports go in `docs/reports/m3-revisit/`. The old M3 Test is now a regression set, not a pristine holdout.

## Verified starting point

`baseline-audit.json` verifies the sealed archive and protected historical bytes, selected Dev/Test results and the actual pipeline. Dev initial / actual reranker input / final gold coverage is .64815476 / .27464286 / .53583333. Current parser produces 869 glyph-line Blocks and exactly 869 children; maximum Block length is 129, so every current Block has one child. The 160-codepoint maximum is not the observed average chunk size. Overlap is zero. C2 expands neighboring original spans after retrieval; it is not formal Parent-Child chunking.

RRF combines two per-version lists for each document then keeps a global 20. This discards original gold candidates before BGE can rank them. C1 exact dedup was already rejected and will not be renamed or repeated. Stage loss and answer root cause remain distinct and categories are nonexclusive.

## Bounded experiment plan

1. **R1 — reranker candidate budget 20 vs 40.** Start from C2; change only the bounded RRF cutoff. Keep per-version Dense/BM25 40, BGE model, six seeds, C2 context caps, answer-v1 and Judge-v4. Batch the 40 inputs through the existing maximum-20 gateway; measure actual calls, stage coverage, rankings, end-to-end scores and GPU/RAM. Reject if extra input fails to improve useful coverage/answers or introduces unacceptable regressions/cost.
2. **R2 — paragraph projection as parent.** Compare with the same C2 retrieval/candidate settings. Native line Blocks cannot provide more context on this corpus. Build a query-independent bounded paragraph projection from immutable Blocks using line geometry and visible boundary cues, preserving child IDs and physical evidence. Parent groups and their member support spans are different objects; never cite a synthetic parent as if it were an original span. Cap parent/total characters and member counts. No parser or chunk identity rewrite. Record heuristic ambiguities.
3. **R3 — E5-small vs BGE-M3, Dense only.** Same corpus/children, BM25/RRF/BGE reranker/candidate/context/prompt/Judge/Dev. Use pinned BGE-M3 revision `5617a9f61b028005a4858fdac845db406aefb181`, 1024-dimensional normalized Dense output, no sparse or multi-vector. Keep the old E5 index; create independently owned collections. Measure real indexing/storage/query/VRAM/RAM and quality, not model-card leaderboard claims.
4. A fourth main experiment is optional only if Dev evidence supports generic routing or a controlled combination of individually supported changes. No per-case IDs/labels/gold enter query behavior. No automatic prompt replacement.

Each experiment is registered before execution with hypothesis, constants, budget, artifacts and KEEP/REJECT; validation repeats are recorded separately. Selection uses Dev; old Test is checked after selection. A new source/question dataset must be frozen before final candidate selection, with source hashes, exact gold spans, answerability/type and AI-authored provenance. Holdout results remain unopened until candidate freeze. Without credible independent Gold, report the procedural holdout and its annotation limitations rather than claim unbiased generalization.

## Engineering boundary

Preserve the normal API contracts, PostgreSQL authority, immutable evidence, fenced index publication, current active version/index bindings, Celery recovery, bounded calls and lifecycle tests. Experimental embedding indexes never replace the active E5 index. Keep the stable default while evaluating opt-in profiles. Run new gates to separate report paths so historical M3 records are not overwritten.

M0 selected E5-small as the first resource-controlled local baseline; it did not compare against BGE-M3. BGE-M3 is an embedding model; the existing BGE reranker is a different component. Official model-card reference: https://huggingface.co/BAAI/bge-m3 (SentenceTransformers supports Dense-only use; no query instruction prefix). Technical-history assertions about old employer/lab projects remain unverified unless supported by already-authorized non-private records; do not reread their source for this implementation.

Final output: funnel/root causes, experiment decisions, E5/BGE and C2/parent comparisons, Dev/regression/holdout results, resource costs, architecture/resume fact table, limitations and release recommendation. Stop at completion.
