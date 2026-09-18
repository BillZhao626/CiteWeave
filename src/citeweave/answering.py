"""Persist a query snapshot, stream provisional text, and commit only validated citations."""

import asyncio
import hashlib
import json
import logging
import re
from contextlib import aclosing
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, text

from citeweave import catalog, schemas
from citeweave.costs import attempt_cost, estimated_cost
from citeweave.db import transaction
from citeweave.domain import (
    ChunkRow,
    CitationRow,
    DocumentRow,
    EvalCaseRow,
    IndexRow,
    QueryRunRow,
    VersionRow,
)
from citeweave.embeddings import embedding_identity, resolve_experiment_bindings
from citeweave.evidence import Block, EvidenceSpan, resolve_span
from citeweave.hybrid import HybridRetriever
from citeweave.lifecycle import governance_lock
from citeweave.llm import DeepSeekProvider
from citeweave.profiles import query_profile
from citeweave.query_runtime import check_owned, expire_queries, remaining
from citeweave.reliability import error_category
from citeweave.settings import ROOT, settings
from citeweave.trace import RunTrace, current_trace, runtime_config, stage

PROMPT = ROOT / "prompts/answer-v1.txt"
REFUSAL = "证据不足，无法回答。"


def begin_query(workspace, body, key, captured_bindings=None):
    fingerprint_body = body.model_dump(mode="json")
    if body.profile == "m2":
        fingerprint_body.pop("profile")  # Preserve idempotency of historical M2 requests.
    digest = catalog.fingerprint(fingerprint_body)
    with transaction() as db:
        catalog.authorized_kb(db, body.kb_id, workspace)
        # One local provider budget across all workspaces, serialized before reservation.
        db.execute(text("SELECT pg_advisory_xact_lock(17702201)"))
        governance_lock(db)
        now = db.scalar(select(func.clock_timestamp()))
        expire_queries(db, now)
        existing = db.scalar(
            select(QueryRunRow).where(QueryRunRow.workspace_id == workspace, QueryRunRow.key == key)
        )
        if existing:
            if existing.fingerprint != digest:
                raise HTTPException(409, "idempotency_conflict")
            if existing.status == "RUNNING":
                raise HTTPException(409, "query_running")
            return existing
        if (
            db.scalar(select(func.count()).select_from(QueryRunRow).where(QueryRunRow.status == "RUNNING"))
            >= settings().max_active_queries
        ):
            raise HTTPException(429, "single_query_capacity", headers={"Retry-After": "2"})
        month = now.astimezone(ZoneInfo("Asia/Shanghai")).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        spent = db.scalar(
            select(
                func.coalesce(
                    func.sum(func.coalesce(QueryRunRow.estimated_yuan, QueryRunRow.reserved_yuan)), 0
                )
            ).where(QueryRunRow.created_at >= month)
        )
        spent += db.scalar(
            select(
                func.coalesce(
                    func.sum(
                        func.coalesce(EvalCaseRow.judge_estimated_yuan, EvalCaseRow.judge_reserved_yuan)
                    ),
                    0,
                )
            ).where(func.coalesce(EvalCaseRow.judge_reserved_at, EvalCaseRow.created_at) >= month)
        )
        if spent + Decimal("0.10") > Decimal(str(settings().monthly_budget_yuan)):
            raise HTTPException(429, "monthly_budget_reserved")
        versions = list(
            db.scalars(
                select(VersionRow.id)
                .join(DocumentRow, DocumentRow.active_version_id == VersionRow.id)
                .where(DocumentRow.kb_id == body.kb_id, VersionRow.status == "READY")
                .order_by(VersionRow.id)
            )
        )
        if captured_bindings is not None:
            from uuid import UUID

            versions = list(
                db.scalars(
                    select(VersionRow.id).where(
                        VersionRow.id.in_([UUID(v) for v in captured_bindings]),
                        VersionRow.kb_id == body.kb_id,
                        VersionRow.status == "READY",
                    )
                )
            )
            if len(versions) != len(captured_bindings):
                raise HTTPException(409, "evaluation_snapshot_unavailable")
        if not versions:
            raise HTTPException(409, "no_ready_documents")
        profile = query_profile(body.profile)
        if profile.get("embedding_key"):
            captured_bindings = resolve_experiment_bindings(
                db, workspace, versions, embedding_identity(profile["embedding_key"]), captured_bindings
            )
        bindings = {}
        for version_id in versions:
            version = db.get(VersionRow, version_id)
            name = (
                captured_bindings[str(version_id)]
                if captured_bindings is not None
                else version.index_collection
            )
            index = db.get(IndexRow, name)
            if index and index.unit_kind != "legacy_span":
                raise HTTPException(409, "structural_query_not_enabled")
            if index and (
                index.state not in {"PUBLISHED", "SUPERSEDED", "EXPERIMENT_READY"}
                or index.version_id != version_id
            ):
                raise HTTPException(409, "index_unavailable_rebuild_required")
            if not index and name != version.index_collection:
                raise HTTPException(409, "evaluation_snapshot_unavailable")
            if index and index.state == "EXPERIMENT_READY" and not profile.get("embedding_key"):
                raise HTTPException(409, "embedding_identity_mismatch")
            bindings[str(version_id)] = name
        run = QueryRunRow(
            id=uuid4(),
            workspace_id=workspace,
            kb_id=body.kb_id,
            key=key,
            fingerprint=digest,
            question=body.question,
            versions=[str(v) for v in versions],
            index_bindings=bindings,
            runtime_config=runtime_config(body.profile),
            created_at=now,
            absolute_deadline=now + timedelta(seconds=settings().query_deadline_seconds),
            owner=uuid4(),
            fence=1,
            runtime_policy="runtime-deadlines-v1",
        )
        db.add(run)
        db.flush()
        return run


def citation_for(chunk, label):
    span = EvidenceSpan.model_validate(chunk.evidence)
    block = Block.model_validate(chunk.block)
    resolve_span(span, block, block.scope)
    if span.scope.revision_id != chunk.version_id:
        raise ValueError("citation_version_mismatch")
    with transaction() as db:
        version = db.get(VersionRow, chunk.version_id)
        if span.source_sha256 != version.source_sha256:
            raise ValueError("citation_source_mismatch")
        return schemas.Citation(
            label=label,
            evidence_id=span.id,
            document_version_id=version.id,
            filename=version.filename,
            span=span,
            content_url=f"/v1/document-versions/{version.id}/content",
        )


def validate_citations(answer, selected):
    if answer.strip() == REFUSAL:
        return []
    labels = list(dict.fromkeys(re.findall(r"\[([^\[\]\n]+)\]", answer)))
    available = {c.label: c for c in selected}
    if not labels or any(label not in available for label in labels):
        raise ValueError("invalid_or_missing_citation")
    return [available[label] for label in labels]


def save_trace(run_id, trace, owner=None, fence=None):
    with transaction() as db:
        row, _ = check_owned(db, run_id, owner, fence)
        row.candidates = trace


def save_usage(run_id, usage, owner=None, fence=None):
    with transaction() as db:
        row, _ = check_owned(db, run_id, owner, fence)
        row.usage = usage
        row.estimated_yuan = estimated_cost(usage)


def finish(run_id, answer, owner=None, fence=None):
    with transaction() as db:
        row, stamp = check_owned(db, run_id, owner, fence)
        row.result, row.status = answer.model_dump(mode="json"), "COMPLETED"
        row.completed_at = stamp
        row.usage, row.estimated_yuan = answer.usage, answer.estimated_yuan
        for citation in answer.citations:
            db.add(CitationRow(run_id=run_id, evidence_id=citation.evidence_id))


def failed(run_id, code, contacted):
    with transaction() as db:
        row = db.scalar(select(QueryRunRow).where(QueryRunRow.id == run_id).with_for_update())
        if row.status == "RUNNING":
            row.status, row.error_code = "FAILED", code
            row.completed_at, row.error_category = (
                db.scalar(select(func.clock_timestamp())),
                error_category(code),
            )
            if not contacted or code in {"circuit_open", "llm_key_missing"}:
                row.estimated_yuan = Decimal(0)


def sse(event):
    # Omit absent envelope fields but retain nested nullable contract fields, identical to HTTP views.
    payload = {k: v for k, v in event.model_dump(mode="json").items() if v is not None}
    return "data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n"


async def stream_answer(run, provider=None, retriever=None):
    if run.status != "RUNNING":
        async with aclosing(_stream_answer(run, provider, retriever)) as stream:
            async for part in stream:
                yield part
        return
    trace = RunTrace(run.id, run.owner, run.fence)
    token = current_trace.set(trace)
    try:
        with trace.stage("request_received", input_count=1, output_count=1):
            pass
        async with aclosing(_stream_answer(run, provider, retriever)) as stream:
            async for part in stream:
                yield part
    finally:
        trace.cancelled.set()
        current_trace.reset(token)


async def _stream_answer(run, provider=None, retriever=None):
    if run.status != "RUNNING":
        yield sse(
            schemas.StreamEvent(
                type="final" if run.status == "COMPLETED" else "error",
                run_id=run.id,
                answer=run.result,
                code=run.error_code,
            )
        )
        return
    contacted, completed = False, False
    try:
        budget = await asyncio.to_thread(remaining, run.id, run.owner, run.fence)
        async with asyncio.timeout(budget):
            yield sse(schemas.StreamEvent(type="stage", run_id=run.id, stage="混合检索与重排"))
            chunks, trace = await asyncio.to_thread(
                (
                    retriever
                    or HybridRetriever(
                        index_bindings=run.index_bindings,
                        profile=run.runtime_config.get("query_profile", "m2"),
                    )
                ).retrieve,
                run.question,
                run.versions,
            )
            await asyncio.to_thread(save_trace, run.id, trace, run.owner, run.fence)
            with stage("evidence_binding", input_count=len(chunks), output_count=len(chunks)):
                selected = [
                    await asyncio.to_thread(citation_for, chunk, f"E{i}") for i, chunk in enumerate(chunks, 1)
                ]
            prompt_identity = run.runtime_config.get("prompt_identity", "answer-v1")
            prompt = (ROOT / "prompts" / (prompt_identity + ".txt")).read_text(encoding="utf-8")
            prompt_version = prompt_identity + ":" + hashlib.sha256(prompt.encode()).hexdigest()[:16]
            answer_text, usage = "", None
            if not selected:
                answer_text = REFUSAL
            else:
                messages = [
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": run.question,
                                "evidence": [{"label": c.label, "text": c.span.quote} for c in selected],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
                yield sse(schemas.StreamEvent(type="stage", run_id=run.id, stage="依据证据生成"))
                contacted = True
                async with aclosing(_provider_parts(provider or DeepSeekProvider(), messages)) as parts:
                    async for part in parts:
                        if "usage" in part:
                            usage = dict(
                                part["usage"],
                                model=part.get("model"),
                                provider_id=part.get("provider_id"),
                                uncertain_retry=part.get("uncertain_retry", False),
                                rate_card="deepseek-flash-CNY-2026-09-13",
                            )
                            await asyncio.to_thread(save_usage, run.id, usage, run.owner, run.fence)
                        if part.get("text"):
                            answer_text += part["text"]
                            if len(answer_text) > 8192:
                                raise ValueError("answer_length_limit")
                            yield sse(
                                schemas.StreamEvent(
                                    type="delta", run_id=run.id, text=part["text"], provisional=True
                                )
                            )
            with stage("citation_validation", input_count=len(selected)) as info:
                citations = validate_citations(answer_text, selected)
                info["output_count"] = len(citations)
            estimate = estimated_cost(usage) if contacted else Decimal(0)
            if active_trace := current_trace.get():
                provider_calls = [c for c in active_trace.calls if c["upstream"] == "deepseek"]
                if provider_calls:
                    estimate = attempt_cost(provider_calls)
            answer = schemas.Answer(
                run_id=run.id,
                text=answer_text,
                citations=citations,
                prompt_version=prompt_version,
                usage=usage,
                estimated_yuan=float(estimate) if estimate is not None else None,
            )
            with stage("final_response", input_count=1, output_count=1):
                await asyncio.to_thread(finish, run.id, answer, run.owner, run.fence)
            completed = True
            yield sse(schemas.StreamEvent(type="final", run_id=run.id, answer=answer))
    except (asyncio.CancelledError, GeneratorExit):
        await asyncio.shield(asyncio.to_thread(failed, run.id, "client_cancelled", contacted))
        raise
    except Exception as exc:
        safe_validation_codes = {
            "invalid_or_missing_citation",
            "answer_length_limit",
            "snapshot_not_ready",
            "index_provenance_mismatch",
            "citation_version_mismatch",
            "citation_source_mismatch",
            "run_no_longer_active",
        }
        code = (
            exc.code
            if hasattr(exc, "code")
            else "query_timeout"
            if isinstance(exc, TimeoutError)
            else str(exc)
            if isinstance(exc, ValueError) and str(exc) in safe_validation_codes
            else type(exc).__name__
        )
        logging.error("query_failed run=%s code=%s", run.id, code)
        await asyncio.to_thread(failed, run.id, code, contacted)
        yield sse(schemas.StreamEvent(type="error", run_id=run.id, code=code))
    finally:
        if not completed:
            try:
                await asyncio.shield(asyncio.to_thread(failed, run.id, "stream_interrupted", contacted))
            except Exception as exc:
                logging.error("query_cleanup_failed run=%s class=%s", run.id, type(exc).__name__)


async def _provider_parts(provider, messages):
    from contextlib import aclosing

    with stage("llm", input_count=len(messages)) as info:
        count = 0
        async with aclosing(provider.stream(messages)) as stream:
            async for part in stream:
                if part.get("text"):
                    count += len(part["text"])
                if part.get("usage"):
                    info["usage"] = part["usage"]
                yield part
        info["output_chars"] = count


def get_citation(workspace, run_id, evidence_id):
    with transaction() as db:
        run = db.scalar(
            select(QueryRunRow).where(
                QueryRunRow.id == run_id,
                QueryRunRow.workspace_id == workspace,
                QueryRunRow.status == "COMPLETED",
            )
        )
        if not run or not db.get(CitationRow, (run_id, evidence_id)):
            raise HTTPException(404, "citation_not_found")
        chunk = db.get(ChunkRow, evidence_id)
        if str(chunk.version_id) not in run.versions:
            raise HTTPException(404, "citation_not_found")
        label = next(c["label"] for c in run.result["citations"] if c["evidence_id"] == str(evidence_id))
        block = Block.model_validate(chunk.block)
        if block.scope.workspace_id != workspace or block.scope.kb_id != run.kb_id:
            raise HTTPException(404, "citation_not_found")
    return citation_for(chunk, label)
