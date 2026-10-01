"""Real DEV context preparation with fixed PG seeds and production retrieval.

Offline probes are separate Runs, never model executions or quality candidates.
State-only paid targets later belong to EvalCase, not a product Conversation Run.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4, uuid5

from sqlalchemy import text

from citeweave import conversations as core
from citeweave.conversation_contract import Admission, Execution
from citeweave.conversation_evidence import assemble
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_history import HistoryQuery
from citeweave.conversation_interpretation import (
    CriticalTerm,
    InterpretationInput,
    interpret,
    selected_sources,
)
from citeweave.conversation_runtime import generation_messages
from citeweave.db import transaction
from citeweave.evaluation.dev_arms import arm
from citeweave.evaluation.dev_dataset import digest
from citeweave.evaluation.dev_dispatch import (
    generation_input_bound,
    reserves,
    slots_for_view,
    tokenizer_certificate,
)
from citeweave.evaluation.dev_environment import DATABASE, ENVIRONMENT, verify_environment
from citeweave.evaluation.dev_execution import fixture_draft
from citeweave.evaluation.dev_postgres import PgBackend
from citeweave.evaluation.dev_state import evaluation_messages
from citeweave.llm import completion_payload
from citeweave.model_client import ModelGateway


def require_dev_database():
    with transaction() as db:
        if db.scalar(text("SELECT current_database()")) != DATABASE:
            raise ValueError("dev_dedicated_database_required")


class RealDevBackend(PgBackend):
    def __init__(self, data, view, config, *, campaign_id=None):
        super().__init__(
            data,
            view,
            config,
            mode="REAL_DEV_FIXED_PREFIX_V1",
            isolation_check=require_dev_database,
            campaign_id=campaign_id,
        )


def context_for(backend, *, run=None, purpose="probe"):
    request = Admission(
        question=backend.view.question,
        scope=backend.scope(backend.view.scope),
        expected_head=backend.previous.id if backend.previous else None,
    )
    query = HistoryQuery(
        scope=request.scope, expected_head=request.expected_head, signals=backend.view.query_signals
    )
    if backend.config.b and run is None:
        run = core.admit(
            backend.workspace,
            backend.conversation,
            "provider-free-history-probe:" + uuid4().hex,
            request,
            Execution(owner=uuid4(), deadline=datetime.now(timezone.utc) + timedelta(seconds=45)),
        )
    backend.run = run
    try:
        history = backend.history(query)
    finally:
        if backend.config.b and purpose == "probe" and run:
            core.finish(
                backend.workspace, backend.conversation, run.turn_id, run.id, run.owner, run.fence, "FAILED"
            )
    context = InterpretationInput(
        conversation_id=backend.conversation,
        turn_id=run.turn_id if run else uuid5(backend.conversation, backend.view.id + ":evaluation-target"),
        request=request,
        previous=backend.previous,
        history=history,
        required=tuple(CriticalTerm(dimension=k, value=v) for k, v in backend.view.protected),
    )
    return context


def prepare_contracts(root, data, accounting):
    import json

    from citeweave.costs import maximum_cost

    environment = verify_environment()
    previous = json.loads(ENVIRONMENT.read_bytes())
    # The optional additive evaluation migration changes only schema_head.
    if {k: v for k, v in environment.items() if k != "schema_head"} != {
        k: v for k, v in previous.items() if k not in {"schema_head", "approval_id"}
    }:
        raise ValueError("dev_environment_binding_drift")
    output = reserves(root, accounting)
    certificate = tokenizer_certificate(
        root / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json", accounting
    )
    prompt = (root / "prompts/answer-telecom-v1.txt").read_text(encoding="utf-8")
    slots, probes = [], []
    for view in data.views:
        for aid in ("cp-a-v1", "cp-ab0-v1"):
            backend = RealDevBackend(data, view, arm(aid))
            context = context_for(backend)
            purposes = slots_for_view(view, aid)
            if not purposes:
                if context.history.failure != "incomplete_group":
                    raise ValueError("dev_zero_call_guard_not_proven")
                probes.append(dict(view=view.id, arm=aid, guard="incomplete_group", dispatch_slots=[]))
                continue
            selected_sources(context)
            key = view.id + ":" + aid
            probe = dict(
                view=view.id,
                arm=aid,
                context=context.model_dump(mode="json"),
                prefix_ids={k: str(v.id) for k, v in backend.prefix_acceptances.items()},
                dispatch_slots=list(purposes),
                kind="PROVIDER_FREE_REAL_CONTEXT_NOT_DEV",
            )
            if "interpretation" in purposes:
                body = completion_payload(
                    evaluation_messages(context), "deepseek-flash", output["interpretation"]
                )
                measurement = accounting.measure(body)
                slots.append(
                    dict(
                        case=key,
                        purpose="interpretation",
                        input_tokens=measurement["input_tokens"],
                        output_tokens=output["interpretation"],
                    )
                )
                probe["interpretation_request"] = body
                probe["interpretation_measurement"] = measurement
                bound = generation_input_bound(context, prompt, output["interpretation"], certificate)
            else:
                # Pre-reviewed deterministic self-contained intent; no model
                # interpretation, and original query is fixed (no quality tuning).
                draft = fixture_draft(view, backend, context)
                decision = interpret(context, draft=draft)
                retriever = StructuralEvidenceRetriever(model=ModelGateway())
                evidence = retriever.retrieve(
                    backend.workspace, context.request.scope, decision.selected_query
                )
                assembled = assemble(
                    backend.workspace, uuid4(), context, decision, evidence, max_input_bytes=2**63 - 1
                )
                body = completion_payload(
                    generation_messages(assembled, prompt), "deepseek-flash", output["generation"]
                )
                measurement = accounting.measure(body)
                bound = dict(input_tokens=measurement["input_tokens"], exact_future_request_known=True)
                probe["generation_request"] = body
                probe["generation_measurement"] = measurement
                probe["reviewed_independent_draft"] = draft.model_dump(mode="json")
            slots.append(
                dict(
                    case=key,
                    purpose="generation",
                    input_tokens=bound["input_tokens"],
                    output_tokens=output["generation"],
                )
            )
            probe["generation_bound"] = bound
            probes.append(probe)
    if len(slots) != 38:
        raise ValueError("dev_conditional_slot_count_mismatch")
    inputs = sum(s["input_tokens"] for s in slots)
    outputs = sum(s["output_tokens"] for s in slots)
    expected_slots = [
        s for s in slots if not (s["case"].startswith("D4.V1:") and s["purpose"] == "generation")
    ]
    return dict(
        reserves=output,
        tokenizer_certificate=certificate,
        slots=slots,
        probes=probes,
        environment_sha256=digest(environment),
        environment=environment,
        logical_attempts=24,
        max_calls=38,
        protocol_outer_calls=48,
        expected_calls=36,
        input_tokens=inputs,
        output_tokens=outputs,
        total_tokens=inputs + outputs,
        maximum_yuan=str(maximum_cost(inputs, outputs)),
        expected_path_yuan_upper_bound=str(
            maximum_cost(
                sum(s["input_tokens"] for s in expected_slots),
                sum(s["output_tokens"] for s in expected_slots),
            )
        ),
        stage_input_max={
            p: max(s["input_tokens"] for s in slots if s["purpose"] == p)
            for p in ("interpretation", "generation")
        },
        external_calls=0,
        authority="PROPOSED_FINANCIAL_BOUNDS_NOT_HUMAN_GRANT",
    )
