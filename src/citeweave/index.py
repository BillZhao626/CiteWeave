"""Qdrant adapter: immutable attempt collections with named dense and BM25 vectors."""

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from citeweave.settings import settings
from citeweave.trace import network_timeout, stage


def qdrant_timeout():
    remaining = network_timeout(8)
    if remaining < 1:
        raise TimeoutError("query_deadline_exhausted")
    return int(remaining)


class QdrantIndex:
    def __init__(self):
        self.client = QdrantClient(url=settings().qdrant_url, timeout=network_timeout(8))

    def create(self, collection, dimension=384):
        self.client.create_collection(
            collection,
            timeout=qdrant_timeout(),
            vectors_config={"dense": qm.VectorParams(size=dimension, distance=qm.Distance.COSINE)},
            sparse_vectors_config={"bm25": qm.SparseVectorParams()},
        )

    def write(self, collection, chunks, dense, encoder, start):
        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, dense, strict=True), start=start):
            sparse = encoder.document_vector(i)
            points.append(
                qm.PointStruct(
                    id=chunk["id"],
                    vector={
                        "dense": vector,
                        "bm25": qm.SparseVector(indices=sparse.indices, values=sparse.values),
                    },
                    payload={
                        "version_id": chunk["evidence"]["scope"]["revision_id"],
                        "kb_id": chunk["evidence"]["scope"]["kb_id"],
                    },
                )
            )
        # This pinned client version accepts upsert timeout only at client construction.
        client = QdrantClient(url=settings().qdrant_url, timeout=network_timeout(8))
        try:
            client.upsert(collection, points, wait=True)
        finally:
            client.close()

    def verify(self, collection, ids):
        if self.client.count(collection, exact=True, timeout=qdrant_timeout()).count != len(ids):
            raise RuntimeError("index_count_mismatch")
        for start in range(0, len(ids), 100):
            wanted = ids[start : start + 100]
            records = self.client.retrieve(
                collection,
                wanted,
                with_payload=False,
                with_vectors=False,
                timeout=qdrant_timeout(),
            )
            if {str(r.id) for r in records} != set(wanted):
                raise RuntimeError("index_identity_mismatch")

    def branches(self, collection, version_id, dense, sparse, limit=40):
        scope = qm.Filter(
            must=[qm.FieldCondition(key="version_id", match=qm.MatchValue(value=str(version_id)))]
        )
        with stage(
            "retrieval_dense", version_id=str(version_id), collection=collection, input_count=1
        ) as info:
            dense_hits = self.client.query_points(
                collection,
                timeout=qdrant_timeout(),
                query=dense,
                using="dense",
                query_filter=scope,
                limit=limit,
                with_payload=False,
            ).points
            info["output_count"] = len(dense_hits)
        with stage(
            "retrieval_bm25",
            version_id=str(version_id),
            collection=collection,
            input_count=len(sparse.indices),
        ) as info:
            sparse_hits = (
                self.client.query_points(
                    collection,
                    timeout=qdrant_timeout(),
                    query=qm.SparseVector(indices=sparse.indices, values=sparse.values),
                    using="bm25",
                    query_filter=scope,
                    limit=limit,
                    with_payload=False,
                ).points
                if sparse.indices
                else []
            )
            info["output_count"] = len(sparse_hits)
        return [[(str(p.id), p.score) for p in dense_hits], [(str(p.id), p.score) for p in sparse_hits]]
