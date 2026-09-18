"""Query a captured READY snapshot; never derive visibility from vector payloads."""

from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, or_, select

from citeweave.db import transaction
from citeweave.domain import ChunkRow, IndexRow, VersionRow
from citeweave.index import QdrantIndex
from citeweave.model_client import ModelGateway
from citeweave.parents import expand_parents
from citeweave.profiles import candidate_cutoff, expand_context, query_profile
from citeweave.retrieval import BM25Encoder, fuse_rrf
from citeweave.trace import stage


class Retriever(Protocol):
    def retrieve(self, question: str, version_ids: list[str]) -> tuple[list, list]: ...


class HybridRetriever:
    def __init__(self, index=None, model=None, index_bindings=None, profile="m2"):
        self.index = index or QdrantIndex()
        self.index_bindings = index_bindings
        self.profile = query_profile(profile)
        self.model = model or ModelGateway(embedding_key=self.profile.get("embedding_key", "e5-small"))
        if self.profile.get("embedding_key") and not index_bindings:
            raise ValueError("embedding_index_bindings_required")
        self.rerank_limit = self.profile.get("rerank_limit", 20)

    def retrieve(self, question, version_ids):
        with transaction() as db:
            versions = list(
                db.scalars(
                    select(VersionRow).where(
                        VersionRow.id.in_([UUID(v) for v in version_ids]), VersionRow.status == "READY"
                    )
                )
            )
            for version in versions:
                name = (
                    self.index_bindings[str(version.id)] if self.index_bindings else version.index_collection
                )
                row = db.get(IndexRow, name)
                if (row and row.unit_kind != "legacy_span") or version.profile.get(
                    "unit_kind"
                ) == "structural_child":
                    raise ValueError("structural_query_not_enabled")
        if len(versions) != len(version_ids):
            raise ValueError("snapshot_not_ready")
        with stage("query_embedding", input_count=1, output_count=1):
            dense = self.model.embed([question], query=True)[0]
        rankings, traces = [], {}
        for version in versions:
            encoder = BM25Encoder(**version.bm25)
            branches = self.index.branches(
                self.index_bindings[str(version.id)] if self.index_bindings else version.index_collection,
                version.id,
                dense,
                encoder.query_vector(question),
            )
            for source, hits in zip(("dense", "bm25"), branches, strict=True):
                rankings.append([identity for identity, _ in hits])
                for rank, (identity, score) in enumerate(hits, 1):
                    trace = traces.setdefault(
                        identity,
                        {
                            "candidate_id": identity,
                            "document_version_id": str(version.id),
                            "retrieval": [],
                            "reranker_score": None,
                            "final_evidence_rank": None,
                            "boxes": [],
                        },
                    )
                    trace["retrieval"].append(
                        {"source": source, "rank": rank, "score": score, "score_scope": str(version.id)}
                    )
        with stage("rrf", input_count=len(traces), k=60, output_limit=self.rerank_limit) as info:
            all_fused = fuse_rrf(rankings, k=60)
            for rank, (identity, score) in enumerate(all_fused, 1):
                traces[identity].update(rrf_rank=rank, rrf_score=score)
            info["output_count"] = len(all_fused)
        if not all_fused:
            return [], []
        with transaction() as db:
            previews = db.execute(
                select(ChunkRow.id, ChunkRow.text).where(
                    ChunkRow.id.in_([UUID(i) for i in traces]),
                    ChunkRow.version_id.in_([v.id for v in versions]),
                )
            ).all()
            if {str(i) for i, _ in previews} != set(traces):
                raise ValueError("index_provenance_mismatch")
            for identity, preview in previews:
                traces[str(identity)]["text"] = preview
            with stage(
                "candidate_cutoff",
                input_count=len(all_fused),
                output_limit=self.rerank_limit,
                dedup=self.profile["candidate_dedup"],
            ) as info:
                fused = candidate_cutoff(
                    all_fused, traces, self.rerank_limit, self.profile["candidate_dedup"] != "none"
                )
                info["output_count"] = len(fused)
                info["duplicates"] = sum(bool(c.get("duplicate_of")) for c in traces.values())
            chunks = {
                str(c.id): c
                for c in db.scalars(
                    select(ChunkRow).where(
                        ChunkRow.id.in_([UUID(identity) for identity, _ in fused]),
                        ChunkRow.version_id.in_([v.id for v in versions]),
                    )
                )
            }
        if len(chunks) != len(fused):
            raise ValueError("index_provenance_mismatch")
        with stage("reranker", input_count=len(fused), output_count=len(fused)):
            scores = []
            # Preserve the gateway's bounded batches, cancellation and per-call trace.
            for start in range(0, len(fused), 20):
                batch = [chunks[identity].text for identity, _ in fused[start : start + 20]]
                scores.extend(self.model.rerank(question, batch))
        for (identity, rrf_score), score in zip(fused, scores, strict=True):
            traces[identity].update(
                rrf_score=rrf_score, reranker_score=score, boxes=chunks[identity].evidence["boxes"]
            )
        ordered = sorted([identity for identity, _ in fused], key=lambda i: (-traces[i]["reranker_score"], i))
        with stage("evidence_selection", input_count=len(ordered), output_count=min(6, len(ordered))):
            for rank, identity in enumerate(ordered, 1):
                traces[identity]["reranker_rank"] = rank
                traces[identity]["final_evidence_rank"] = rank if rank <= 6 else None
        selected = [chunks[i] for i in ordered[:6]]
        if selected and self.profile.get("neighbor_radius"):
            pages = {(c.version_id, c.evidence["boxes"][0]["page_index"]) for c in selected}
            with stage("evidence_context", input_count=len(selected), profile=self.profile) as info:
                with transaction() as db:
                    pool = list(
                        db.scalars(
                            select(ChunkRow).where(
                                or_(
                                    *[
                                        and_(
                                            ChunkRow.version_id == version,
                                            ChunkRow.evidence["boxes"][0]["page_index"].as_integer() == page,
                                        )
                                        for version, page in pages
                                    ]
                                )
                            )
                        )
                    )
                if self.profile.get("context_strategy") == "geometry-paragraph-v1":
                    selected, origins, parents = expand_parents(selected, pool, self.profile)
                    info["parent_contexts"] = parents
                    parent_ids = {
                        identity: p["parent_id"] for p in parents for identity in p["selected_member_ids"]
                    }
                else:
                    selected, origins = expand_context(selected, pool, self.profile)
                    parent_ids = {}
                for trace in traces.values():
                    trace["final_evidence_rank"] = None
                for rank, chunk in enumerate(selected, 1):
                    identity = str(chunk.id)
                    trace = traces.setdefault(
                        identity,
                        dict(
                            candidate_id=identity,
                            document_version_id=str(chunk.version_id),
                            retrieval=[],
                            reranker_score=None,
                        ),
                    )
                    trace.update(text=chunk.text, boxes=chunk.evidence["boxes"], final_evidence_rank=rank)
                    if identity in origins:
                        trace["context_seed"] = origins[identity]
                    if identity in parent_ids:
                        trace["parent_context_id"] = parent_ids[identity]
                info.update(output_count=len(selected), output_chars=sum(len(c.text) for c in selected))
        remainder = [i for i, _ in all_fused if i not in ordered]
        trace_order = list(dict.fromkeys([str(c.id) for c in selected] + ordered + remainder))
        return selected, [traces[i] for i in trace_order]
