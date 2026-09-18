"""Assess retrieval and source grounding independently of the answering pipeline."""

import json
from uuid import UUID

from sqlalchemy import select

from citeweave.answering import get_citation
from citeweave.blobs import LocalBlobStore
from citeweave.db import transaction
from citeweave.domain import ChildSpanRow, ChunkRow, QueryRunRow, StructureArtifactRow, VersionRow
from citeweave.evaluation.metrics import grounded_citations
from citeweave.evidence import Block, EvidenceSpan, resolve_span
from citeweave.retrieval import fuse_rrf
from citeweave.settings import settings


class Assessor:
    def __init__(self, workspace, versions):
        self.workspace, self.versions = workspace, versions
        self.parsed = {}

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
            # Frozen canonical geometry is bound to these exact source bytes and parser.
            # Never run today's parser over yesterday's immutable version.
            with transaction() as db:
                artifact = db.scalar(
                    select(StructureArtifactRow).where(
                        StructureArtifactRow.version_id == version.id,
                        StructureArtifactRow.state == "PUBLISHED",
                    )
                )
            if artifact and (
                artifact.canonical_sha != version.canonical_key
                or artifact.parser_revision != version.profile.get("parser_revision")
            ):
                raise ValueError("frozen_parser_identity_mismatch")
            blocks = [Block.model_validate(b) for b in json.loads(blob.get(version.canonical_key))]
            self.parsed[identity] = {b.block_id: b for b in blocks}
        span = EvidenceSpan.model_validate(citation["span"])
        if span != evidence.span or str(span.scope.revision_id) != identity:
            raise ValueError("citation_identity_changed")
        block = self.parsed[identity][span.block_id]
        resolve_span(span, block, block.scope)  # Checks text, codepoint offsets, hashes and every box.
        return dict(version=True, page=True, quote=True, grounded=True)

    def assess(self, case, run_id, branches, candidates, answer):
        return self.assess_support(case, run_id, branches, candidates, answer)

    def assess_support(self, case, run_id, branches, candidates, answer):
        from citeweave.evaluation.support import group_ranking, support_coverage

        groups = case.get("support_groups")
        if groups is None:
            groups = [
                dict(group_id=f"legacy-support-{i}", alternatives=[[g]]) for i, g in enumerate(case["gold"])
            ]
        aspects = case.get(
            "required_aspects",
            [dict(aspect_id=g["group_id"], required_groups=[g["group_id"]]) for g in groups],
        )
        sources = case.get(
            "required_sources",
            sorted({r["source_id"] for g in groups for alt in g["alternatives"] for r in alt}),
        )
        candidate_ids = [UUID(c["candidate_id"]) for c in candidates]
        if len(candidate_ids) > 800:
            raise ValueError("assessment_candidate_limit")
        with transaction() as db:
            run = db.get(QueryRunRow, run_id)
            members = list(db.scalars(select(ChildSpanRow).where(ChildSpanRow.child_id.in_(candidate_ids))))
            identities = set(candidate_ids) | {m.evidence_id for m in members}
            identities.update(UUID(s["evidence_id"]) for s in (run.evidence_pack or {}).get("spans", []))
            gold_blocks = {r["block_id"] for g in groups for alt in g["alternatives"] for r in alt}
            from sqlalchemy import or_

            self.chunks = list(
                db.scalars(
                    select(ChunkRow).where(
                        ChunkRow.version_id.in_([UUID(v) for v in self.versions.values()]),
                        or_(ChunkRow.id.in_(identities), ChunkRow.block["block_id"].astext.in_(gold_blocks)),
                    )
                )
            )
        reverse = {v: k for k, v in self.versions.items()}
        atoms = {
            str(c.id): dict(
                source_id=reverse[str(c.version_id)],
                block_id=c.block["block_id"],
                start_offset=c.evidence["start_offset"],
                end_offset=c.evidence["end_offset"],
            )
            for c in self.chunks
        }
        by_block = {(reverse[str(c.version_id)], c.block["block_id"]): c.block for c in self.chunks}
        with transaction() as db:
            versions = {k: db.get(VersionRow, UUID(v)) for k, v in self.versions.items()}
            run = db.get(QueryRunRow, run_id)
            for g in groups:
                for alt in g["alternatives"]:
                    for r in alt:
                        v, b = versions[r["source_id"]], by_block.get((r["source_id"], r["block_id"]))
                        if not b or not 0 <= r["start_offset"] < r["end_offset"] <= len(b["text"]):
                            raise ValueError("gold_not_resolvable")
                        if (
                            r.get("quote") is not None
                            and b["text"][r["start_offset"] : r["end_offset"]] != r["quote"]
                        ):
                            raise ValueError("gold_quote_mismatch")
                        if r.get("quote_sha256"):
                            import hashlib

                            if (
                                hashlib.sha256(
                                    b["text"][r["start_offset"] : r["end_offset"]].encode()
                                ).hexdigest()
                                != r["quote_sha256"]
                            ):
                                raise ValueError("gold_range_hash_mismatch")
                        if any(
                            r.get(k) and r[k] != value
                            for k, value in (
                                ("source_sha256", v.source_sha256),
                                ("canonical_sha256", v.canonical_key),
                                ("parser_revision", v.profile.get("parser_revision")),
                            )
                        ):
                            raise ValueError("gold_frozen_identity_mismatch")
            projection = {i: [a] for i, a in atoms.items()}
            candidate_ids = [UUID(c["candidate_id"]) for c in candidates]
            for member in db.scalars(select(ChildSpanRow).where(ChildSpanRow.child_id.in_(candidate_ids))):
                if str(member.evidence_id) not in atoms:
                    raise ValueError("candidate_span_scope_mismatch")
                projection.setdefault(str(member.child_id), []).append(atoms[str(member.evidence_id)])
        rankings = {name: [[h[0] for h in b[name]] for b in branches] for name in ("dense", "bm25")}
        stages = {name: [i for i, _ in fuse_rrf(rows)] for name, rows in rankings.items()}
        stages["rrf"] = [i for i, _ in fuse_rrf([hits for rows in rankings.values() for hits in rows])]
        ranked = [c for c in candidates if c.get("bge") or c.get("reranker_score") is not None]
        ranked.sort(
            key=lambda c: (-(c["bge"]["score"] if c.get("bge") else c["reranker_score"]), c["candidate_id"])
        )
        stages["reranked"] = [c["candidate_id"] for c in ranked]
        initial = [a for i in stages["rrf"] for a in projection.get(i, [])]
        pool = [a for i in stages["reranked"] for a in projection.get(i, [])]
        selected = (
            [s["evidence_id"] for s in run.evidence_pack["spans"]]
            if run.evidence_pack
            else [c["candidate_id"] for c in candidates if c.get("final_evidence_rank")]
        )
        final = [a for i in selected for a in projection.get(i, [])]
        coverage = {
            name: support_coverage(items, groups, aspects, sources)
            for name, items in (("initial", initial), ("rerank_input", pool), ("final", final))
        }
        citations = answer.get("citations", []) if answer else []
        physical = grounded_citations(citations, set(), lambda c: self.validate(run_id, c))
        from citeweave.evaluation.support import covered_groups

        valid = [
            atoms[c["evidence_id"]] for c in physical["checks"] if c["grounded"] and c["evidence_id"] in atoms
        ]
        gold_ranges = [r for g in groups for alt in g["alternatives"] for r in alt]
        overlapping = sum(
            any(
                a["source_id"] == r["source_id"]
                and a["block_id"] == r["block_id"]
                and max(a["start_offset"], r["start_offset"]) < min(a["end_offset"], r["end_offset"])
                for r in gold_ranges
            )
            for a in valid
        )
        physical["precision"] = overlapping / len(citations) if citations and groups else None
        physical["recall"] = len(covered_groups(valid, groups)) / len(groups) if groups else None
        physical["relevance_method"] = "finite_source_range_overlap_and_support_group_recall"
        return dict(
            metric_revision="source-support-v1",
            gold_ids=[g["group_id"] for g in groups],
            retrieval={
                name: {str(k): group_ranking(ids, projection, groups, k) for k in (5, 6, 10, 20, 40)}
                for name, ids in stages.items()
            },
            evidence={name: c["required_aspect_coverage"] for name, c in coverage.items()},
            support_coverage=coverage,
            citation=physical,
            stage_rankings=stages,
            per_version={},
        )
