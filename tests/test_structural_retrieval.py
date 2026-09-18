import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from uuid import uuid4

import httpx
import pytest

from citeweave import model_client
from citeweave.query_evidence import read_query
from citeweave.retrieval import BM25Encoder, fuse_rrf
from citeweave.schemas import QueryCreate
from citeweave.structural_contract import QUERY_CONTRACT, validate_rerank
from citeweave.structural_retrieval import branches
from citeweave.tokenization import TOKENIZERS
from citeweave.trace import bounded_stage, network_timeout


def response():
    return dict(
        contract=QUERY_CONTRACT,
        tokenizers=copy.deepcopy(TOKENIZERS),
        e5_input=12,
        bge_query=8,
        body_tokens=[20, 30],
        pair_tokens=[32, 42],
        scores=[-0.2, 0.4],
        queue_ms=1.0,
        inference_ms=10.0,
    )


def test_hand_rrf_duplicate_vote_ties_and_build_bm25():
    scores = dict(fuse_rrf([["a", "a", "b"], ["b", "c"]]))
    assert scores["a"] == 1 / 61 and scores["b"] == 1 / 62 + 1 / 61 and scores["c"] == 1 / 62
    assert fuse_rrf([["z"], ["a"]])[0][0] == "a"
    one, two = BM25Encoder.fit(["signal signal", "message"]), BM25Encoder.fit(["signal", "signal"])
    assert one.idf["signal"] != two.idf["signal"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("scores", [float("nan"), 0]),
        ("scores", [0]),
        ("pair_tokens", [513, 20]),
        ("pair_tokens", [20, 20]),
        ("body_tokens", [321, 1]),
        ("bge_query", 129),
        ("queue_ms", -1),
        ("inference_ms", float("inf")),
        ("scores", [True, 0]),
    ],
)
def test_bge_invalid_protocol_fails_closed(field, value):
    body = response()
    body[field] = value
    with pytest.raises(ValueError):
        validate_rerank(body, 2)


def test_pinned_reranker_identity_and_valid_response():
    body = response()
    assert validate_rerank(body, 2)["scores"] == [-0.2, 0.4]
    body["tokenizers"]["bge"]["revision"] = "wrong"
    with pytest.raises(ValueError, match="identity"):
        validate_rerank(body, 2)


def test_legacy_reader_does_not_reinterpret_or_mutate_candidates():
    candidates = [{"candidate_id": "historical-atom", "old_field": 7}]
    row = NS(
        trace_schema_revision="legacy-v1", candidates=candidates, evidence_pack=None, structural_snapshot=None
    )
    assert read_query(row).candidates is candidates
    assert row.candidates == [{"candidate_id": "historical-atom", "old_field": 7}]
    row.evidence_pack = {}
    with pytest.raises(ValueError, match="legacy_trace"):
        read_query(row)


def test_legacy_request_limit_scope_and_new_profile():
    with pytest.raises(ValueError):
        QueryCreate(kb_id=uuid4(), question="x" * 161)
    with pytest.raises(ValueError):
        QueryCreate(kb_id=uuid4(), question="q", document_ids=[uuid4()])
    assert (
        len(QueryCreate(kb_id=uuid4(), question="x" * 512, profile="telecom-structural-v1").question) == 512
    )


def test_qdrant_actual_global_concurrency_and_shared_failure():
    snapshot = NS(bindings=[NS(version_id=str(i), index_name=str(i)) for i in range(5)])
    encoder = BM25Encoder.fit(["test signal"])
    builds = {b.version_id: vars(encoder) for b in snapshot.bindings}
    lock, active, peak = threading.Lock(), 0, 0

    def query(*args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return []

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: branches(snapshot, builds, "signal", [1.0], query), range(2)))
    assert peak == 4 and all(len(r) == 10 for r in results)

    def failed(*args):
        raise TimeoutError("one_source_timed_out")

    with pytest.raises(TimeoutError):
        branches(snapshot, builds, "signal", [1.0], failed)


def test_absolute_deadline_rejects_late_results_and_cancels_queued_branches():
    snapshot = NS(bindings=[NS(version_id=str(i), index_name=str(i)) for i in range(8)])
    encoder = BM25Encoder.fit(["signal"])
    builds = {b.version_id: vars(encoder) for b in snapshot.bindings}
    started = []

    def query(binding, snapshot, branch, vector, cancelled):
        started.append(binding.version_id)
        cancelled.wait(0.2)
        network_timeout(8)
        return []

    with pytest.raises(TimeoutError), bounded_stage(0.04):
        branches(snapshot, builds, "signal", [1.0], query)
    time.sleep(0.05)
    assert len(started) <= 4


def test_reranker_retries_share_absolute_deadline(monkeypatch):
    from citeweave.settings import Settings

    monkeypatch.setattr(
        model_client, "settings", lambda: Settings(model_attempts=2, retry_backoff_seconds=0.001)
    )
    calls = []

    def handler(req):
        calls.append(req.extensions["timeout"]["read"])
        time.sleep(0.02)
        return httpx.Response(503)

    circuit = NS(change=lambda *args: 0)
    client = model_client.ModelGateway(httpx.MockTransport(handler), circuit)
    with pytest.raises(model_client.GatewayError), bounded_stage(0.2):
        client.structural_rerank("q", ["t"])
    assert len(calls) == 2 and 0 < calls[1] < calls[0] <= 0.201
