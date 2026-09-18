"""Versioned, fallible LLM rubric; cost is reserved before contacting the provider."""

import asyncio
import hashlib
import json
import re
from contextlib import aclosing
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, QueryRunRow
from citeweave.llm import DeepSeekProvider
from citeweave.settings import ROOT, settings

Score = Literal[0, 0.5, 1]


class Judgment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correctness: Score
    completeness: Score
    faithfulness: Score | None
    relevancy: Score
    refusal_correctness: Score
    verdict: Literal["correct_complete", "partial", "incorrect_or_unjustified_refusal"]
    reason: str = Field(max_length=600)


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str = Field(min_length=1, max_length=600)
    evidence_labels: list[str] = Field(max_length=30)
    support: Score


class JudgmentV2(Judgment):
    claims: list[Claim] = Field(max_length=12)


class ClaimUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_index: int = Field(ge=0)
    factual: bool
    evidence_labels: list[str] = Field(max_length=30)
    support: Score | None


class JudgmentV3(Judgment):
    claims: list[ClaimUnit] = Field(max_length=60)


def answer_units(answer):
    sentences = re.findall(r"[^\n]+?(?:[。！？!?](?:\s*\[E\d+\])*|$)", answer, re.M)
    return [
        dict(
            claim_index=i,
            text=sentence.strip(),
            attached_labels=list(dict.fromkeys(re.findall(r"\[(E\d+)\]", sentence))),
        )
        for i, sentence in enumerate(sentences)
        if sentence.strip()
    ]


def validate_judgment(raw, result, identity):
    schema = {"judge-v1": Judgment, "judge-v2": JudgmentV2, "judge-v3": JudgmentV3, "judge-v4": JudgmentV3}[
        identity
    ]
    scores = schema.model_validate_json(raw).model_dump()
    answer = result["answer"]
    labels = {c["label"] for c in answer.get("citations", [])}
    if identity in {"judge-v3", "judge-v4"}:
        units = {u["claim_index"]: u for u in answer_units(answer["text"])}
        ids = [c["claim_index"] for c in scores["claims"]]
        if len(set(ids)) != len(ids) or set(ids) != set(units):
            raise ValueError("judge_claim_unit_coverage")
        for claim in scores["claims"]:
            unit = units[claim["claim_index"]]
            claim["claim"] = unit["text"]
            if not set(claim["evidence_labels"]) <= set(unit["attached_labels"]):
                raise ValueError("judge_claim_attachment_invalid")
            if claim["factual"] and claim["support"] is None:
                raise ValueError("judge_factual_support_missing")
        scores["unit_assessments"] = list(scores["claims"])
        scores["claims"] = [c for c in scores["claims"] if c["factual"]]
    for claim in scores.get("claims", []):
        if claim["claim"] not in answer["text"] or not set(claim["evidence_labels"]) <= labels:
            raise ValueError("judge_claim_scope_invalid")
        if not claim["evidence_labels"] and claim["support"] != 0:
            raise ValueError("judge_uncited_claim_support")
    return scores


def reserve(eval_id, case_id):
    with transaction() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(17702201)"))
        row = db.get(EvalCaseRow, (eval_id, case_id))
        if row.judge or row.judge_reserved_yuan:
            raise ValueError("judge_already_attempted")
        month = (
            datetime.now(timezone.utc)
            .astimezone(ZoneInfo("Asia/Shanghai"))
            .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
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
        row.judge_reserved_yuan, row.judge_estimated_yuan = Decimal("0.10"), None
        row.judge_reserved_at = db.scalar(select(func.clock_timestamp()))


async def assess_answer(case, result, identity="judge-v1"):
    if identity not in {"judge-v1", "judge-v2", "judge-v3", "judge-v4"}:
        raise ValueError("unknown_judge_profile")
    prompt = (ROOT / "prompts" / (identity + ".txt")).read_text(encoding="utf-8")
    metadata = dict(
        method="llm_judge_not_ground_truth",
        prompt_identity=identity,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        provider="deepseek",
        model=settings().deepseek_model,
        max_tokens=1024,
        thinking="disabled",
        human_review="not_reviewed",
    )
    answer = result.get("answer")
    if identity == "judge-v4" and answer and answer["text"] == "证据不足，无法回答。":
        correct = not case["answerable"]
        value = int(correct)
        return dict(
            metadata,
            method="deterministic_exact_refusal_policy",
            status="COMPLETED",
            scores=dict(
                correctness=value,
                completeness=value,
                faithfulness=None,
                relevancy=1 if correct else 0.5,
                refusal_correctness=value,
                verdict="correct_complete" if correct else "incorrect_or_unjustified_refusal",
                reason="Exact full refusal evaluated against frozen corpus answerability; no LLM call.",
                claims=[],
                unit_assessments=[
                    dict(
                        claim_index=u["claim_index"],
                        claim=u["text"],
                        factual=False,
                        evidence_labels=[],
                        support=None,
                    )
                    for u in answer_units(answer["text"])
                ],
            ),
            attempts=[],
            estimated_yuan=0,
        )
    if not answer:
        return dict(
            metadata,
            status="NOT_APPLICABLE",
            scores=dict(
                correctness=0,
                completeness=0,
                faithfulness=None,
                relevancy=0,
                refusal_correctness=0,
                verdict="incorrect_or_unjustified_refusal",
                reason="请求失败，无有效最终答案；按系统失败计入分母。",
            ),
            attempts=[],
            estimated_yuan=0,
        )
    data = dict(
        question=case["question"],
        answerable=case["answerable"],
        reference_answer=case["reference_answer"],
        reference_passages=[g["quote"] for g in case["gold"]],
        answer=answer["text"],
        supplied_evidence=result.get("selected_evidence", []),
    )
    if identity in {"judge-v3", "judge-v4"}:
        data["answer_units"] = answer_units(answer["text"])
    provider, raw = DeepSeekProvider(), ""
    status, scores, code = "COMPLETED", None, None
    try:
        async with (
            asyncio.timeout(45),
            aclosing(
                provider.stream(
                    [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                    ]
                )
            ) as stream,
        ):
            async for part in stream:
                raw += part.get("text", "")
                if len(raw) > 8192:
                    raise ValueError("judge_output_limit")
        scores = validate_judgment(raw, result, identity)
    except Exception as exc:
        status, code = "FAILED", getattr(exc, "code", type(exc).__name__)
        if isinstance(exc, ValueError) and str(exc).startswith("judge_"):
            code = str(exc)  # Our allowlisted validator code, never a provider body.
    costs = [a["estimated_yuan"] for a in provider.attempts]
    estimate = sum(costs) if all(c is not None for c in costs) else None
    return dict(
        metadata,
        status=status,
        scores=scores,
        error_code=code,
        attempts=provider.attempts,
        estimated_yuan=estimate,
    )
