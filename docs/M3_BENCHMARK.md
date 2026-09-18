# M3 benchmark — quality freeze and formal Test

Selected: `m3-context` (C2), `answer-v1`, `judge-v4`. Three controlled candidates; C1/C3 rejected. Dev repeat and all regression gates passed before the formal Test freeze. No Test-driven tuning followed.

## Scope and method

Three historical English standards PDFs (RFC 2119, RFC 3339, NIST SP 800-145), 27 physical PDF pages, 869 immutable line chunks; 48 Chinese questions, 24 Dev/24 frozen Test. Each split has 20 answerable and four unanswerable questions. Not a Chinese-document business-accuracy benchmark. The original Chinese handbook separately verifies the product path.

Frozen dataset SHA-256: `3769061016dc8b6ec0009a03e6510fa0722e437a60f10e5011799f1a32c16476`. Original questions/reference/gold and submitted human labels were not modified. Both sides use identical immutable versions/index bindings and the same v4 rubric hash. Baseline answers are the actual M2 outputs, independently rejudged in separate EvalRuns; replay does not regenerate them.

Hit@K means at least one annotated gold identity; Recall@K measures the fraction of finite gold identities. MRR and binary-relevance nDCG use saved rank order. Stage coverage separates initial union, actual 20-item reranker input and final evidence. Partial gold is not no recall; full finite-gold coverage alone is not proof of semantic sufficiency.

Answer scores use {0, .5, 1}. v4 scores exact whole-answer refusal deterministically against frozen corpus answerability, and sends other answers to DeepSeek Flash (thinking disabled, max_tokens 1024, default sampling). Factual sentence units can cite only labels attached to that original sentence. This validates citation structure; semantic support remains a fallible LLM judgment. Missing/failed judgments stay unavailable. Different denominators are visible.

## Human reference and attribution

Owner-submitted AI-assisted material review: 7 correct complete, 1 partial, 16 incorrect/unjustified refusal; 24/24 matched the same M2 run and Dev split. v1 agreement 21/24 (87.5%), disagreements 005/011/035. v2 and v3 were rejected; v4 pipeline agreement 24/24 comprises 20 deterministic refusals and only 4 LLM-assessed factual answers. This is small-set calibration, not universal or independent-human Judge accuracy. Confusion matrices, question-type and refusal-group definitions are in the human/Judge JSON reports.

Nonexclusive baseline Dev observations: no initial recall 0; candidate/fusion loss 17; evidence-selection loss 3; reviewed sufficient-context generation error 2; incomplete answer 1; improper refusal 16; semantic citation error 2; physical citation error 0. The 17 candidate losses are measured stage losses, not 17 independently proven root causes. Categories overlap. See `reports/m3-dev-attribution.json`.

## Controlled experiments

| Candidate | Single change | Decision and evidence |
|---|---|---|
| C1 | Same-version whitespace-exact dedup before unchanged top 20 | REJECT: duplicate slots freed, gold coverage unchanged; 2 correctness losses and 1 unavailable pair |
| C2 | Add bounded geometric neighbors to six final seeds | KEEP: final Dev coverage .2383 → .5358 in two runs; no correctness loss vs M2 in either run |
| C3 | Only answer-v2 prompt over C2 evidence | REJECT: two query citation-validation failures, lower completeness/faithfulness; return to answer-v1 |

C2 preserves E5-small, Chinese BM25, RRF k=60, BGE reranker, 40 per retrieval branch and 20 reranker slots. It expands same-page/version original spans within three neighbors, capped at 30 spans/3200 codepoints and geometric distance. This repairs fragmented context without reindexing or synthesizing citation text. First C2 correctness/completeness .6522 (n=23); independent repeat .5833 (n=24). The repeat is the selected Dev result below; the difference is disclosed model variation, not cherry-picked away.

## Dev

Baseline EvalRun `953c5e62-71ae-4393-8e23-89992cb76672`; candidate `b66bab34-b63b-46fe-b33e-f0f116cf65ba`.

| Metric | M2 / v4 | C2 / v4 |
|---|---:|---:|
| evidence.initial | 0.6482 (n=20) | 0.6482 (n=20) |
| evidence.rerank_input | 0.2746 (n=20) | 0.2746 (n=20) |
| evidence.final | 0.2383 (n=20) | 0.5358 (n=20) |
| answer.correctness | 0.3125 (n=24) | 0.5833 (n=24) |
| answer.completeness | 0.3125 (n=24) | 0.5833 (n=24) |
| answer.faithfulness | 0.7500 (n=4) | 0.9167 (n=12) |
| answer.relevancy | 0.6458 (n=24) | 0.8333 (n=24) |
| answer.refusal_correctness | 0.3125 (n=24) | 0.5833 (n=24) |
| finite-gold citation precision | 0.5833 (n=4) | 0.8194 (n=12) |
| finite-gold citation recall | 0.0933 (n=20) | 0.5067 (n=20) |
| Physical PDF grounding | 8/8 | 50/50 |
| Semantic sentence-unit support | 0.8000 (n=5) | 0.9000 (n=25) |
| Cited factual-unit fraction | 1.0000 | 0.9200 |
| Query p50 / p95 ms | 1403 / 1743 | 1916 / 2681 |

Paired correctness: 7 wins / 17 ties / 0 losses / 0 unavailable. New correctness/completeness/faithfulness regression IDs among comparable pairs: `[]`.

| Stage | Hit@5 | Recall@5 | Recall@10 | Recall@20 | MRR@20 | nDCG@20 |
|---|---:|---:|---:|---:|---:|---:|
| dense | 0.1500 (n=20) | 0.0583 (n=20) | 0.1313 (n=20) | 0.2226 (n=20) | 0.1001 (n=20) | 0.1094 (n=20) |
| bm25 | 0.1500 (n=20) | 0.0833 (n=20) | 0.0833 (n=20) | 0.1583 (n=20) | 0.0858 (n=20) | 0.0826 (n=20) |
| rrf | 0.2000 (n=20) | 0.0708 (n=20) | 0.1867 (n=20) | 0.2746 (n=20) | 0.1230 (n=20) | 0.1402 (n=20) |
| reranked | 0.5500 (n=20) | 0.2383 (n=20) | 0.2663 (n=20) | 0.2746 (n=20) | 0.4383 (n=20) | 0.2817 (n=20) |

Retrieval-stage ranks/coverage are unchanged from M2 for the selected profile; only final context changes. API estimates in CNY:

- Source M2 query estimate 0.00640644; incremental baseline rejudge 0.01135896.
- C2 query estimate 0.00918940; C2 Judge 0.02291396. Actual provider debit unavailable.

## Test

Baseline EvalRun `e6aedb3a-5977-4164-988c-1bbd0aca40d9`; candidate `d2c953cc-e6b2-4f65-8fe4-1c650a4f6f4a`.

| Metric | M2 / v4 | C2 / v4 |
|---|---:|---:|
| evidence.initial | 0.6333 (n=20) | 0.6333 (n=20) |
| evidence.rerank_input | 0.2900 (n=20) | 0.2900 (n=20) |
| evidence.final | 0.2227 (n=20) | 0.5083 (n=20) |
| answer.correctness | 0.3261 (n=23) | 0.7045 (n=22) |
| answer.completeness | 0.3261 (n=23) | 0.7045 (n=22) |
| answer.faithfulness | 0.7500 (n=6) | 0.8846 (n=13) |
| answer.relevancy | 0.6739 (n=23) | 0.8636 (n=22) |
| answer.refusal_correctness | 0.3261 (n=23) | 0.7045 (n=22) |
| finite-gold citation precision | 0.7500 (n=7) | 0.6556 (n=15) |
| finite-gold citation recall | 0.1283 (n=20) | 0.4525 (n=20) |
| Physical PDF grounding | 18/18 | 59/59 |
| Semantic sentence-unit support | 0.6250 (n=8) | 0.8250 (n=20) |
| Cited factual-unit fraction | 0.8750 | 0.8500 |
| Query p50 / p95 ms | 1379 / 1829 | 1768 / 3538 |

Paired correctness: 9 wins / 12 ties / 0 losses / 3 unavailable. New correctness/completeness/faithfulness regression IDs among comparable pairs: `[]`.

| Stage | Hit@5 | Recall@5 | Recall@10 | Recall@20 | MRR@20 | nDCG@20 |
|---|---:|---:|---:|---:|---:|---:|
| dense | 0.2000 (n=20) | 0.0505 (n=20) | 0.0505 (n=20) | 0.1910 (n=20) | 0.1237 (n=20) | 0.0979 (n=20) |
| bm25 | 0.4000 (n=20) | 0.1451 (n=20) | 0.1648 (n=20) | 0.2577 (n=20) | 0.2885 (n=20) | 0.1820 (n=20) |
| rrf | 0.3500 (n=20) | 0.1160 (n=20) | 0.1873 (n=20) | 0.2900 (n=20) | 0.1623 (n=20) | 0.1621 (n=20) |
| reranked | 0.6000 (n=20) | 0.2227 (n=20) | 0.2370 (n=20) | 0.2900 (n=20) | 0.5455 (n=20) | 0.3106 (n=20) |

Retrieval-stage ranks/coverage are unchanged from M2 for the selected profile; only final context changes. API estimates in CNY:

- Source M2 query estimate 0.00685850; incremental baseline rejudge 0.00926396.
- C2 query estimate 0.02455300; C2 Judge 0.02831776. Actual provider debit unavailable.

## Test failures, tradeoffs and release judgment

Test queries succeeded 24/24 on both sides. Baseline Judge 016 and candidate Judge 024/046 failed `judge_uncited_claim_support`: the model assigned positive support to an uncited factual unit. They remain failed and were not retried or manually relabeled. Paired comparison therefore has three unavailable cases. Across all 24 questions, treating missing correctness scores anywhere in [0,1] gives baseline [.3125,.3542], candidate [.6458,.7292]; this sensitivity interval is not a confidence interval or a replacement score.

Test finite-gold citation precision decreases .7500 → .6556 while finite-gold recall increases .1283 → .4525; extra valid contextual citations can be outside the finite gold annotation. Semantic support increases .625 → .825 but cited-unit fraction decreases .875 → .85, with different factual-unit counts. Three candidate factual units are judged unsupported; exact PDF positioning does not establish truth. No claim of perfect semantic citations is made.

Test p95 rises 1829 → 3538 ms, with one bounded model-connection retry visible in case 008 (5205 ms total). More context increases binding/token work; historical baseline and candidate timing are not a randomized simultaneous performance experiment. All Test queries remain below the configured deadline. Query/Judge estimates are still small relative to the configured CNY 50 monthly budget, but provider actual bills and account-external usage are not observed.

The bounded quality gate is met for this corpus: deterministic final coverage improvement on Dev repeat and held-out Test, paired answer gains without observed comparable answer regressions, all physical citations valid, and disclosed semantic/latency limits. Retain C2; stop tuning. Release readiness additionally depends on the separate regression, clean-install, licensing and source-candidate gates.

Reproduction: preserve `reports/m3-experiments.json`, `m3-quality-freeze.json`, `m3-selected-dev.json`, `m3-selected-test.json`, and rejected candidate reports. Run `python scripts/report_m3.py` to render this document from preserved comparisons. For a new experiment, see M3_EVALUATION.md; stochastic answers and API costs will not reproduce byte-for-byte.
