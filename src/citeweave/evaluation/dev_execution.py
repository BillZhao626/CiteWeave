"""Provider-neutral multi-turn evaluation receipts over existing domain workflows.

Only explicit L1 fake execution is exposed by this task. No provider factory,
automatic retry, live policy or DEV execution command exists here. PostgreSQL
backends must use existing admission/acceptance/readback; synthetic DTO backends
cannot claim durable acceptance. Labels are never signed by the runner.
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from citeweave.answering import REFUSAL, validate_citations
from citeweave.conversation_contract import (
    Acceptance,
    Admission,
    CoreConflict,
    HistoryRelation,
    ProducedResult,
    ResolvedConversationDelta,
    Scope,
    SourceRef,
    StateValue,
)
from citeweave.conversation_evidence import CurrentEvidence, assemble, make_result, produce
from citeweave.conversation_history import (
    HistoryQuery,
    HistorySource,
    match_reasons,
    project_state,
    reduce_state,
    within,
)
from citeweave.conversation_interpretation import (
    Ambiguity,
    CriticalTerm,
    FakeInterpreter,
    IntentFact,
    InterpretationDraft,
    InterpretationInput,
    RetrievalRewrite,
    StateCorrection,
    TextSpan,
)
from citeweave.conversation_runtime import generation_messages
from citeweave.evaluation.dev_arms import ARM_IDS, arm, select_arm
from citeweave.evaluation.dev_dataset import DATASET_ID, canonical, digest, identity, load_dev
from citeweave.evaluation.dev_state import evaluation_messages
from citeweave.provider_accounting import serialize_request
from citeweave.schemas import Answer


def frozen_runtime(root):
    names = (
        "prompts/answer-telecom-v1.txt",
        "prompts/conversation-interpretation-v1.txt",
        "uv.lock",
        "src/citeweave/conversation_history.py",
        "src/citeweave/conversation_interpretation.py",
        "src/citeweave/conversation_evidence.py",
        "src/citeweave/conversation_runtime.py",
        "src/citeweave/conversation_history_pg.py",
        "src/citeweave/answering.py",
        "src/citeweave/llm.py",
        "src/citeweave/provider_accounting.py",
        "src/citeweave/costs.py",
        "src/citeweave/evaluation/dev_arms.py",
        "src/citeweave/evaluation/dev_execution.py",
        "src/citeweave/evaluation/dev_dataset.py",
        "src/citeweave/evaluation/dev_fixtures.py",
        "src/citeweave/evaluation/dev_postgres.py",
        "src/citeweave/evaluation/dev_metrics.py",
        "src/citeweave/evaluation/dev_comparison.py",
        "src/citeweave/evaluation/dev_v0.py",
        "src/citeweave/evaluation/dev_review.py",
        "src/citeweave/evaluation/dev_accounting.py",
        "src/citeweave/evaluation/dev_approval.py",
        "src/citeweave/evaluation/dev_state.py",
    )
    return {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names}


class DtoBackend:
    """Original manual fixed-prefix DTO replay only, not a business authority."""

    authority = "SYNTHETIC_DTO_NOT_POSTGRES_ACCEPTANCE"

    def __init__(self, data, view, config, *, mode="FIXED_PREFIX_L1"):
        self.data, self.view, self.config = data, view, config
        self.mode = mode
        self.workspace = identity("workspace")
        self.conversation = identity(view.id + ":" + config.config_hash + ":" + mode + ":conversation")
        self.sources, self.refs = {}, {}
        self.prefix_acceptances = {}
        self.previous = None
        self.raw_fetches = []
        for prefix in view.prefix:
            ref = SourceRef(
                acceptance_id=identity(str(self.conversation) + ":" + prefix.id + ":acceptance"),
                turn_id=identity(str(self.conversation) + ":" + prefix.id),
            )
            puts = []
            if config.state:
                for v in prefix.state:
                    replaced = (identity(str(self.conversation) + ":" + v.replaces),) if v.replaces else ()
                    puts.append(
                        StateValue(
                            id=identity(str(self.conversation) + ":" + prefix.id + ":" + v.key),
                            kind=v.kind,
                            key=v.key,
                            value=v.value,
                            replaces=replaced,
                        )
                    )
            relations = (
                (HistoryRelation(target=self.refs[prefix.correction], kind="correction"),)
                if prefix.correction
                else ()
            )
            request = Admission(
                question=prefix.question,
                scope=self.scope(prefix.scope),
                expected_head=self.previous.id if self.previous else None,
            )
            delta = ResolvedConversationDelta(
                source_turn_id=ref.turn_id,
                previous_snapshot_id=request.expected_head,
                signals=prefix.signals,
                put=tuple(puts),
                relations=relations,
            )
            state = reduce_state(self.previous, ref, request.scope, delta)
            acceptance = Acceptance(
                id=ref.acceptance_id,
                conversation_id=self.conversation,
                turn_id=ref.turn_id,
                run_id=identity(str(ref.turn_id) + ":run"),
                result=ProducedResult(
                    kind="clarification", text="Manual fixed-prefix intent; not a generated technical answer"
                ),
                state=state,
                created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            )
            source = HistorySource(acceptance=acceptance, request=request)
            self.sources[ref] = source
            self.refs[prefix.id] = ref
            self.prefix_acceptances[prefix.id] = acceptance
            self.previous = acceptance

    def scope(self, sids):
        versions = {s.id: s.version_id for s in self.data.sources}
        return Scope(kb_id=identity("kb"), version_ids=tuple(versions[s] for s in sids))

    def history(self, query):
        latest = list(self.refs.values())[-self.config.n :] if self.config.n else []
        recent = tuple(r for r in latest if within(self.sources[r].request.scope, query.scope))
        b = (
            tuple(
                r
                for r, s in self.sources.items()
                if within(s.request.scope, query.scope) and match_reasons(s, query)
            )
            if self.config.b
            else ()
        )
        projection = (
            project_state(self.previous.state, query.scope) if self.previous and self.config.state else ()
        )

        def fetch(refs):
            self.raw_fetches.extend(refs)
            return tuple(self.sources[r] for r in refs if r in self.sources)

        return select_arm(
            self.config.id, recent, b, query, projection, fetch, state_only_intent=self.view.state_only_intent
        )

    def accept(self, run, context, result, decision, draft):
        rid = run.id if hasattr(run, "id") else run
        ref = SourceRef(acceptance_id=identity(str(rid) + ":acceptance"), turn_id=context.turn_id)
        self.last_acceptance = Acceptance(
            id=ref.acceptance_id,
            conversation_id=self.conversation,
            turn_id=context.turn_id,
            run_id=rid,
            result=result,
            state=reduce_state(self.previous, ref, context.request.scope, decision.delta),
            created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        )
        return dict(
            authority=self.authority, accepted_id=None, durable=False, result=result.model_dump(mode="json")
        )


def fixture_draft(view, backend, context):
    """Gold-derived deterministic response for L1 only. Never a semantic model."""
    facts = []
    for kind, value, pid in view.facts:
        if pid == "CURRENT":
            start = view.question.index(value)
            facts.append(
                IntentFact(kind=kind, value=value, span=TextSpan(start=start, end=start + len(value)))
            )
        else:
            ref = backend.refs[pid]
            item = next(
                (
                    e.item.id
                    for e in context.history.state_projection
                    if e.introduced_by == ref and e.item.value == value
                ),
                None,
            )
            facts.append(IntentFact(kind=kind, value=value, source=ref, state_item_id=item))
    corrections = []
    if view.id == "D4.V2":
        start = view.question.index("Beacon-South")
        corrections = [
            StateCorrection(item_id=e.item.id, mention=TextSpan(start=start, end=start + len("Beacon-South")))
            for e in context.history.state_projection
            if e.item.kind == "ambiguity"
        ]
    ambiguities = (
        (Ambiguity(reason="multiple_candidates", candidates=tuple(facts)),)
        if view.dependency == "unresolved"
        else ()
    )
    inherited = list(dict.fromkeys(f.value for f in facts if f.source))
    rewrite = (
        RetrievalRewrite(
            text=view.question + "\n" + "\n".join(inherited),
            scope=context.request.scope,
            retained=context.required,
        )
        if view.dependency == "required"
        else None
    )
    return InterpretationDraft(
        topic_relation=view.topic_relation,
        dependency=view.dependency,
        facts=tuple(facts),
        ambiguities=ambiguities,
        rewrite=rewrite,
        corrections=tuple(corrections),
    )


class FixtureGenerator:
    kind = "DETERMINISTIC_GOLD_DERIVED_FAKE_L1"

    def __init__(self, view, root):
        self.view, self.root = view, root
        self.calls = []

    def generate(self, context):
        prompt = (self.root / "prompts/answer-telecom-v1.txt").read_text(encoding="utf-8")
        messages = generation_messages(context, prompt)
        self.calls.append(
            dict(purpose="generation", messages=messages, context=context.model_dump(mode="json"))
        )
        if self.view.outcome == "evidence_insufficient":
            text = REFUSAL
        else:
            # Return the exact current quote for the required source; no model
            # quality score may be inferred from this constructed response.
            sid = self.view.evidence_support[0][0]
            version = str(identity(sid + ":version:1"))
            c = next(c for c in context.evidence.citations if str(c.document_version_id) == version)
            text = c.span.quote + " [" + c.label + "]"
        return Answer(
            run_id=context.run_id,
            text=text,
            citations=validate_citations(text, context.evidence.citations),
            prompt_version="FAKE_L1_NOT_PROVIDER_QUALITY",
            estimated_yuan=0,
        )


def execute_target(
    backend, run, request, query, *, required, draft_adapter, retriever, generator, max_input_bytes, observe
):
    """Provider-neutral admitted target over existing domain and PG seams.

    Injected adapters own call accounting; a paid adapter must use RuntimeCalls
    and its durable authorization, never a direct provider. This function creates
    no grant, provider or retry. No paid campaign entrypoint is installed.
    """
    from citeweave.conversation_interpretation import selected_sources

    history = backend.history(query)
    observe("history", history)
    run_id = run.id if hasattr(run, "id") else run
    context = InterpretationInput(
        conversation_id=backend.conversation,
        turn_id=run.turn_id if hasattr(run, "turn_id") else identity(str(run_id) + ":turn"),
        request=request,
        previous=backend.previous,
        history=history,
        required=required,
    )
    if history.failure or history.search_incomplete:
        raise CoreConflict(history.failure or "search_incomplete")
    selected_sources(context)  # Incomplete groups fail before any interpretation call.
    draft = draft_adapter(context)
    if backend.config.id == "cp-a-v1" and backend.view.state_only_intent:
        from citeweave.evaluation.dev_state import state_intent

        decision = state_intent(context, draft)
        evidence = retriever.retrieve(backend.workspace, request.scope, decision.selected_query)
        evidence = CurrentEvidence.model_validate(evidence.model_dump(mode="json"))
        assembled = assemble(
            backend.workspace, run_id, context, decision, evidence, max_input_bytes=max_input_bytes
        )
        if not evidence.citations:
            raise CoreConflict("evaluation_current_evidence_required")
        result = make_result(assembled, generator.generate(assembled.model_copy(deep=True)))
        # Existing production acceptance requires raw intent provenance. This
        # diagnostic is an evaluation artifact; never bypass that business guard.
        if hasattr(backend, "fail"):
            backend.fail(run, "evaluation_state_output_not_product_acceptance")
        return result, decision, None
    result, decision = produce(
        backend.workspace,
        run_id,
        context,
        draft=draft,
        retriever=retriever,
        generator=generator,
        max_input_bytes=max_input_bytes,
    )
    accepted = backend.accept(run, context, result, decision, draft)
    return result, decision, accepted


def execute_l1(
    root: Path,
    view_id,
    arm_id,
    *,
    retriever,
    backend_factory=DtoBackend,
    expected_hash=None,
    test_max_input_bytes=None,
    dataset_id=DATASET_ID,
    split="Development",
):
    """A single explicitly selected fake fixture; never a real DEV command."""
    data, dataset_hash = load_dev(root, identity=dataset_id, split=split, expected_hash=expected_hash)
    config = arm(arm_id)
    view = next((v for v in data.views if v.id == view_id), None)
    if view is None:
        raise ValueError("dev_view_rejected")
    backend = backend_factory(data, view, config)
    start = time.perf_counter()
    request = Admission(
        question=view.question,
        scope=backend.scope(view.scope),
        expected_head=backend.previous.id if backend.previous else None,
    )
    run = (
        backend.begin(request)
        if hasattr(backend, "begin")
        else identity(str(backend.conversation) + ":" + view.id + ":target-run")
    )
    run_id = run.id if hasattr(run, "id") else run
    receipt = dict(
        revision="v02a-view-receipt-v1",
        execution_kind="FAKE_L1_NOT_DEV",
        dataset_id=data.dataset_id,
        dataset_hash=dataset_hash,
        view_id=view.id,
        view_hash=view.sha256,
        family=view.family,
        mode=getattr(backend, "mode", "FIXED_PREFIX_L1"),
        control_conditions=dict(
            provider="NONE_L1",
            model="NONE_L1",
            sampling="DETERMINISTIC_FAKE",
            corpus_hash=digest([s.model_dump(mode="json") for s in data.sources]),
            rubric="comparison-descriptive-v1:" + data.protocol_sha256,
            common_config_hash=config.common_hash,
            environment_cache="EXPLICIT_FIXTURE_NO_REMOTE_SERVICES",
        ),
        hard=view.hard,
        split=data.split,
        repeat=1,
        arm_id=config.id,
        arm_config_hash=config.config_hash,
        runtime_sources=frozen_runtime(root),
        conversation_id=str(backend.conversation),
        turn_id=str(run.turn_id) if hasattr(run, "turn_id") else str(identity(str(run_id) + ":turn")),
        run_id=str(run_id),
        authority=backend.authority,
        status="NOT_RUN",
        acceptance=None,
        calls=[],
        external_calls=0,
        retry=0,
        refetch=0,
        judge=0,
        human_review=None,
        semantic_quality=None,
        history=None,
        interpretation=None,
        evidence_identity=None,
        timeout_censored=False,
        raw_fetches=[],
        protected_terms=[list(p) for p in view.protected],
        prefix_receipts=[
            dict(
                prefix_id=p.id,
                question_hash=digest(p.question),
                scope=list(p.scope),
                turn_id=str(backend.prefix_acceptances[p.id].turn_id),
                run_id=str(backend.prefix_acceptances[p.id].run_id),
                acceptance_id=str(backend.prefix_acceptances[p.id].id),
                state_hash=digest(backend.prefix_acceptances[p.id].state.model_dump(mode="json")),
                kind="MANUAL_ACCEPTED_INTENT_SEED_NOT_GENERATED_EVIDENCE",
                external_calls=0,
                durable=backend.authority == "EXISTING_POSTGRES_ADMISSION_ACCEPTANCE",
            )
            for p in view.prefix
        ],
    )
    generator = FixtureGenerator(view, root)
    if getattr(backend, "recovered", None):
        receipt.update(
            status="RECOVERED",
            acceptance=backend.recovered,
            latency_ms=(time.perf_counter() - start) * 1000,
            measurement_scope="recovery_only_not_original_execution",
        )
        return receipt
    try:
        if arm_id == ARM_IDS[0]:
            # Exact legacy structural control serialization, with empty history.
            from citeweave.conversation_evidence import validate_evidence

            material = retriever.retrieve(backend.workspace, request.scope, request.question)
            validate_evidence(backend.workspace, request.scope, material)
            prompt = (root / "prompts/answer-telecom-v1.txt").read_text(encoding="utf-8")
            messages = [
                dict(role="system", content=prompt),
                dict(
                    role="user",
                    content=json.dumps({"question": request.question}, ensure_ascii=False)
                    + "\n"
                    + material.pack.prompt_json,
                ),
            ]
            if sum(len(m["content"]) for m in messages) > 12000:
                raise CoreConflict("prompt_character_limit")
            receipt.update(
                status="V0_SERIALIZATION_CONTROL_ONLY",
                calls=[dict(purpose="generation", messages=messages)],
                evidence_identity=digest(material.pack.model_dump(mode="json")),
                v0_output_limit=1024,
            )
            # This snapshot alone is not a product V0 result. dev_v0 delegates
            # actual execution to the existing admitted single-turn contract.
            receipt["v0_execution_adapter"] = "dev_v0.execute_v0"
            for call in receipt["calls"]:
                call["execution_kind"] = "serialization_only_no_provider_dispatch"
                call["message_sha256"] = hashlib.sha256(serialize_request(call["messages"])).hexdigest()
                call["provider_usage"] = None
            return receipt
        query = HistoryQuery(
            scope=request.scope, expected_head=request.expected_head, signals=view.query_signals
        )

        def draft_adapter(context):
            draft = fixture_draft(view, backend, context)
            if view.dependency != "none" or view.id == "D4.V2":
                fake = FakeInterpreter(draft)
                draft = fake.interpret(context)
                receipt["calls"].append(
                    dict(
                        purpose="interpretation",
                        messages=evaluation_messages(context),
                        fake_calls=fake.calls,
                        reference_output=draft.model_dump_json(),
                    )
                )
            return draft

        def observe(stage, value):
            receipt[stage] = value.model_dump(mode="json")

        result, decision, accepted = execute_target(
            backend,
            run,
            request,
            query,
            required=tuple(CriticalTerm(dimension=k, value=v) for k, v in view.protected),
            draft_adapter=draft_adapter,
            retriever=retriever,
            generator=generator,
            observe=observe,
            max_input_bytes=test_max_input_bytes
            if test_max_input_bytes is not None
            else len(canonical(data.model_dump(mode="json"))),
        )
        receipt["interpretation"] = decision.model_dump(mode="json")
        receipt["acceptance"] = accepted
        if accepted is None:
            receipt["evaluation_output"] = result.model_dump(mode="json")
            receipt["publication"] = "EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED"
        receipt["status"] = "COMPLETED"
        if hasattr(result, "trace"):
            receipt["evidence_identity"] = result.trace.evidence_identity
    except CoreConflict as exc:
        receipt.update(
            status="GUARD_FAILURE",
            failure_stage="history_or_interpretation_or_acceptance",
            error_code=str(exc),
        )
        if hasattr(backend, "fail"):
            backend.fail(run, str(exc))
    finally:
        receipt["calls"].extend(generator.calls)
        receipt["raw_fetches"] = [r.model_dump(mode="json") for r in backend.raw_fetches]
        receipt["latency_ms"] = (time.perf_counter() - start) * 1000
    for call in receipt["calls"]:
        call["execution_kind"] = "fake_not_provider_dispatch"
        call["message_sha256"] = hashlib.sha256(serialize_request(call["messages"])).hexdigest()
        call["provider_usage"] = None
    return receipt


def save_receipt(path, receipt):
    """Write once: callers recover existing durable business truth, never refetch."""
    with path.open("xb") as stream:
        stream.write(canonical(receipt))


def closed_loop_l1(root, arm_id, *, retriever, allow_branch=True, backend_factory=DtoBackend):
    """D4 prewritten clarification branch; separate fake L1 mode, never DEV."""
    data, _ = load_dev(root)
    first = next(v for v in data.views if v.id == data.closed_loop_branch["first"])
    following = next(v for v in data.views if v.id == data.closed_loop_branch["next"])
    backend = backend_factory(data, first, arm(arm_id), mode="CLOSED_LOOP_L1")
    receipt = execute_l1(root, first.id, arm_id, retriever=retriever, backend_factory=lambda *_: backend)
    plan = dict(
        mode="CLOSED_LOOP_L1_NOT_DEV",
        arm_id=arm_id,
        planned=2,
        receipts=[receipt],
        not_run=[following.id],
        branch=data.closed_loop_branch,
    )
    if (
        not allow_branch
        or not receipt.get("acceptance")
        or receipt["acceptance"]["result"]["kind"] != data.closed_loop_branch["required_kind"]
    ):
        plan["branch_status"] = "NOT_TAKEN_NEXT_REMAINS_PLANNED"
        return plan
    accepted = backend.last_acceptance
    ref = SourceRef(acceptance_id=accepted.id, turn_id=accepted.turn_id)
    if hasattr(backend, "sources"):
        backend.sources[ref] = HistorySource(
            acceptance=accepted,
            request=Admission(
                question=first.question, scope=backend.scope(first.scope), expected_head=backend.previous.id
            ),
        )
    backend.previous = accepted
    backend.refs["T2"] = ref
    backend.prefix_acceptances["T2"] = accepted
    backend.view = following
    next_receipt = execute_l1(
        root, following.id, arm_id, retriever=retriever, backend_factory=lambda *_: backend
    )
    next_receipt["prefix_receipts"][-1]["kind"] = "ACTUAL_PRIOR_L1_CONTROL_ACCEPTANCE_NOT_MANUAL_SEED"
    plan.update(receipts=[receipt, next_receipt], not_run=[], branch_status="TAKEN")
    return plan
