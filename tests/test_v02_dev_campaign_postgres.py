"""Real isolated PG, synthetic markers only, no external I/O or positive grant."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import metadata
from test_v02_dev_remediation import policy

from citeweave.conversation_contract import CoreConflict
from citeweave.conversation_models import ConversationAcceptanceRow, ConversationRow
from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, ProviderPhaseRow
from citeweave.evaluation import dev_campaign as campaign
from citeweave.evaluation.dev_campaign_models import DevCampaignRow
from citeweave.llm import completion_payload
from citeweave.provider_accounting import request_hash

pytestmark = pytest.mark.integration


class Accounting:
    reserved = ()

    class tokenizer:
        @staticmethod
        def encode(raw, *, add_special_tokens):
            from types import SimpleNamespace

            return SimpleNamespace(ids=list(raw.encode()))

    def measure(self, body):
        return dict(input_tokens=100, output_tokens=body["max_tokens"], request_hash=request_hash(body))


BODY = completion_payload(
    [dict(role="system", content="synthetic"), dict(role="user", content="no IO")], "deepseek-flash", 100
)
KEY = "D1.V2:cp-a-v1"


def start(mode="SYNTHETIC"):
    workspace, scope = metadata()
    p = policy(mode)
    campaign.create(workspace, scope.kb_id, p)
    token = campaign.begin(workspace, p.campaign_id, KEY)
    return workspace, p, token


def marker(workspace, p, token, purpose="generation"):
    phase = campaign.prepare(workspace, p.campaign_id, KEY, token["owner"], purpose, BODY, Accounting())
    campaign.dispatch(workspace, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
    return phase


def test_disabled_is_zero_and_no_provider_construction(monkeypatch):
    import citeweave.llm as llm

    monkeypatch.setattr(llm.DeepSeekProvider, "__init__", lambda *a, **k: pytest.fail("no provider"))
    workspace, scope = metadata()
    p = policy()
    campaign.create(workspace, scope.kb_id, p)
    with pytest.raises(CoreConflict, match="disabled_or_stopped"):
        campaign.begin(workspace, p.campaign_id, KEY)
    with transaction() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ProviderPhaseRow)
                .where(ProviderPhaseRow.eval_run_id == p.campaign_id)
            )
            == 0
        )


@pytest.mark.parametrize("key", ["D1.V2:cp-a-v1", "D3.V1:cp-a-v1"])
def test_known_state_only_settlement_no_acceptance_head_or_redispatch(monkeypatch, key):
    monkeypatch.setattr(__import__(__name__), "KEY", key)
    if key != "D1.V2:cp-a-v1":
        original = policy
        monkeypatch.setattr(
            __import__(__name__),
            "policy",
            lambda mode: original(
                mode,
                slots=[
                    dict(case=key, purpose=p, input_tokens=200, output_tokens=100)
                    for p in ("interpretation", "generation")
                ],
            ),
        )
    w, p, token = start()
    with transaction() as db:
        before = db.scalar(select(func.count()).select_from(ConversationAcceptanceRow))
        heads = list(db.execute(select(ConversationRow.id, ConversationRow.head_id)))
    phase = marker(w, p, token)
    campaign.observe(
        w,
        p.campaign_id,
        KEY,
        token["owner"],
        phase,
        dict(result_hash="1" * 64, usage=dict(prompt_tokens=100, completion_tokens=40)),
        known=True,
    )
    artifact = dict(kind="documentary_answer", text="synthetic evaluation result")
    receipt = campaign.settle(w, p.campaign_id, KEY, token["owner"], artifact)
    assert receipt["publication"] == "EVALUATION_ONLY_NOT_PRODUCT_ACCEPTED"
    assert campaign.begin(w, p.campaign_id, KEY)["result"] == receipt
    assert campaign.settle(w, p.campaign_id, KEY, token["owner"], artifact) == receipt
    with pytest.raises(CoreConflict):
        campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
    with transaction() as db:
        assert db.scalar(select(func.count()).select_from(ConversationAcceptanceRow)) == before
        assert list(db.execute(select(ConversationRow.id, ConversationRow.head_id))) == heads
        row = db.get(ProviderPhaseRow, phase)
        assert row.state == "COMPLETED" and row.reserved_yuan == Decimal("0.001")
        assert row.usage == dict(prompt_tokens=100, completion_tokens=40)


def test_unknown_is_durable_campaign_stop_and_reservation_is_retained():
    w, p, token = start()
    phase = marker(w, p, token, "interpretation")
    campaign.observe(w, p.campaign_id, KEY, token["owner"], phase, {}, known=False)
    for action in (
        lambda: campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting()),
        lambda: campaign.begin(w, p.campaign_id, "D2.V1:cp-a-v1"),
        lambda: campaign.dispatch(
            w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities
        ),
    ):
        with pytest.raises(CoreConflict):
            action()
    with transaction() as db:
        assert db.get(DevCampaignRow, p.campaign_id).status == "STOPPED"
        assert db.get(ProviderPhaseRow, phase).state == "UNKNOWN"
        assert db.get(ProviderPhaseRow, phase).reserved_yuan == Decimal("0.001")


@pytest.mark.parametrize(
    "dimension,value",
    [
        ("calls", 0),
        ("input_tokens", 99),
        ("output_tokens", 99),
        ("total_tokens", 199),
        ("yuan", "0.00099999"),
    ],
)
def test_each_campaign_budget_dimension_before_phase_creation(dimension, value):
    workspace, scope = metadata()
    p = policy("SYNTHETIC")
    values = p.proposed.model_dump()
    values[dimension] = value
    p = campaign.DevPolicy.model_validate({**p.model_dump(), "proposed": values})
    campaign.create(workspace, scope.kb_id, p)
    token = campaign.begin(workspace, p.campaign_id, KEY)
    with pytest.raises(CoreConflict, match="budget_exceeded"):
        campaign.prepare(workspace, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
    with transaction() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ProviderPhaseRow)
                .where(ProviderPhaseRow.eval_run_id == p.campaign_id)
            )
            == 0
        )


def test_cancel_stops_new_dispatch_but_retains_dispatched_accounting():
    w, p, token = start()
    phase = marker(w, p, token)
    campaign.cancel(w, p.campaign_id)
    with pytest.raises(CoreConflict):
        campaign.begin(w, p.campaign_id, "D2.V1:cp-a-v1")
    campaign.observe(w, p.campaign_id, KEY, token["owner"], phase, dict(result_hash="2" * 64), known=True)
    receipt = campaign.settle(w, p.campaign_id, KEY, token["owner"], {"late": "known"})
    assert campaign.begin(w, p.campaign_id, KEY)["result"] == receipt
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase).reserved_yuan == Decimal("0.001")
        assert db.get(DevCampaignRow, p.campaign_id).status == "STOPPED"


def test_expired_dispatched_phase_recovers_unknown_and_never_dispatches():
    w, p, token = start()
    phase = marker(w, p, token)
    # Database clock is authoritative; shorten immutable deadline only by
    # moving the injected clock, rather than mutating a frozen authorization.
    original = campaign._lock
    from datetime import timedelta

    def later(db, campaign_id, workspace):
        row, policy_value, now = original(db, campaign_id, workspace)
        return row, policy_value, now + timedelta(seconds=60)

    from unittest.mock import patch

    with patch.object(campaign, "_lock", later), pytest.raises(CoreConflict, match="unknown"):
        campaign.begin(w, p.campaign_id, "D2.V1:cp-a-v1")
    assert campaign.begin(w, p.campaign_id, KEY)["status"] == "OUTCOME_UNKNOWN"
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase).state == "UNKNOWN"


def test_review_is_prospective_finite_and_does_not_rewrite_gold():
    w, p, _ = start()
    campaign.record_review(
        w, p.campaign_id, "OUTPUT:" + KEY, "1" * 64, 288, reviewer="synthetic fixture", decision="APPROVE"
    )
    with pytest.raises(CoreConflict, match="review_capacity"):
        campaign.record_review(
            w, p.campaign_id, "DISPUTE:D1.V2", "2" * 64, 1, reviewer="synthetic fixture", decision="DISPUTED"
        )
    with transaction() as db:
        receipt = db.get(DevCampaignRow, p.campaign_id).review["OUTPUT:" + KEY]
        assert receipt["minutes"] == 288 and receipt["recorded_at"]


def test_concurrent_targets_and_duplicate_phases_are_fenced():
    w, p, token = start()
    with pytest.raises(CoreConflict, match="parallel"):
        campaign.begin(w, p.campaign_id, "D2.V1:cp-a-v1")

    def reserve():
        try:
            return campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
        except CoreConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda _: reserve(), range(2)))
    assert sum(r is not None for r in result) == 1


def test_migration_policy_immutable_and_completion_readback():
    w, p, token = start()
    with pytest.raises(IntegrityError), transaction() as db:
        db.execute(
            text("UPDATE cw6_dev_campaigns SET policy=policy||CAST(:patch AS jsonb) WHERE id=:id"),
            dict(id=p.campaign_id, patch='{"increased":true}'),
        )
    with transaction() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0012"
        assert db.get(EvalCaseRow, (p.campaign_id, KEY)).execution_attempt == 1


def test_saved_slot_cannot_be_reassigned_and_input_is_recounted():
    w, p, token = start()
    with pytest.raises(CoreConflict, match="request_bound"):
        campaign.prepare(w, p.campaign_id, KEY, token["owner"], "judge", BODY, Accounting())
    phase = campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
    changed = dict(BODY, max_tokens=101)
    with pytest.raises(CoreConflict):
        campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, changed, Accounting(), p.identities)
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase).state == "PREPARED"


@pytest.mark.parametrize(
    "raw,uncertain", [("known synthetic output", False), ("{", False), ("partial", True)]
)
def test_call_bridge_known_invalid_and_unknown_with_zero_grant(monkeypatch, raw, uncertain):
    """Test-only bypass of Human admission, SYNTHETIC ledger, fake transport.

    The real launcher never admits this zero-grant mode (separate sentinel test).
    No positive authorization, account key, HTTP client or provider is used.
    """
    from citeweave.evaluation import dev_launcher
    from citeweave.settings import settings

    w, p, token = start()
    monkeypatch.setattr(dev_launcher, "require_human", lambda supplied: supplied)
    monkeypatch.setattr(dev_launcher, "live_identities", lambda packet: p.identities)
    monkeypatch.setattr(settings(), "provider_attempts", 1)
    original_dispatch = campaign.dispatch

    def synthetic_dispatch(*args, **kwargs):
        kwargs["real_transport"] = False
        return original_dispatch(*args, **kwargs)

    monkeypatch.setattr(campaign, "dispatch", synthetic_dispatch)
    sent = []

    class SyntheticTransport:
        async def stream_request(self, body, *, before_send):
            before_send()
            sent.append(body)
            yield dict(text=raw)
            if uncertain:
                raise TimeoutError("synthetic truncated stream")
            yield dict(usage=dict(prompt_tokens=100, completion_tokens=1))

    monkeypatch.setattr(dev_launcher, "DeepSeekProvider", SyntheticTransport)
    calls = dev_launcher.Calls(w, p, KEY, token, Accounting(), {})
    purpose = "interpretation" if raw == "{" else "generation"
    if uncertain:
        with pytest.raises(TimeoutError):
            calls.call(purpose, BODY["messages"])
        assert campaign.begin(w, p.campaign_id, KEY)["status"] == "OUTCOME_UNKNOWN"
    elif raw == "{":
        with pytest.raises(CoreConflict, match="invalid_json_or_schema"):
            calls.call(purpose, BODY["messages"])
        campaign.settle(w, p.campaign_id, KEY, token["owner"], {"invalid": True}, failed=True)
        assert campaign.begin(w, p.campaign_id, KEY)["status"] == "FAILED"
    else:
        assert calls.call(purpose, BODY["messages"]) == raw
        campaign.settle(w, p.campaign_id, KEY, token["owner"], {"text": raw})
    assert len(sent) == 1 and p.grant.calls == 0 and p.grant.yuan == 0
    with transaction() as db:
        phase = db.scalar(select(ProviderPhaseRow).where(ProviderPhaseRow.eval_run_id == p.campaign_id))
        assert phase.reserved_yuan == Decimal("0.001")
        assert phase.state == ("UNKNOWN" if uncertain else "COMPLETED")


def test_synthetic_marker_never_authorizes_real_transport():
    w, p, token = start()
    phase = campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
    with pytest.raises(CoreConflict, match="durable_human_authorization"):
        campaign.dispatch(
            w,
            p.campaign_id,
            KEY,
            token["owner"],
            phase,
            BODY,
            Accounting(),
            p.identities,
            real_transport=True,
        )
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase).state == "PREPARED"
