"""Real runtime/PG with explicitly mocked HTTP transport. No provider requests."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from conversation_evidence_fixtures import FakeModel
from pydantic import SecretStr
from sqlalchemy import select
from test_conversation_evidence_postgres import evidence_case as evidence_case
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark

from citeweave import conversations as core
from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_evidence_pg import StructuralEvidenceRetriever
from citeweave.conversation_interpretation import InterpretationDraft
from citeweave.conversation_runtime import PhasePlan, ProductionRuntime, RuntimePolicy
from citeweave.db import transaction
from citeweave.domain import ProviderPhaseRow
from citeweave.llm import DeepSeekProvider
from citeweave.provider_accounting import request_hash
from citeweave.settings import settings


class SyntheticAccounting:
    identity = "SYNTHETIC-NOT-TOKEN-EVIDENCE"

    def measure(self, body):
        return {"input_tokens": 73, "request_hash": request_hash(body)}


def policy(sample, draft=True):
    deadline = datetime.now(timezone.utc) + timedelta(seconds=60)
    return RuntimePolicy(
        workspace_id=sample[0],
        conversation_id=sample[1],
        request=sample[2],
        execution_deadline=deadline,
        authorization_id=uuid4(),
        authorization_deadline=deadline,
        max_calls=3,
        max_input_tokens=900,
        max_output_tokens=900,
        max_yuan=Decimal("0.008"),
        phases=(
            PhasePlan(purpose="interpretation", input_tokens=300, output_tokens=300),
            PhasePlan(purpose="generation", input_tokens=300, output_tokens=300),
        ),
        history_scan_limit=512,
        history_statement_ms=1000,
        context_max_bytes=131072,
        reviewed_interpretation=InterpretationDraft(topic_relation="continue", dependency="none")
        if draft
        else None,
    )


def runtime(case, monkeypatch, *, draft=True, response=None):
    sample, fixture = case
    monkeypatch.setattr(settings(), "deepseek_api_key", SecretStr("synthetic-key-never-sent"))
    calls = []

    def handler(request):
        body = json.loads(request.content)
        with transaction() as db:
            phase = db.scalar(
                select(ProviderPhaseRow).where(
                    ProviderPhaseRow.conversation_run_id == active.id, ProviderPhaseRow.state == "DISPATCHED"
                )
            )
            assert phase is not None and phase.request_hash == request_hash(body)
        calls.append(body)
        content = response if response is not None else fixture.atom.text + " [E1]"
        if callable(content):
            return content(request)
        chunks = [
            dict(id="mock-response", choices=[dict(delta={"content": content}, finish_reason="stop")]),
            dict(id="mock-response", choices=[], usage={"prompt_tokens": 73, "completion_tokens": 20}),
        ]
        return httpx.Response(
            200, text="".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
        )

    def gateway():
        return DeepSeekProvider(
            transport=httpx.MockTransport(handler), circuit=SimpleNamespace(change=lambda *args: None)
        )

    value = ProductionRuntime(
        policy(sample, draft), SyntheticAccounting(), model=FakeModel(), provider_factory=gateway
    )
    value.retriever = StructuralEvidenceRetriever(model=FakeModel(), branch_query=fixture.branch)
    active = core.admit(*sample[:2], uuid4().hex, sample[2], value.prepare())
    return value, active, calls


def test_generation_only_runtime(evidence_case, monkeypatch):
    value, run, calls = runtime(evidence_case, monkeypatch)
    result = value.execute(evidence_case[0][0], run)
    assert result.result.answer.citations == [evidence_case[1].citation]
    assert len(calls) == 1
    assert core.read_run_id(*evidence_case[0][:2], run.id).run.status == "ACCEPTED"
    with pytest.raises(CoreConflict):
        value.execute(evidence_case[0][0], run)
    assert len(calls) == 1


def test_provider_clarify_bypasses_retrieval_generation(evidence_case, monkeypatch):
    draft = InterpretationDraft(topic_relation="continue", dependency="unresolved")
    value, run, calls = runtime(evidence_case, monkeypatch, draft=False, response=draft.model_dump_json())
    value.retriever = SimpleNamespace(retrieve=lambda *args: pytest.fail("CLARIFY must bypass retrieval"))
    result = value.execute(evidence_case[0][0], run)
    assert result.result.kind == "clarification" and len(calls) == 1


def test_invalid_provider_draft_does_not_retrieve(evidence_case, monkeypatch):
    value, run, calls = runtime(
        evidence_case,
        monkeypatch,
        draft=False,
        response='{"topic_relation":"continue","dependency":"required"}',
    )
    value.retriever = SimpleNamespace(retrieve=lambda *args: pytest.fail("invalid draft retrieved"))
    with pytest.raises(CoreConflict, match="rewrite_required"):
        value.execute(evidence_case[0][0], run)
    truth = core.read_run_id(*evidence_case[0][:2], run.id)
    assert truth.accepted is None and truth.conversation.head is None and len(calls) == 1


@pytest.mark.parametrize("status,expected", [(429, "REJECTED"), (503, "UNKNOWN")])
def test_transport_failure_is_not_ordinary_failed(evidence_case, monkeypatch, status, expected):
    value, run, calls = runtime(evidence_case, monkeypatch, response=lambda request: httpx.Response(status))
    with pytest.raises(Exception):
        value.execute(evidence_case[0][0], run)
    with transaction() as db:
        row = db.scalar(select(ProviderPhaseRow).where(ProviderPhaseRow.conversation_run_id == run.id))
        assert row.state == expected
    assert len(calls) == 1 and core.read_run_id(*evidence_case[0][:2], run.id).accepted is None


def test_response_then_acceptance_failure_never_replays(evidence_case, monkeypatch):
    value, run, calls = runtime(evidence_case, monkeypatch)
    monkeypatch.setattr(
        core,
        "accept",
        lambda *args, **kw: (_ for _ in ()).throw(CoreConflict("synthetic_acceptance_failure")),
    )
    with pytest.raises(CoreConflict):
        value.execute(evidence_case[0][0], run)
    with pytest.raises(CoreConflict):
        value.execute(evidence_case[0][0], run)
    assert len(calls) == 1 and core.read_run_id(*evidence_case[0][:2], run.id).accepted is None


def test_production_history_selector_matches_local_with_complete_corrections(evidence_case):
    from test_conversation_postgres import execution, history_accept

    from citeweave.conversation_contract import HistoryRelation, ResolvedSignals
    from citeweave.conversation_history import HistoryQuery
    from citeweave.conversation_history_pg import LocalHistoryRead, RuntimeHistoryRead, read_history

    sample, _ = evidence_case
    old = history_accept(sample, question="Original receiver", signals=ResolvedSignals(topic="receiver"))
    correction = history_accept(
        sample,
        question="Corrected receiver",
        signals=ResolvedSignals(topic="receiver"),
        relations=(HistoryRelation(kind="correction", target=old.state.source),),
    )
    for _ in range(3):
        history_accept(sample, question="Noise", signals=ResolvedSignals(topic="noise"))
    previous = core.read_conversation(*sample[:2]).head
    request = sample[2].model_copy(update={"expected_head": previous.id})
    run = core.admit(*sample[:2], uuid4().hex, request, execution())
    query = HistoryQuery(
        scope=request.scope, expected_head=previous.id, signals=ResolvedSignals(topic="receiver")
    )
    expected = read_history(*sample[:2], query, permit=LocalHistoryRead())
    permit = RuntimeHistoryRead(run=run, scan_limit=512, statement_ms=1000)
    actual = read_history(*sample[:2], query, permit=permit)
    assert actual.selected == expected.selected and actual.state_projection == expected.state_projection
    assert {s.ref for g in actual.selected for s in g.sources} == {old.state.source, correction.state.source}
    assert actual.round_trips <= 8
    capped = read_history(*sample[:2], query, permit=permit.model_copy(update={"scan_limit": 1}))
    assert capped.failure == "history_scan_envelope_exceeded"
    with pytest.raises(CoreConflict):
        read_history(
            *sample[:2],
            query,
            permit=permit.model_copy(update={"run": run.model_copy(update={"owner": uuid4()})}),
        )
