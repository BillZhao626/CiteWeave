"""Render the final quality report from preserved paired comparison artifacts."""

import json

from citeweave.settings import ROOT


def read(name):
    return json.loads((ROOT / "docs/reports" / (name + ".json")).read_text(encoding="utf-8"))


def metric(value):
    return "unavailable" if value["mean"] is None else f"{value['mean']:.4f} (n={value['denominator']})"


def main():
    reports = {split: read("m3-selected-" + split) for split in ("dev", "test")}
    lines = [
        "# M3 benchmark — quality freeze and formal Test",
        "",
        "Selected: `m3-context` (C2), `answer-v1`, `judge-v4`. Three controlled candidates; C1/C3 rejected. Dev repeat and all regression gates passed before the formal Test freeze. No Test-driven tuning followed.",
        "",
        "## Scope and method",
        "",
        "Three historical English standards PDFs (RFC 2119, RFC 3339, NIST SP 800-145), 27 physical PDF pages, 869 immutable line chunks; 48 Chinese questions, 24 Dev/24 frozen Test. Each split has 20 answerable and four unanswerable questions. Not a Chinese-document business-accuracy benchmark. The original Chinese handbook separately verifies the product path.",
        "",
        "Frozen dataset SHA-256: `3769061016dc8b6ec0009a03e6510fa0722e437a60f10e5011799f1a32c16476`. Original questions/reference/gold and submitted human labels were not modified. Both sides use identical immutable versions/index bindings and the same v4 rubric hash. Baseline answers are the actual M2 outputs, independently rejudged in separate EvalRuns; replay does not regenerate them.",
        "",
        "Hit@K means at least one annotated gold identity; Recall@K measures the fraction of finite gold identities. MRR and binary-relevance nDCG use saved rank order. Stage coverage separates initial union, actual 20-item reranker input and final evidence. Partial gold is not no recall; full finite-gold coverage alone is not proof of semantic sufficiency.",
        "",
        "Answer scores use {0, .5, 1}. v4 scores exact whole-answer refusal deterministically against frozen corpus answerability, and sends other answers to DeepSeek Flash (thinking disabled, max_tokens 1024, default sampling). Factual sentence units can cite only labels attached to that original sentence. This validates citation structure; semantic support remains a fallible LLM judgment. Missing/failed judgments stay unavailable. Different denominators are visible.",
        "",
        "## Human reference and attribution",
        "",
        "Owner-submitted AI-assisted material review: 7 correct complete, 1 partial, 16 incorrect/unjustified refusal; 24/24 matched the same M2 run and Dev split. v1 agreement 21/24 (87.5%), disagreements 005/011/035. v2 and v3 were rejected; v4 pipeline agreement 24/24 comprises 20 deterministic refusals and only 4 LLM-assessed factual answers. This is small-set calibration, not universal or independent-human Judge accuracy. Confusion matrices, question-type and refusal-group definitions are in the human/Judge JSON reports.",
        "",
        "Nonexclusive baseline Dev observations: no initial recall 0; candidate/fusion loss 17; evidence-selection loss 3; reviewed sufficient-context generation error 2; incomplete answer 1; improper refusal 16; semantic citation error 2; physical citation error 0. The 17 candidate losses are measured stage losses, not 17 independently proven root causes. Categories overlap. See `reports/m3-dev-attribution.json`.",
        "",
        "## Controlled experiments",
        "",
        "| Candidate | Single change | Decision and evidence |",
        "|---|---|---|",
        "| C1 | Same-version whitespace-exact dedup before unchanged top 20 | REJECT: duplicate slots freed, gold coverage unchanged; 2 correctness losses and 1 unavailable pair |",
        "| C2 | Add bounded geometric neighbors to six final seeds | KEEP: final Dev coverage .2383 → .5358 in two runs; no correctness loss vs M2 in either run |",
        "| C3 | Only answer-v2 prompt over C2 evidence | REJECT: two query citation-validation failures, lower completeness/faithfulness; return to answer-v1 |",
        "",
        "C2 preserves E5-small, Chinese BM25, RRF k=60, BGE reranker, 40 per retrieval branch and 20 reranker slots. It expands same-page/version original spans within three neighbors, capped at 30 spans/3200 codepoints and geometric distance. This repairs fragmented context without reindexing or synthesizing citation text. First C2 correctness/completeness .6522 (n=23); independent repeat .5833 (n=24). The repeat is the selected Dev result below; the difference is disclosed model variation, not cherry-picked away.",
    ]
    for split, report in reports.items():
        old, new = report["baseline"], report["candidate"]
        lines += [
            "",
            "## " + split.title(),
            "",
            f"Baseline EvalRun `{report['baseline_id']}`; candidate `{report['candidate_id']}`.",
            "",
            "| Metric | M2 / v4 | C2 / v4 |",
            "|---|---:|---:|",
        ]
        for group, keys in (
            ("evidence", ("initial", "rerank_input", "final")),
            ("answer", ("correctness", "completeness", "faithfulness", "relevancy", "refusal_correctness")),
        ):
            lines += [
                f"| {group}.{key} | {metric(old[group][key])} | {metric(new[group][key])} |" for key in keys
            ]
        for key in ("precision", "recall"):
            lines.append(
                f"| finite-gold citation {key} | {metric(old['citation'][key])} | {metric(new['citation'][key])} |"
            )
        for side in (old, new):
            c = side["citation"]["micro_grounded"]
            side["physical_display"] = f"{c['passed']}/{c['count']}"
        lines += [
            f"| Physical PDF grounding | {old['physical_display']} | {new['physical_display']} |",
            f"| Semantic sentence-unit support | {metric(old['semantic_citation']['support'])} | {metric(new['semantic_citation']['support'])} |",
            f"| Cited factual-unit fraction | {old['semantic_citation']['cited_claim_fraction']:.4f} | {new['semantic_citation']['cited_claim_fraction']:.4f} |",
            f"| Query p50 / p95 ms | {old['latency_ms']['p50']:.0f} / {old['latency_ms']['p95']:.0f} | {new['latency_ms']['p50']:.0f} / {new['latency_ms']['p95']:.0f} |",
        ]
        paired = report["paired"]["correctness"]
        lines += [
            "",
            f"Paired correctness: {paired.get('win', 0)} wins / {paired.get('tie', 0)} ties / {paired.get('loss', 0)} losses / {paired.get('unavailable', 0)} unavailable. New correctness/completeness/faithfulness regression IDs among comparable pairs: `{report['new_regression_ids']}`.",
            "",
            "| Stage | Hit@5 | Recall@5 | Recall@10 | Recall@20 | MRR@20 | nDCG@20 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for stage in ("dense", "bm25", "rrf", "reranked"):
            values = new["retrieval"][stage]
            cells = [
                metric(values[str(k)][m])
                for k, m in (
                    (5, "hit"),
                    (5, "recall"),
                    (10, "recall"),
                    (20, "recall"),
                    (20, "mrr"),
                    (20, "ndcg"),
                )
            ]
            lines.append("| " + stage + " | " + " | ".join(cells) + " |")
        lines += [
            "",
            "Retrieval-stage ranks/coverage are unchanged from M2 for the selected profile; only final context changes. API estimates in CNY:",
            "",
            f"- Source M2 query estimate {old['cost']['query_known_estimated_yuan']:.8f}; incremental baseline rejudge {old['cost']['judge_known_estimated_yuan']:.8f}.",
            f"- C2 query estimate {new['cost']['query_known_estimated_yuan']:.8f}; C2 Judge {new['cost']['judge_known_estimated_yuan']:.8f}. Actual provider debit unavailable.",
        ]
    lines += [
        "",
        "## Test failures, tradeoffs and release judgment",
        "",
        "Test queries succeeded 24/24 on both sides. Baseline Judge 016 and candidate Judge 024/046 failed `judge_uncited_claim_support`: the model assigned positive support to an uncited factual unit. They remain failed and were not retried or manually relabeled. Paired comparison therefore has three unavailable cases. Across all 24 questions, treating missing correctness scores anywhere in [0,1] gives baseline [.3125,.3542], candidate [.6458,.7292]; this sensitivity interval is not a confidence interval or a replacement score.",
        "",
        "Test finite-gold citation precision decreases .7500 → .6556 while finite-gold recall increases .1283 → .4525; extra valid contextual citations can be outside the finite gold annotation. Semantic support increases .625 → .825 but cited-unit fraction decreases .875 → .85, with different factual-unit counts. Three candidate factual units are judged unsupported; exact PDF positioning does not establish truth. No claim of perfect semantic citations is made.",
        "",
        "Test p95 rises 1829 → 3538 ms, with one bounded model-connection retry visible in case 008 (5205 ms total). More context increases binding/token work; historical baseline and candidate timing are not a randomized simultaneous performance experiment. All Test queries remain below the configured deadline. Query/Judge estimates are still small relative to the configured CNY 50 monthly budget, but provider actual bills and account-external usage are not observed.",
        "",
        "The bounded quality gate is met for this corpus: deterministic final coverage improvement on Dev repeat and held-out Test, paired answer gains without observed comparable answer regressions, all physical citations valid, and disclosed semantic/latency limits. Retain C2; stop tuning. Release readiness additionally depends on the separate regression, clean-install, licensing and source-candidate gates.",
        "",
        "Reproduction: preserve `reports/m3-experiments.json`, `m3-quality-freeze.json`, `m3-selected-dev.json`, `m3-selected-test.json`, and rejected candidate reports. Run `python scripts/report_m3.py` to render this document from preserved comparisons. For a new experiment, see M3_EVALUATION.md; stochastic answers and API costs will not reproduce byte-for-byte.",
    ]
    (ROOT / "docs/M3_BENCHMARK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("M3 benchmark rendered from preserved comparisons")


if __name__ == "__main__":
    main()
