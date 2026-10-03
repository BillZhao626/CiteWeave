"""Production adapters for the existing Conversation orchestration and gateway.

An explicit, request-bound server policy is deployment input, never a public API
grant or a default spending budget. PostgreSQL owns the persisted authorization.
"""

import asyncio
import hashlib
import json
import logging
import random
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from pydantic import AwareDatetime, Field

from citeweave import conversation_provider as ledger
from citeweave import conversations as core
from citeweave.answering import validate_citations
from citeweave.conversation_api import UnavailableRuntime
from citeweave.conversation_contract import Admission, CoreConflict, DurableDTO, Execution, StateSnapshot
from citeweave.conversation_evidence import produce
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_history import HistoryQuery
from citeweave.conversation_history_pg import RuntimeHistoryRead, read_history
from citeweave.conversation_interpretation import InterpretationDraft, InterpretationInput, interpret
from citeweave.costs import RATE_CARD, maximum_cost
from citeweave.llm import DeepSeekProvider, ProviderError, completion_payload
from citeweave.model_client import ModelGateway
from citeweave.provider_accounting import DeepSeekAccounting, request_hash, serialize_request
from citeweave.runtime_reliability import retry_delay
from citeweave.schemas import Answer
from citeweave.settings import ROOT, settings
from citeweave.trace import bounded_stage


class PhasePlan(DurableDTO):
    purpose: str = Field(pattern="^(interpretation|generation)$")
    input_tokens: int = Field(gt=0, strict=True)
    output_tokens: int = Field(gt=0, strict=True)
    request_hash: str | None = Field(default=None, pattern="^[0-9a-f]{64}$")
    max_attempts: int = Field(default=1, ge=1, le=3, strict=True)


class RuntimePolicy(DurableDTO):
    """No numeric defaults. Loaded only from explicit server-side configuration."""

    workspace_id: UUID
    conversation_id: UUID
    request: Admission
    execution_deadline: AwareDatetime
    authorization_id: UUID
    authorization_deadline: AwareDatetime
    max_calls: int = Field(ge=0, strict=True)
    max_input_tokens: int = Field(ge=0, strict=True)
    max_output_tokens: int = Field(ge=0, strict=True)
    max_yuan: Decimal = Field(ge=0, max_digits=12, decimal_places=8, allow_inf_nan=False)
    phases: tuple[PhasePlan, ...]
    history_scan_limit: int = Field(gt=0, le=2147483646, strict=True)
    history_statement_ms: int = Field(gt=0, le=2147483647, strict=True)
    context_max_bytes: int = Field(gt=0, strict=True)
    # A structured, server-reviewed intent is bound to this exact request.
    # Absent one, use the existing Interpreter seam through the paid gateway.
    reviewed_interpretation: InterpretationDraft | None = None
    history_query: HistoryQuery | None = None


def generation_messages(context, prompt):
    intent = dict(
        authority="contextual_intent_not_evidence",
        original_question=context.original_question,
        validated_query=context.retrieval_query,
        interpretation=dict(
            mode=context.interpretation.mode,
            topic_relation=context.interpretation.topic_relation,
            facts=[f.model_dump(mode="json") for f in context.interpretation.facts],
        ),
        history=[h.model_dump(mode="json") for h in context.history],
        working_state=[s.model_dump(mode="json") for s in context.working_state],
    )
    return [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": json.dumps(intent, ensure_ascii=False, separators=(",", ":"))
            + "\n"
            + context.evidence.pack.prompt_json,
        },
    ]


def interpretation_messages(context):
    # New seam contract, not a tuned replacement for any existing answer prompt.
    prompt = (ROOT / "prompts/conversation-interpretation-v1.txt").read_text(encoding="utf-8")
    sources = {s.ref: s for g in context.history.selected for s in g.sources}
    value = dict(
        authority="contextual_intent_not_evidence",
        question=context.request.question,
        scope=context.request.scope.model_dump(mode="json"),
        required=[t.model_dump(mode="json") for t in context.required],
        history=[
            dict(
                source=s.ref.model_dump(mode="json"),
                question=s.request.question,
                signals=s.signals.model_dump(mode="json"),
                relations=[r.model_dump(mode="json") for r in s.relations],
            )
            for s in sources.values()
        ],
        working_state=[s.model_dump(mode="json") for s in context.history.state_projection],
        output_schema=InterpretationDraft.model_json_schema(),
    )
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(value, ensure_ascii=False, separators=(",", ":"))},
    ]


class RuntimeCalls:
    def __init__(self, workspace, run, policy, accounting, provider_factory=DeepSeekProvider):
        self.workspace, self.run, self.policy = workspace, run, policy
        self.accounting, self.provider_factory = accounting, provider_factory

    def request(self, purpose, messages):
        plans = [p for p in self.policy.phases if p.purpose == purpose]
        if len(plans) != 1:
            raise CoreConflict("provider_phase_not_authorized")
        plan = plans[0]
        body = completion_payload(messages, settings().deepseek_model, plan.output_tokens)
        if len(serialize_request(body)) > self.policy.context_max_bytes:
            raise CoreConflict("conversation_context_overflow")
        measured = self.accounting.measure(body)
        if measured["input_tokens"] > plan.input_tokens:
            raise CoreConflict("provider_input_authorization_exceeded")
        if plan.request_hash and plan.request_hash != request_hash(body):
            raise CoreConflict("provider_request_identity_conflict")
        return body, measured

    def call(self, purpose, messages):
        body, measured = self.request(purpose, messages)
        plan = next(p for p in self.policy.phases if p.purpose == purpose)
        grant = ledger.CallAuthorization(
            id=uuid5(self.policy.authorization_id, purpose),
            run_id=self.run.id,
            purpose=purpose,
            provider="deepseek",
            model=body["model"],
            price_revision=RATE_CARD,
            prompt_revision="conversation-v1:"
            + hashlib.sha256(messages[0]["content"].encode()).hexdigest()
            + ":"
            + hashlib.sha256(self.accounting.identity.encode()).hexdigest()[:16],
            request_hash=request_hash(body),
            input_tokens=measured["input_tokens"],
            output_tokens=body["max_tokens"],
            max_yuan=maximum_cost(measured["input_tokens"], body["max_tokens"]),
            expires_at=self.policy.authorization_deadline,
            max_attempts=plan.max_attempts,
        )
        phase = ledger.prepare(self.workspace, self.run, grant)
        if phase.state != "PREPARED":
            raise CoreConflict("provider_phase_not_dispatchable")
        return asyncio.run(self._send(phase, body))

    async def _send(self, phase, body):
        from contextlib import aclosing

        while True:
            attempt = ledger.begin_attempt(self.workspace, self.run, phase.id)
            observed, text, dispatched = {}, "", False
            started = time.perf_counter()

            def before_send():
                nonlocal dispatched
                ledger.dispatch(self.workspace, self.run, phase.id, attempt=attempt)
                dispatched = True

            try:
                provider = self.provider_factory()
                provider.max_attempts = 1  # All retries belong to the durable ledger.
                remaining = (self.run.deadline - datetime.now(timezone.utc)).total_seconds()
                async with asyncio.timeout(min(35, remaining)):
                    async with aclosing(provider.stream_request(body, before_send=before_send)) as stream:
                        async for part in stream:
                            text += part.get("text", "")
                            if len(text.encode("utf-8")) > self.policy.context_max_bytes:
                                raise CoreConflict("provider_response_overflow")
                            if part.get("usage") is not None:
                                observed["usage"] = part["usage"]
                            if part.get("provider_id"):
                                observed["request_id"] = part["provider_id"]
                observed["result_hash"] = hashlib.sha256(text.encode()).hexdigest()
                receipt = ledger.Observation.model_validate(observed)
                ledger.complete(
                    self.workspace,
                    self.run,
                    phase.id,
                    receipt,
                    attempt=attempt,
                    latency_ms=round((time.perf_counter() - started) * 1000, 3),
                )
                if receipt.usage and (
                    receipt.usage.prompt_tokens is not None
                    and receipt.usage.prompt_tokens > phase.input_tokens
                    or receipt.usage.completion_tokens is not None
                    and receipt.usage.completion_tokens > phase.output_tokens
                ):
                    raise CoreConflict("provider_usage_exceeded_authorization")
                return text, receipt
            except Exception as exc:
                code = (
                    exc.code
                    if isinstance(exc, ProviderError)
                    else "request_timeout"
                    if isinstance(exc, TimeoutError)
                    else "response_lost"
                    if dispatched
                    else "local_validation_failed"
                )
                if dispatched and (text or observed):
                    code = "response_lost"  # Partial success outweighs a retryable error name.
                try:
                    classification = ledger.fail_attempt(
                        self.workspace,
                        self.run,
                        phase.id,
                        attempt,
                        code,
                        dispatched=dispatched,
                        latency_ms=round((time.perf_counter() - started) * 1000, 3),
                        observation=ledger.Observation.model_validate(observed),
                    )
                except CoreConflict:
                    logging.info(
                        "conversation_provider_receipt_deferred run=%s attempt=%s", self.run.id, attempt
                    )
                    raise exc
                if classification != "RETRYABLE_KNOWN" or attempt >= phase.transport_limit:
                    raise
                delay = retry_delay(attempt, random.random())
                ledger.schedule_retry(self.workspace, self.run, phase.id, attempt, delay)
                await asyncio.sleep(delay)


class ProductionRuntime:
    def __init__(self, policy, accounting, *, model=None, provider_factory=DeepSeekProvider):
        self.policy, self.accounting = policy, accounting
        self.retriever = StructuralEvidenceRetriever(model=model or ModelGateway())
        self.provider_factory = provider_factory

    def prepare(self):
        if datetime.now(timezone.utc) >= self.policy.authorization_deadline:
            return UnavailableRuntime().prepare()
        return Execution(owner=uuid4(), deadline=self.policy.execution_deadline)

    def execute(self, workspace, run):
        # A duplicated worker entry must not finish/fence the current executor.
        core.start_execution(workspace, run)
        try:
            return self._execute(workspace, run)
        except Exception as exc:
            try:
                from citeweave.db import transaction

                with transaction() as db:
                    blocked = ledger.blocks_retry(db, run.id)
                core.finish(
                    workspace,
                    run.conversation_id,
                    run.turn_id,
                    run.id,
                    run.owner,
                    run.fence,
                    "UNKNOWN" if blocked else "FAILED",
                    error_class=type(exc).__name__,
                )
            except CoreConflict:
                # Cancellation/completion/recovery already won the durable race.
                logging.info("conversation_runtime_finish_fenced run=%s", run.id)
            raise

    def _execute(self, workspace, run):
        policy = self.policy
        request, previous = core.execution_input(workspace, run)
        if (
            workspace != policy.workspace_id
            or run.conversation_id != policy.conversation_id
            or request != policy.request
        ):
            raise CoreConflict("runtime_request_not_authorized")
        ledger.authorize_run(
            workspace,
            run,
            ledger.RunAuthorization(
                id=policy.authorization_id,
                run_id=run.id,
                expires_at=policy.authorization_deadline,
                max_calls=policy.max_calls,
                max_input_tokens=policy.max_input_tokens,
                max_output_tokens=policy.max_output_tokens,
                max_yuan=policy.max_yuan,
            ),
        )
        query = policy.history_query or HistoryQuery(scope=request.scope, expected_head=request.expected_head)
        if query.scope != request.scope or query.expected_head != request.expected_head:
            raise CoreConflict("runtime_history_query_conflict")
        history = read_history(
            workspace,
            run.conversation_id,
            query,
            permit=RuntimeHistoryRead(
                run=run, scan_limit=policy.history_scan_limit, statement_ms=policy.history_statement_ms
            ),
        )
        context = InterpretationInput(
            conversation_id=run.conversation_id,
            turn_id=run.turn_id,
            request=request,
            previous=previous,
            history=history,
        )
        calls = RuntimeCalls(workspace, run, policy, self.accounting, self.provider_factory)
        draft = policy.reviewed_interpretation
        # Validate history before any model side effect, even without a draft.
        from citeweave.conversation_interpretation import selected_sources

        selected_sources(context)
        with bounded_stage((run.deadline - datetime.now(timezone.utc)).total_seconds()):
            if draft is None:
                raw, _ = calls.call("interpretation", interpretation_messages(context))
                draft = InterpretationDraft.model_validate_json(raw)
            interpret(context, draft=draft)  # Guard provider drafts before documentary retrieval.
            core.execution_input(workspace, run)
            result, decision = produce(
                workspace,
                run.id,
                context,
                draft=draft,
                retriever=self.retriever,
                generator=ProductionGenerator(calls),
                max_input_bytes=policy.context_max_bytes,
            )
        return core.accept(
            workspace,
            run.conversation_id,
            run.turn_id,
            run.id,
            run.owner,
            run.fence,
            result,
            StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=run.expected_head),
            delta=decision.delta,
            interpretation=(context, draft),
        )


class ProductionGenerator:
    def __init__(self, calls):
        self.calls = calls

    def generate(self, context):
        name = settings().telecom_answer_prompt
        prompt = (ROOT / "prompts" / f"{name}.txt").read_text(encoding="utf-8")
        value, receipt = self.calls.call("generation", generation_messages(context, prompt))
        return Answer(
            run_id=context.run_id,
            text=value,
            citations=validate_citations(value, context.evidence.citations),
            prompt_version=name + ":" + hashlib.sha256(prompt.encode()).hexdigest()[:16],
            usage=receipt.usage.model_dump(exclude_none=True) if receipt.usage else None,
        )


def build_runtime(config=None):
    config = config or settings()
    if (
        not config.conversation_runtime_policy
        or not config.conversation_tokenizer
        or not config.deepseek_api_key.get_secret_value()
        or not (config.database_url.get_secret_value() or config.db_password.get_secret_value())
        or not (config.model_token.get_secret_value() or len(config.admin_token.get_secret_value()) >= 24)
    ):
        return UnavailableRuntime()
    try:
        policy = RuntimePolicy.model_validate_json(Path(config.conversation_runtime_policy).read_bytes())
        # Validate generic limits with the same durable DTO used by grant issuance.
        ledger.RunAuthorization(
            id=policy.authorization_id,
            run_id=UUID(int=0),
            expires_at=policy.authorization_deadline,
            max_calls=policy.max_calls,
            max_input_tokens=policy.max_input_tokens,
            max_output_tokens=policy.max_output_tokens,
            max_yuan=policy.max_yuan,
        )
        if not datetime.now(timezone.utc) < policy.authorization_deadline <= policy.execution_deadline:
            raise ValueError("runtime_deadline_invalid")
        if len({p.purpose for p in policy.phases}) != len(policy.phases):
            raise ValueError("runtime_phase_duplicate")
        return ProductionRuntime(policy, DeepSeekAccounting(config.conversation_tokenizer))
    except (ValueError, OSError):
        return UnavailableRuntime()
