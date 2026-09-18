import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from citeweave.embeddings import BGE, E5
from citeweave.m2_api import EvaluationCreate
from citeweave.model_client import ModelGateway
from citeweave.parents import expand_parents, project_parents
from citeweave.profiles import candidate_cutoff, query_profile
from citeweave.schemas import QueryCreate
from citeweave.trace import runtime_config


def test_candidate_budget_is_independent_of_generation_context_and_seed_budget():
    assert (
        QueryCreate(kb_id=uuid4(), question="fixture", profile="m3-candidates40").profile == "m3-candidates40"
    )
    assert EvaluationCreate(kb_id=uuid4(), profile="m3-candidates40").profile == "m3-candidates40"
    baseline, candidate = query_profile("m3-context"), query_profile("m3-candidates40")
    assert candidate.pop("rerank_limit") == 40
    assert baseline == candidate
    assert runtime_config("m3-context")["rerank_limit"] == 20
    assert runtime_config("m3-candidates40")["rerank_limit"] == 40
    assert runtime_config("m3-candidates40")["evidence_limit"] == 30
    ranked = [(str(i), 1 / (i + 1)) for i in range(60)]
    traces = {i: dict(document_version_id="one", text="Original " + i) for i, _ in ranked}
    old = candidate_cutoff(ranked, copy.deepcopy(traces), 20, False)
    new = candidate_cutoff(ranked, traces, 40, False)
    assert old == new[:20] and len(new) == 40
    assert traces["39"]["rerank_input_rank"] == 40
    assert "rerank_input_rank" not in traces["40"]


def test_parent_membership_is_query_independent_bounded_and_keeps_original_children():
    def child(i, top, text="Original supporting sentence", page=0, version="v1", left=0.1):
        return SimpleNamespace(
            id=str(i),
            version_id=version,
            text=text,
            evidence=dict(
                block_id="line-" + str(i),
                start_offset=0,
                boxes=[dict(page_index=page, top=top, bottom=top + 0.01, left=left)],
            ),
        )

    pool = [child(i, 0.1 + i * 0.013) for i in range(8)]
    pool += [
        child("heading", 0.21, "2. New section"),
        child("after", 0.223),
        child("gap", 0.5),
        child("column", 0.51, left=0.8),
        child("page", 0.1, page=1),
        child("version", 0.1, version="v2"),
    ]
    profile = query_profile("m3-parent")
    parents = project_parents(pool, profile)
    assert [p.id for p in parents] == [p.id for p in project_parents(list(reversed(pool)), profile)]
    assert len(next(p for p in parents if pool[0] in p.members).members) == 8
    selected, _, metadata = expand_parents([pool[0]], pool, profile)
    assert selected == pool[:8] and all(a is b for a, b in zip(selected, pool))
    assert metadata[0]["selected_member_ids"] == [str(i) for i in range(8)]
    selected2, _, metadata2 = expand_parents([pool[7]], pool, profile)
    assert selected2 == selected and metadata2 == metadata
    selected, _, _ = expand_parents(
        [pool[0]], pool, dict(profile, max_evidence_spans=3, max_evidence_chars=60)
    )
    assert len(selected) == 2 and sum(len(c.text) for c in selected) <= 60
    assert all(p.version_id == str(p.members[0].version_id) for p in parents)


def test_native_long_block_children_share_parent_without_crossing_caps():
    pool = [
        SimpleNamespace(
            id=str(i),
            version_id="v",
            text="x" * 160,
            evidence=dict(
                block_id="same-original-block",
                start_offset=i * 160,
                boxes=[dict(page_index=0, top=0.1, bottom=0.11, left=0.1)],
            ),
        )
        for i in range(8)
    ]
    parents = project_parents(pool, query_profile("m3-parent"))
    assert [len(p.members) for p in parents] == [5, 3]
    assert all(sum(len(c.text) for c in p.members) <= 800 for p in parents)


def test_dense_model_identity_and_dimensions_are_checked_before_use(monkeypatch):
    class Circuit:
        def change(self, *args):
            return "permit"

    monkeypatch.setenv("CW_ADMIN_TOKEN", "fixture-token-only-not-a-secret-1234")
    from citeweave.settings import settings

    settings.cache_clear()
    sent = []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(200, json=dict(embedding=BGE, vectors=[[0.0] * 1024]))

    gateway = ModelGateway(httpx.MockTransport(handler), Circuit(), embedding_key="bge-m3")
    assert len(gateway.embed(["测试"], query=True)[0]) == 1024
    assert sent[0]["embedding"] == BGE and sent[0]["query"] is True
    wrong = ModelGateway(httpx.MockTransport(handler), Circuit())
    with pytest.raises(ValueError, match="embedding_identity_mismatch"):
        wrong.embed(["text"])
    bad_dimension = ModelGateway(
        httpx.MockTransport(lambda _: httpx.Response(200, json=dict(embedding=E5, vectors=[[0.0] * 1024]))),
        Circuit(),
    )
    with pytest.raises(ValueError, match="model_dimension_mismatch"):
        bad_dimension.embed(["text"])
    settings.cache_clear()


def test_bge_profile_only_changes_dense_identity_not_retrieval_or_answering():
    before = query_profile("m3-context")
    after = query_profile("m3-bge-dense")
    assert after.pop("embedding_key") == "bge-m3" and before == after
    config = runtime_config("m3-bge-dense")
    assert config["embedding_identity"] == BGE and config["dimension"] == 1024
    assert config["reranker"] == "BAAI/bge-reranker-v2-m3"
    assert config["rerank_limit"] == 20 and config["evidence_limit"] == 30
    from citeweave.hybrid import HybridRetriever

    with pytest.raises(ValueError, match="embedding_index_bindings_required"):
        HybridRetriever(index=object(), model=object(), profile="m3-bge-dense")


def test_holdout_rejects_unfrozen_candidate_changed_code_and_unselected_profile(tmp_path):
    from citeweave.evaluation.holdout import HOLDOUT_SHA256, require_selection, runtime_sources

    with pytest.raises(ValueError, match="not_frozen"):
        require_selection("m3-context", "judge-v4", "test", tmp_path)
    (tmp_path / "src/citeweave").mkdir(parents=True)
    source = tmp_path / "src/citeweave/fixture.py"
    source.write_text("fixture = 1\n")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals/m3-revisit-selection.json").write_text(
        json.dumps(
            dict(
                status="FROZEN_BEFORE_HOLDOUT",
                holdout_sha256=HOLDOUT_SHA256,
                selected_profile="m3-candidates40",
                runtime_sources=runtime_sources(tmp_path),
            )
        )
    )
    assert require_selection("m3-candidates40", "judge-v4", "test", tmp_path)
    with pytest.raises(ValueError, match="configuration_not_frozen"):
        require_selection("m3-parent", "judge-v4", "test", tmp_path)
    source.write_text("fixture = 2\n")
    with pytest.raises(ValueError, match="runtime_changed"):
        require_selection("m3-context", "judge-v4", "test", tmp_path)
