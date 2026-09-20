"""Owned evaluation execution reuses durable answers and never retries uncertainty."""

import asyncio
import hashlib
import threading
import time
from contextlib import aclosing
from uuid import UUID

from sqlalchemy import select

from citeweave import answering, schemas
from citeweave.db import transaction
from citeweave.domain import ChunkRow, EvalCaseRow, QueryRunRow
from citeweave.evaluation import lifecycle
from citeweave.evaluation.assessment import Assessor
from citeweave.evaluation.dataset import load_dataset
from citeweave.evaluation.judge import assess_answer, reserve
from citeweave.evaluation.reporting import refresh
from citeweave.llm import DeepSeekProvider
from citeweave.provider_phases import DurableProvider, evaluation_owner
from citeweave.settings import ROOT
from citeweave.trace import runtime_config


def provider_factory(phase):
    return DeepSeekProvider()


def save_owned(eval_id, case_id, owner, **values):
    with transaction() as db:
        case = db.get(EvalCaseRow, (eval_id, case_id))
        if not case or case.owner != owner:
            raise ValueError("evaluation_lease_lost")
        token = lifecycle.Ownership(eval_id, case_id, owner, case.fence)
    lifecycle.save(token, **values)


async def execute_case(eval_id, case_id, owner):
    token = evaluation_owner.get()
    with transaction() as db:
        saved, evaluation, _ = lifecycle.owned(db, token)
    dataset, digest = load_dataset(evaluation.dataset_id)
    spec = next(c for c in dataset["cases"] if c["case_id"] == case_id)
    if digest != evaluation.dataset_hash:
        raise ValueError("evaluation_dataset_changed")
    current = runtime_config(evaluation.runtime_config.get("query_profile", "m2"))
    if any(evaluation.runtime_config.get(k) != v for k, v in current.items()):
        raise ValueError("evaluation_config_changed")
    judge_profile = evaluation.runtime_config.get("judge_profile", "judge-v1")
    if (
        hashlib.sha256((ROOT / "prompts" / (judge_profile + ".txt")).read_bytes()).hexdigest()
        != evaluation.runtime_config["judge_prompt_sha256"]
    ):
        raise ValueError("evaluation_judge_changed")
    start, result = time.perf_counter(), saved.result
    if not result:
        with transaction() as db:
            prior = db.get(QueryRunRow, saved.query_run_id) if saved.query_run_id else None
        if prior and prior.status == "RUNNING":
            # A lost owner cannot attach and issue a second request. Only completed answers
            # are reusable here; a dispatched transport is resolved by the phase ledger.
            raise ValueError("prior_query_incomplete")
        if prior and prior.status == "COMPLETED":
            run = prior
        else:
            run = answering.begin_query(
                evaluation.workspace_id,
                schemas.QueryCreate(
                    kb_id=evaluation.kb_id,
                    question=spec["question"],
                    profile=evaluation.runtime_config.get("query_profile", "m2"),
                    evidence_mode=("compare" if spec["question_type"] == "comparison" else "single")
                    if evaluation.runtime_config.get("query_profile", "m2") == "telecom-structural-v1"
                    else "auto",
                ),
                f"eval:{eval_id}:{case_id}:{saved.execution_attempt}",
                captured_bindings=evaluation.runtime_config["index_bindings"],
                captured_snapshot=evaluation.runtime_config.get("structural_snapshot"),
            )
            lifecycle.save(token, query_run_id=run.id, phase="answer")
            async with aclosing(answering.stream_answer(run, provider=provider_factory("answer"))) as stream:
                async for _ in stream:
                    pass
        with transaction() as db:
            row = db.get(QueryRunRow, run.id)
            if row.status != "COMPLETED":
                raise ValueError("answer_not_completed")
            if row.evidence_pack:
                selected = row.evidence_pack["spans"]
                evidence = [
                    dict(label=c["label"], text=db.get(ChunkRow, UUID(c["evidence_id"])).text)
                    for c in selected
                ]
            else:
                selected = sorted(
                    [c for c in row.candidates if c.get("final_evidence_rank")],
                    key=lambda c: c["final_evidence_rank"],
                )
                evidence = [
                    dict(
                        label="E" + str(c["final_evidence_rank"]),
                        text=db.get(ChunkRow, UUID(c["candidate_id"])).text,
                    )
                    for c in selected
                ]
        assessor = Assessor(evaluation.workspace_id, evaluation.versions)
        from citeweave.evaluation.service import branches_from_run

        result = dict(
            case_id=case_id,
            split=spec["split"],
            query_run_id=str(row.id),
            status=row.status,
            question=spec["question"],
            question_type=spec["question_type"],
            answerable=spec["answerable"],
            answer=row.result,
            selected_evidence=evidence,
            error_code=row.error_code,
            usage=row.usage,
            estimated_yuan=float(row.estimated_yuan) if row.estimated_yuan is not None else None,
            latency_ms=(time.perf_counter() - start) * 1000,
            actual_config=row.runtime_config,
            assessment=assessor.assess(spec, row.id, branches_from_run(row), row.candidates, row.result),
        )
        lifecycle.save(token, result=result)
    with transaction() as db:
        saved, _, _ = lifecycle.owned(db, token)
    if saved.judge.get("status") != "COMPLETED":
        if saved.judge_reserved_yuan:
            with transaction() as db:
                from citeweave.domain import ProviderPhaseRow

                recorded = db.scalar(
                    select(ProviderPhaseRow.id)
                    .where(
                        ProviderPhaseRow.eval_run_id == eval_id,
                        ProviderPhaseRow.case_id == case_id,
                        ProviderPhaseRow.phase == "judge",
                    )
                    .limit(1)
                )
            if not recorded:
                # Unledgered reservations cannot prove that no legacy request was sent.
                lifecycle.save(
                    token, status="OUTCOME_UNKNOWN", last_error_code="unledgered_judge_reservation"
                )
                return
        if not saved.judge_reserved_yuan:
            reserve(eval_id, case_id)
        lifecycle.save(token, phase="judge")
        provider = DurableProvider(provider_factory("judge"), saved.query_run_id, phase="judge", token=token)
        judged = await assess_answer(spec, result, judge_profile, provider=provider)
        with transaction() as db:
            from citeweave.domain import ProviderPhaseRow

            unknown = db.scalar(
                select(ProviderPhaseRow.id)
                .where(
                    ProviderPhaseRow.eval_run_id == eval_id,
                    ProviderPhaseRow.case_id == case_id,
                    ProviderPhaseRow.phase == "judge",
                    ProviderPhaseRow.state.in_(["UNKNOWN", "DISPATCHED"]),
                )
                .limit(1)
            )
        if unknown:
            judged["estimated_yuan"] = None
        lifecycle.save(token, judge=judged, judge_estimated_yuan=judged["estimated_yuan"])
        if judged["status"] != "COMPLETED":
            raise ValueError("judge_not_completed")
    lifecycle.save(token, status="COMPLETED", phase="complete")
    refresh(eval_id)


def run_case(eval_id, case_id, generation=None):
    # Old tasks without a generation cannot authorize a new durable execution.
    if generation is None:
        return
    token = lifecycle.claim(UUID(eval_id), case_id, generation)
    if token is None:
        return
    stop = threading.Event()

    def beat():
        while not stop.wait(10):
            try:
                lifecycle.heartbeat(token)
            except Exception:
                return  # no new phase/result can pass its mandatory PG guard

    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    context = evaluation_owner.set(token)
    try:
        asyncio.run(execute_case(token.eval_id, token.case_id, token.owner))
    except Exception as exc:
        lifecycle.fail(token, type(exc).__name__)
    finally:
        stop.set()
        thread.join(timeout=1)
        evaluation_owner.reset(context)
        refresh(token.eval_id)
