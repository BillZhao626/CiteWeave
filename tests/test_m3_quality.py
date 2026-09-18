import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.human import validate_reviews
from citeweave.evaluation.judge import answer_units, assess_answer, validate_judgment
from citeweave.evaluation.metrics import ranking_metrics
from citeweave.profiles import candidate_cutoff, expand_context, query_profile
from citeweave.settings import ROOT


def test_dedup_recovers_budget_without_merging_versions_or_rewriting_ids():
    ranked = [("a", 1), ("b", 0.9), ("c", 0.8), ("d", 0.7)]
    traces = {
        i: dict(document_version_id=v, text=t)
        for i, v, t in [
            ("a", "v1", "Header   repeated"),
            ("b", "v1", "Header repeated\n"),
            ("c", "v2", "Header repeated"),
            ("d", "v1", "Useful unique fact"),
        ]
    }
    assert candidate_cutoff(ranked, copy.deepcopy(traces), 3, False) == ranked[:3]
    assert candidate_cutoff(ranked, traces, 3, True) == [ranked[i] for i in [0, 2, 3]]
    assert traces["b"]["duplicate_of"] == "a"
    assert traces["d"]["rerank_input_rank"] == 3
    assert "rerank_input_rank" not in traces["b"]
    assert ranking_metrics(["a"], {"a", "d"}, 5)["hit"] == 1
    assert ranking_metrics(["a"], {"a", "d"}, 5)["recall"] == 0.5


def review_fixture():
    folder = ROOT / "evals/reviews/m2-dev-24"
    document = json.loads((folder / "M2_Dev24_人工复核_标签.json").read_text(encoding="utf-8"))
    markdown = (folder / "M2_Dev24_人工复核_已填写.md").read_text(encoding="utf-8")
    dataset, digest = load_dataset()
    run = document["run_id"]
    artifact = dict(
        evaluation=dict(id=run, dataset_hash=digest),
        cases=[
            dict(eval_run_id=run, case_id=c["case_id"], result=dict(question=c["question"], split=c["split"]))
            for c in dataset["cases"]
        ],
    )
    return document, markdown, dataset, digest, artifact


def test_review_rejects_test_duplicate_wrong_run_hash_and_md_conflict():
    args = review_fixture()
    assert len(validate_reviews(*args)) == 24
    for field, bad in [("run_id", "other"), ("dataset_sha256", "0" * 64), ("split", "test")]:
        modified = copy.deepcopy(args)
        modified[0][field] = bad
        with pytest.raises(ValueError):
            validate_reviews(*modified)
    for bad in ["002", "003"]:
        modified = copy.deepcopy(args)
        modified[0]["reviews"][0]["case_id"] = bad
        with pytest.raises(ValueError, match="membership"):
            validate_reviews(*modified)
    with pytest.raises(ValueError, match="markdown_label"):
        validate_reviews(
            args[0], args[1].replace("- 总体结论：错误或不当拒答", "- 总体结论：正确完整", 1), *args[2:]
        )


def test_judge_claims_cannot_fabricate_answer_or_citation_labels():
    result = dict(answer=dict(text="Fact [E1]", citations=[dict(label="E1")]))
    base = dict(
        correctness=1,
        completeness=1,
        faithfulness=1,
        relevancy=1,
        refusal_correctness=1,
        verdict="correct_complete",
        reason="fixture",
        claims=[dict(claim="Fact", evidence_labels=["E1"], support=1)],
    )
    assert validate_judgment(json.dumps(base), result, "judge-v2")["claims"][0]["support"] == 1
    for claim in [
        dict(claim="invented", evidence_labels=["E1"], support=1),
        dict(claim="Fact", evidence_labels=["E9"], support=1),
        dict(claim="Fact", evidence_labels=[], support=1),
    ]:
        with pytest.raises(ValueError):
            validate_judgment(json.dumps(dict(base, claims=[claim])), result, "judge-v2")


def test_context_preserves_ids_scope_reading_order_and_bounded_budget():
    def chunk(identity, version="v1", page=0, top=0.2, left=0.1):
        return SimpleNamespace(
            id=identity,
            version_id=version,
            text="x" * 100,
            evidence=dict(start_offset=0, boxes=[dict(page_index=page, top=top, left=left)]),
        )

    seed = chunk("seed")
    pool = [
        chunk("previous", top=0.18),
        seed,
        chunk("next", top=0.22),
        chunk("far", top=0.6),
        chunk("column", left=0.8, top=0.24),
        chunk("wrong-version", version="v2"),
        chunk("wrong-page", page=1),
    ]
    profile = query_profile("m3-context")
    selected, origins = expand_context([seed], pool, profile)
    assert [c.id for c in selected] == ["previous", "seed", "next"]
    assert selected[1] is seed and origins == {"next": "seed", "previous": "seed"}
    selected, _ = expand_context([seed], pool, dict(profile, max_evidence_chars=200))
    assert len(selected) == 2 and sum(len(c.text) for c in selected) == 200


def test_generation_experiment_changes_only_prompt_not_evidence_policy():
    before, after = query_profile("m3-context"), query_profile("m3-answer")
    assert before.pop("answer_prompt") == "answer-v1"
    assert after.pop("answer_prompt") == "answer-v2"
    assert before == after


def test_exact_refusal_uses_frozen_corpus_answerability_without_provider(monkeypatch):
    from citeweave.evaluation import judge

    monkeypatch.setattr(
        judge, "DeepSeekProvider", lambda: pytest.fail("Exact refusal must not incur a model call")
    )
    for answerable in (True, False):
        value = asyncio.run(
            assess_answer(
                dict(answerable=answerable), dict(answer=dict(text="证据不足，无法回答。")), "judge-v4"
            )
        )
        assert value["scores"]["correctness"] == int(not answerable)
        assert value["scores"]["faithfulness"] is None
        assert value["attempts"] == [] and value["estimated_yuan"] == 0
        assert value["method"] == "deterministic_exact_refusal_policy"


def test_numbered_judge_units_cannot_borrow_another_sentences_citation():
    text = "A [E1]。B [E2]。"
    assert [u["attached_labels"] for u in answer_units(text)] == [["E1"], ["E2"]]
    result = dict(answer=dict(text=text, citations=[dict(label="E1"), dict(label="E2")]))
    scores = dict(
        correctness=1,
        completeness=1,
        faithfulness=1,
        relevancy=1,
        refusal_correctness=1,
        verdict="correct_complete",
        reason="fixture",
        claims=[
            dict(claim_index=0, factual=True, evidence_labels=["E2"], support=1),
            dict(claim_index=1, factual=True, evidence_labels=["E2"], support=1),
        ],
    )
    with pytest.raises(ValueError, match="attachment"):
        validate_judgment(json.dumps(scores), result, "judge-v4")
    scores["claims"][0]["evidence_labels"] = ["E1"]
    checked = validate_judgment(json.dumps(scores), result, "judge-v4")
    assert checked["claims"][0]["claim"] == "A [E1]。"
    scores["claims"].pop()
    with pytest.raises(ValueError, match="coverage"):
        validate_judgment(json.dumps(scores), result, "judge-v4")
