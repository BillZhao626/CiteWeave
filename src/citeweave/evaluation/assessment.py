"""Assess retrieval and source grounding independently of the answering pipeline."""

from uuid import UUID

from sqlalchemy import select

from citeweave.answering import get_citation
from citeweave.blobs import LocalBlobStore
from citeweave.db import transaction
from citeweave.domain import ChunkRow, QueryRunRow, VersionRow
from citeweave.evaluation.metrics import coverage, grounded_citations, ranking_metrics
from citeweave.evidence import EvidenceSpan, Scope, resolve_span
from citeweave.parsing import parse_simple_pdf
from citeweave.retrieval import fuse_rrf
from citeweave.settings import settings


class Assessor:
    def __init__(self, workspace, versions):
        self.workspace, self.versions = workspace, versions
        self.parsed = {}
        with transaction() as db:
            self.chunks = list(
                db.scalars(
                    select(ChunkRow).where(ChunkRow.version_id.in_([UUID(v) for v in versions.values()]))
                )
            )

    def gold_ids(self, case):
        matches = set()
        for gold in case["gold"]:
            found = [
                c
                for c in self.chunks
                if str(c.version_id) == self.versions[gold["source_id"]]
                and c.block["block_id"] == gold["block_id"]
                and c.evidence["start_offset"] <= gold["start_offset"]
                and c.evidence["end_offset"] >= gold["end_offset"]
            ]
            if (
                len(found) != 1
                or found[0].block["text"][gold["start_offset"] : gold["end_offset"]] != gold["quote"]
            ):
                raise ValueError("gold_not_resolvable")
            matches.add(str(found[0].id))
        return matches

    def validate(self, run_id, citation):
        evidence = get_citation(self.workspace, run_id, UUID(citation["evidence_id"]))
        with transaction() as db:
            run = db.get(QueryRunRow, run_id)
            version = db.get(VersionRow, evidence.document_version_id)
        identity = str(version.id)
        if identity not in run.versions or identity not in self.versions.values():
            raise ValueError("version_not_in_captured_scope")
        blob = LocalBlobStore(settings().blob_root)
        blob.get(version.blob_key)  # Recheck bytes even when parsed geometry is cached in this batch.
        if identity not in self.parsed:
            blocks = parse_simple_pdf(
                blob.path(version.blob_key),
                Scope(workspace_id=self.workspace, kb_id=run.kb_id, revision_id=version.id),
            )
            self.parsed[identity] = {b.block_id: b for b in blocks}
        span = EvidenceSpan.model_validate(citation["span"])
        if span != evidence.span or str(span.scope.revision_id) != identity:
            raise ValueError("citation_identity_changed")
        block = self.parsed[identity][span.block_id]
        resolve_span(span, block, block.scope)  # Checks text, codepoint offsets, hashes and every box.
        return dict(version=True, page=True, quote=True, grounded=True)

    def assess(self, case, run_id, branches, candidates, answer):
        gold = self.gold_ids(case)
        rankings = {source: [[h[0] for h in b[source]] for b in branches] for source in ("dense", "bm25")}
        stages = {source: [i for i, _ in fuse_rrf(rows)] for source, rows in rankings.items()}
        all_lists = [hits for rows in rankings.values() for hits in rows]
        stages["rrf"] = [i for i, _ in fuse_rrf(all_lists)]
        reranked = [c for c in candidates if c.get("reranker_score") is not None]
        reranked.sort(key=lambda c: (-c["reranker_score"], c["candidate_id"]))
        stages["reranked"] = [c["candidate_id"] for c in reranked]
        initial = {i for hits in all_lists for i in hits}
        selected = [c["candidate_id"] for c in candidates if c.get("final_evidence_rank")]
        metrics = {
            name: {str(k): ranking_metrics(ids, gold, k) for k in (5, 6, 10, 20, 40)}
            for name, ids in stages.items()
        }
        per_version = {}
        for b in branches:
            relevant = {str(c.id) for c in self.chunks if str(c.version_id) == b["version_id"]} & gold
            if relevant:
                per_version[b["version_id"]] = {
                    source: ranking_metrics([h[0] for h in b[source]], relevant, 40)
                    for source in ("dense", "bm25")
                }
        citations = answer.get("citations", []) if answer else []
        return dict(
            metric_revision="stage-identity-v2",
            retrieval=metrics,
            per_version=per_version,
            gold_ids=sorted(gold),
            evidence=dict(
                initial=coverage(initial, gold),
                rerank_input=coverage(stages["reranked"], gold),
                final=coverage(selected, gold),
            ),
            citation=grounded_citations(citations, gold, lambda c: self.validate(run_id, c)),
            answer=dict(
                method="pending_rubric_review",
                correctness=None,
                completeness=None,
                faithfulness=None,
                relevancy=None,
                refusal_correctness=None,
            ),
            stage_rankings=stages,
        )
