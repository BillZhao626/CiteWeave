import hashlib
import json
import math
from types import SimpleNamespace

import pytest

from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.holdout import open_sealed
from citeweave.evaluation.reporting import aggregate
from citeweave.evaluation.support import covered_groups, group_ranking, support_coverage


def atom(start, end, source="a", block="paragraph"):
    return dict(source_id=source, block_id=block, start_offset=start, end_offset=end)


def test_union_across_atoms_and_children_alternates_and_duplicate_credit():
    groups = [
        dict(group_id="rule", alternatives=[[atom(0, 10)], [atom(20, 25)]]),
        dict(group_id="exception", alternatives=[[atom(0, 4, "b")]]),
    ]
    projection = {
        "first": [atom(0, 5)],
        "second": [atom(5, 10)],
        "overlap": [atom(0, 10)],
        "other": [atom(0, 4, "b")],
    }
    score = group_ranking(["first", "second", "overlap", "other"], projection, groups, 3)
    assert score["recall"] == 0.5 and score["mrr"] == 0.5
    assert score["ndcg"] == pytest.approx((1 / math.log2(3)) / (1 + 1 / math.log2(3)))
    assert group_ranking(["first", "second", "overlap", "other"], projection, groups, 5)["recall"] == 1
    assert covered_groups([atom(20, 25)], groups) == {"rule"}
    assert not covered_groups([atom(0, 4), atom(5, 10)], groups)  # one-codepoint hole
    value = support_coverage([atom(0, 10)], groups, [dict(required_groups=["rule", "exception"])], ["a", "b"])
    assert value["required_aspect_coverage"] == 0 and value["required_source_coverage"] == 0.5
    assert group_ranking([], {}, [], 10)["ndcg"] is None


def test_failed_unknown_and_missing_judge_keep_total_without_false_semantic_zero():
    rows = [
        SimpleNamespace(
            case_id=str(i),
            status=status,
            result={},
            judge={},
            human_review={},
            judge_estimated_yuan=None,
            judge_reserved_yuan=0.1,
        )
        for i, status in enumerate(["FAILED", "OUTCOME_UNKNOWN", "CANCELLED"])
    ]
    result = aggregate(rows, durable=True)
    assert result["quality_accounting"]["total_cases"] == 3
    assert result["quality_accounting"]["missing_judgment"] == 3
    assert result["answer"]["correctness"] == dict(mean=None, denominator=0)
    assert result["quality_accounting"]["end_to_end_correctness"] == 0
    assert result["case_status"]["OUTCOME_UNKNOWN"] == 1


def test_visible_dataset_counts_source_identity_and_no_child_gold():
    value, digest = load_dataset("citeweave-public-telecom-eval-v1")
    assert len(value["cases"]) == 72 and len(digest) == 64
    assert value["holdout"]["status"] == "NOT_YET_SEALED"
    assert not value["holdout"]["content_present"]
    assert "child_id" not in json.dumps(value)
    assert all(c["label_origin"] == "AI_source_grounded_not_human_reviewed" for c in value["cases"])


def test_dummy_holdout_requires_freeze_and_single_decision_receipt(tmp_path):
    data = tmp_path / "original-dummy.json"
    data.write_text('{"question":"Original dummy only"}', encoding="utf-8")
    candidate = {
        k: "0" * 40
        for k in ("source_commit", "source_tree", "profile_sha256", "prompt_sha256", "dataset_sha256")
    }
    freeze = tmp_path / "dummy-freeze.json"
    freeze.write_text(
        json.dumps(
            dict(
                status="SEALED",
                candidate=candidate,
                content_sha256=hashlib.sha256(data.read_bytes()).hexdigest(),
            )
        )
    )
    with pytest.raises(ValueError):
        open_sealed(data, freeze, {}, "wrong")
    assert (
        open_sealed(data, freeze, candidate, "original-engineering-check")["question"]
        == "Original dummy only"
    )
    with pytest.raises(FileExistsError):
        open_sealed(data, freeze, candidate, "second-decision-forbidden")
