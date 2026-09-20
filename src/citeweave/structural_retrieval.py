"""Captured child-build retrieval, real BGE, and immutable evidence projection."""

import math
import threading
import time
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from contextvars import copy_context

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from citeweave.context_tokens import ContextTokenizer
from citeweave.evidence import digest
from citeweave.evidence_selection import select_evidence
from citeweave.http_transport import TLS_CONTEXT
from citeweave.index import child_payload
from citeweave.model_client import GatewayError, ModelGateway
from citeweave.query_evidence import BranchHit, RerankerRanking, StructuralCandidate, StructuralSnapshot
from citeweave.retrieval import BM25Encoder, fuse_rrf
from citeweave.settings import settings
from citeweave.structural_contract import QUERY_CONTRACT
from citeweave.structural_repository import StructuralRepository
from citeweave.trace import bounded_stage, network_timeout, stage

# A single process-wide pool bounds actual HTTP branch requests across target queries.
BRANCH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="structural-qdrant")
TRANSIENT = {
    "model_connection_failed",
    "model_timeout",
    "circuit_open",
    "model_http_429",
    "model_http_502",
    "model_http_503",
    "model_http_504",
}


def qdrant_branch(binding, snapshot, branch, query, cancelled):
    if cancelled.is_set():
        raise TimeoutError("branch_cancelled")
    timeout = network_timeout(8)
    scope = dict(
        version_id=binding.version_id,
        kb_id=snapshot.kb_id,
        workspace_id=snapshot.workspace_id,
        artifact_id=binding.artifact_id,
        unit_kind="structural_child",
    )
    client = QdrantClient(
        url=settings().qdrant_url,
        timeout=timeout,
        check_compatibility=False,
        verify=TLS_CONTEXT,
        trust_env=False,
    )
    try:
        hits = client.query_points(
            binding.index_name,
            using=branch,
            query=query,
            query_filter=qm.Filter(
                must=[qm.FieldCondition(key=k, match=qm.MatchValue(value=v)) for k, v in scope.items()]
            ),
            limit=40,
            with_payload=True,
            timeout=max(1, int(timeout)),
        ).points
    finally:
        client.close()
    network_timeout(8)
    if cancelled.is_set():
        raise TimeoutError("branch_cancelled")
    return hits


def branches(snapshot, builds, question, dense, query=qdrant_branch):
    pending, futures = [], []
    cancelled = threading.Event()
    with bounded_stage(8) as deadline, stage("structural_branches", concurrency=4, branch_limit=40):
        try:
            for binding in snapshot.bindings:
                sparse = BM25Encoder(**builds[binding.version_id]).query_vector(question)
                for branch, vector in (
                    ("dense", dense),
                    ("bm25", qm.SparseVector(indices=sparse.indices, values=sparse.values)),
                ):
                    if branch == "bm25" and not sparse.indices:
                        pending.append((binding, branch, []))
                        continue
                    context = copy_context()
                    future = BRANCH_POOL.submit(
                        context.run, query, binding, snapshot, branch, vector, cancelled
                    )
                    futures.append((binding, branch, future))
            done, unfinished = wait(
                [f for _, _, f in futures],
                timeout=max(0, deadline - time.monotonic()),
                return_when=FIRST_EXCEPTION,
            )
            for f in done:
                f.result()
            if unfinished:
                raise TimeoutError("qdrant_stage_timeout")
            pending.extend((b, branch, f.result()) for b, branch, f in futures)
            network_timeout(8)
            return pending
        finally:
            cancelled.set()
            for _, _, future in futures:
                future.cancel()


class StructuralRetriever:
    def __init__(
        self,
        snapshot,
        model=None,
        repository=None,
        branch_query=qdrant_branch,
        *,
        parent_expansion=True,
        capture_selection=False,
    ):
        self.snapshot = StructuralSnapshot.model_validate(snapshot)
        self.model = model or ModelGateway()
        self.repository = repository or StructuralRepository(self.snapshot)
        self.branch_query = branch_query
        self.pack = None
        self.candidates = []
        self.binding_remaining = 2.0
        self.parent_expansion = parent_expansion
        self.capture_selection = capture_selection
        self.selection_inputs = None

    def retrieve(self, question, version_ids):
        if set(version_ids) != {b.version_id for b in self.snapshot.bindings}:
            raise ValueError("query_snapshot_versions_mismatch")
        with bounded_stage(25), stage("structural_retrieval"):
            binding_started = time.monotonic()
            builds = self.repository.builds()
            binding_spent = time.monotonic() - binding_started
            with bounded_stage(5), stage("query_embedding", input_count=1):
                dense = self.model.embed([question], query=True, contract=QUERY_CONTRACT)[0]
            results = branches(self.snapshot, builds, question, dense, self.branch_query)
            binding_started = time.monotonic()
            identities = {str(h.id) for _, _, hits in results for h in hits}
            children = self.repository.children(identities)
            rankings, retrieval = [], {i: [] for i in identities}
            for binding, branch, hits in results:
                ranking = []
                for hit in hits:
                    identity = str(hit.id)
                    if identity in ranking:
                        continue
                    c = children[identity]
                    payload = child_payload(
                        dict(
                            id=identity,
                            artifact_id=str(c["row"].artifact_id),
                            version_id=str(c["row"].version_id),
                            span_ids=c["span_ids"],
                            membership_hash=c["row"].membership_hash,
                            text_hash=c["row"].text_hash,
                            parent_node_id=str(c["row"].parent_node_id),
                        ),
                        dict(
                            unit_kind=binding.unit_kind,
                            artifact_id=binding.artifact_id,
                            index_profile_hash=binding.index_profile_hash,
                            embedding_identity=binding.embedding_identity,
                            bm25_hash=binding.bm25_hash,
                        ),
                        dict(
                            workspace_id=self.snapshot.workspace_id,
                            kb_id=self.snapshot.kb_id,
                            version_id=binding.version_id,
                        ),
                    )
                    if hit.payload != payload or not math.isfinite(hit.score):
                        raise ValueError("structural_hit_identity_mismatch")
                    ranking.append(identity)
                    retrieval[identity].append(
                        BranchHit(
                            branch=branch,
                            rank=len(ranking),
                            raw_score=hit.score,
                            score_scope=binding.index_name,
                        )
                    )
                rankings.append(ranking)
            with stage("rrf", k=60, input_count=len(identities), output_limit=20):
                fused = fuse_rrf(rankings, k=60)
            candidates = {}
            for rank, (identity, score) in enumerate(fused, 1):
                c = children[identity]
                candidates[identity] = StructuralCandidate(
                    candidate_id=identity,
                    child_id=identity,
                    document_id=c["binding"].document_id,
                    version_id=str(c["row"].version_id),
                    artifact_id=str(c["row"].artifact_id),
                    parent_id=str(c["row"].parent_node_id),
                    section_path=c["section_path"],
                    evidence_ids=c["span_ids"],
                    retrieval=retrieval[identity],
                    rrf_rank=rank,
                    rrf_score=score,
                    pool_reason="top20" if rank <= 20 else "outside_pool",
                )
            ordered = [i for i, _ in fused[:20]]
            self.candidates = list(candidates.values())
            degraded, reason = None, None
            atoms = {}
            if ordered:
                # Validate the exact frozen text before any model sees it.
                atoms = self.repository.atoms({eid for i in ordered for eid in children[i]["span_ids"]})
                for i in ordered:
                    text = "\n".join(atoms[eid].text for eid in children[i]["span_ids"])
                    if (
                        text != children[i]["row"].retrieval_text
                        or digest(text) != children[i]["row"].text_hash
                    ):
                        raise ValueError("child_text_membership_mismatch")
                binding_spent += time.monotonic() - binding_started
                try:
                    with bounded_stage(10), stage("structural_bge", input_count=len(ordered)) as info:
                        response = self.model.structural_rerank(
                            question, [children[i]["row"].retrieval_text for i in ordered]
                        )
                        if (
                            response["body_tokens"]
                            != [children[i]["row"].token_counts["bge"] for i in ordered]
                            or response["bge_query"] != self.snapshot.query_tokens["bge_query"]
                            or response["e5_input"] != self.snapshot.query_tokens["e5_input"]
                        ):
                            raise ValueError("reranker_token_accounting")
                        info.update(
                            queue_ms=response["queue_ms"],
                            inference_ms=response["inference_ms"],
                            tokenizers=response["tokenizers"],
                        )
                    for n, identity in enumerate(ordered):
                        candidates[identity].bge = RerankerRanking(
                            input_rank=n + 1,
                            output_rank=None,
                            score=response["scores"][n],
                            model=response["tokenizers"]["bge"],
                            pair_tokens=response["pair_tokens"][n],
                            body_tokens=response["body_tokens"][n],
                            query_tokens=response["bge_query"],
                            queue_ms=response["queue_ms"],
                            inference_ms=response["inference_ms"],
                        )
                    ordered.sort(key=lambda i: (-candidates[i].bge.score, i))
                    for rank, identity in enumerate(ordered, 1):
                        candidates[identity].bge.output_rank = rank
                except (GatewayError, TimeoutError) as exc:
                    reason = exc.code if isinstance(exc, GatewayError) else "reranker_stage_timeout"
                    if isinstance(exc, GatewayError) and reason not in TRANSIENT:
                        raise
                    network_timeout(2)
                    degraded = "degraded_reranker_unavailable"
            else:
                binding_spent += time.monotonic() - binding_started
            if self.capture_selection:
                self.selection_inputs = dict(
                    ordered=list(ordered),
                    candidates={i: c.model_copy(deep=True) for i, c in candidates.items()},
                    children={i: children[i] for i in ordered},
                    repository=self.repository,
                    tokenizer=ContextTokenizer(self.model),
                    degraded=degraded,
                    reason=reason,
                    seed_atoms=atoms,
                )
            binding_started = time.monotonic()
            with (
                bounded_stage(2 - binding_spent),
                stage("structural_evidence_pack", prior_binding_ms=binding_spent * 1000),
            ):
                chunks, self.pack = select_evidence(
                    ordered,
                    candidates,
                    {i: children[i] for i in ordered},
                    self.repository,
                    ContextTokenizer(self.model),
                    degraded,
                    reason,
                    seed_atoms=atoms,
                    parent_expansion=self.parent_expansion,
                )
            self.binding_remaining = 2 - binding_spent - (time.monotonic() - binding_started)
            return chunks, [c.model_dump(mode="json") for c in candidates.values()]
