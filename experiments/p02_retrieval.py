"""Real Qdrant dense/sparse and app-side RRF; physical snapshots carry frozen IDF."""

import json
import math
import sys
import time
from uuid import NAMESPACE_URL, uuid5

import numpy as np
from common import ROOT, report
from qdrant_client import QdrantClient, models

from citeweave.retrieval import BM25Encoder, fuse_rrf, tokenize

OUTPUT = ROOT / ".artifacts" / "p02"


def metrics(rankings, queries):
    recall, reciprocal, ndcg = [], [], []
    for q in queries:
        rank = next((i + 1 for i, doc in enumerate(rankings[q["id"]][:10]) if doc in q["relevant"]), None)
        recall.append(int(rank is not None))
        reciprocal.append(1 / rank if rank else 0)
        ndcg.append(1 / math.log2(rank + 1) if rank else 0)
    return {
        "recall_at_10": float(np.mean(recall)),
        "mrr_at_10": float(np.mean(reciprocal)),
        "ndcg_at_10": float(np.mean(ndcg)),
        "hits": sum(recall),
        "questions": len(queries),
    }


def main():
    corpus = json.loads((OUTPUT / "corpus.json").read_text(encoding="utf-8"))
    docs, queries = corpus["documents"], corpus["queries"]
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        baseline = json.loads((OUTPUT / "baseline.json").read_text(encoding="utf-8"))
        reranked = json.loads((OUTPUT / "reranked.json").read_text(encoding="utf-8"))
        baseline["metrics"]["rrf_reranker"] = metrics(reranked, queries)
        baseline["models"] = [
            json.loads((OUTPUT / f"{m}-stats.json").read_text()) for m in ["embed", "rerank"]
        ]
        baseline["status"] = "passed_controlled_development_only"
        baseline["limitations"] = [
            "30 designed dev questions, no held-out or real-document quality claim",
            "mostly unrelated background distractors; harder negatives required in M2",
            "one embedding and one reranker measured; alternatives not yet certified",
            "short text max_length=256; long-context behavior not measured",
        ]
        report("p02-retrieval", baseline)
        return
    encoder = BM25Encoder.fit([d["text"] for d in docs])
    vectors = np.load(OUTPUT / "vectors.npz")
    name = f"cw_m0_{encoder.fingerprint[:12]}"
    client = QdrantClient(url="http://127.0.0.1:16333", timeout=20)
    if not client.collection_exists(name):
        client.create_collection(
            name,
            vectors_config={"dense": models.VectorParams(size=384, distance=models.Distance.COSINE)},
            sparse_vectors_config={"bm25": models.SparseVectorParams()},
        )
    points = []
    for i, doc in enumerate(docs):
        sparse = encoder.document_vector(i)
        points.append(
            models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, name + doc["id"])),
                vector={
                    "dense": vectors["documents"][i].tolist(),
                    "bm25": models.SparseVector(indices=sparse.indices, values=sparse.values),
                },
                payload={
                    "chunk_id": doc["id"],
                    "workspace": "cw-m0",
                    "kb": "primary",
                    "revision": encoder.fingerprint,
                },
            )
        )
    # Deliberately strongest cross-KB duplicate. It must be excluded in both retrieval arms.
    poison = points[0].model_copy(deep=True)
    poison.id = str(uuid5(NAMESPACE_URL, name + "other-kb"))
    poison.payload = {**poison.payload, "kb": "other", "chunk_id": "cross-kb-forbidden"}
    for start in range(0, len(points), 100):
        client.upsert(name, points=points[start : start + 100], wait=True)
    client.upsert(name, points=[poison], wait=True)
    scope = models.Filter(
        must=[
            models.FieldCondition(key=k, match=models.MatchValue(value=v))
            for k, v in {"workspace": "cw-m0", "kb": "primary", "revision": encoder.fingerprint}.items()
        ]
    )
    rankings = {m: {} for m in ["dense", "bm25", "rrf"]}
    latency = []
    score_deltas = []
    for i, q in enumerate(queries):
        start = time.perf_counter()
        dense = client.query_points(
            name, query=vectors["queries"][i].tolist(), using="dense", query_filter=scope, limit=40
        ).points
        sparse = encoder.query_vector(q["text"])
        lexical = (
            client.query_points(
                name,
                query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                using="bm25",
                query_filter=scope,
                limit=40,
            ).points
            if sparse.indices
            else []
        )
        for mode, values in [("dense", dense), ("bm25", lexical)]:
            ids = [p.payload["chunk_id"] for p in values]
            assert "cross-kb-forbidden" not in ids
            rankings[mode][q["id"]] = ids
        local = dict(zip([d["id"] for d in docs], encoder.scores(q["text"])))
        score_deltas.extend(abs(local[p.payload["chunk_id"]] - p.score) for p in lexical)
        rankings["rrf"][q["id"]] = [
            p for p, _ in fuse_rrf([rankings["dense"][q["id"]], rankings["bm25"][q["id"]]])
        ]
        latency.append(time.perf_counter() - start)
    assert max(score_deltas) < 0.0001
    wrong_scope = models.Filter(
        must=[models.FieldCondition(key="workspace", match=models.MatchValue(value="absent"))]
    )
    assert not client.query_points(
        name, query=vectors["queries"][0].tolist(), using="dense", query_filter=wrong_scope
    ).points
    assert not client.query_points(
        name, query=models.SparseVector(indices=[0], values=[1]), using="bm25", query_filter=wrong_scope
    ).points
    candidates = {q["id"]: rankings["rrf"][q["id"]][:20] for q in queries}
    (OUTPUT / "candidates.json").write_text(json.dumps(candidates), encoding="utf-8")
    (OUTPUT / "rankings.json").write_text(json.dumps(rankings), encoding="utf-8")
    baseline = {
        "chunks": len(docs),
        "questions": len(queries),
        "collection": name,
        "snapshot_fingerprint": encoder.fingerprint,
        "scope_checks": "cross-KB duplicate excluded; unknown workspace empty in both arms",
        "bm25_max_abs_delta_vs_python": max(score_deltas),
        "chinese_identifier_tokens": tokenize("连接超时与TS 38.331，HTTP/2重试"),
        "retrieval_and_local_crosscheck_p95_seconds": float(np.percentile(latency, 95)),
        "metrics": {mode: metrics(value, queries) for mode, value in rankings.items()},
    }
    (OUTPUT / "baseline.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(baseline, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
