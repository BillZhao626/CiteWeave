"""V2 parsing follows durable known observation; synthetic transport, no grant."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_conversation_postgres import isolated_pg as isolated_pg
from test_v02_dev_campaign_postgres import BODY, KEY, Accounting, start

from citeweave.conversation_contract import CoreConflict
from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, ProviderPhaseRow
from citeweave.evaluation import dev_campaign as campaign
from citeweave.evaluation import dev_launcher
from citeweave.settings import settings

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("invalid", [False, True])
@pytest.mark.parametrize(
    "revision", ["synthetic-v2", "interpretation-stabilized-v3", "interpretation-reconciled-v4"]
)
def test_known_completion_and_format_rejection_never_redispatch(monkeypatch, invalid, revision):
    w, p, token = start()
    monkeypatch.setattr(dev_launcher, "require_human", lambda supplied: supplied)
    monkeypatch.setattr(dev_launcher, "live_identities", lambda packet: p.identities)
    monkeypatch.setattr(settings(), "provider_attempts", 1)
    dispatch = campaign.dispatch

    def synthetic_dispatch(*args, **kwargs):
        kwargs["real_transport"] = False
        return dispatch(*args, **kwargs)

    monkeypatch.setattr(campaign, "dispatch", synthetic_dispatch)
    raw = '{"topic_relation":"continue","dependency":"none"' + (',"rewrite":null' if invalid else "") + "}"
    sent = []

    class SyntheticTransport:
        async def stream_request(self, body, *, before_send):
            before_send()
            sent.append(body)
            yield dict(text=raw)
            yield dict(provider_id="synthetic-v2", usage=dict(prompt_tokens=100, completion_tokens=1))

    monkeypatch.setattr(dev_launcher, "DeepSeekProvider", SyntheticTransport)
    context = SimpleNamespace(
        conversation_id=uuid4(),
        turn_id=uuid4(),
        history=SimpleNamespace(state_projection=[], selected=[]),
        previous=None,
        required=(),
        request=SimpleNamespace(question="Independent question"),
    )
    calls = dev_launcher.Calls(
        w,
        p,
        KEY,
        token,
        Accounting(),
        {"interpretation_format_intervention": {"revision": revision}, "normalized_fact_bytes_cap": 400000},
        context=context,
    )
    if invalid:
        error = (
            "reconciliation_schema"
            if revision == "interpretation-reconciled-v4"
            else (
                "stabilization_schema"
                if revision == "interpretation-stabilized-v3"
                else "interpretation_format_schema"
            )
        )
        with pytest.raises(CoreConflict, match=error):
            calls.call("interpretation", BODY["messages"])
        campaign.settle(
            w, p.campaign_id, KEY, token["owner"], {"error_code": "interpretation_format_schema"}, failed=True
        )
    else:
        assert calls.call("interpretation", BODY["messages"]).dependency == "none"
        campaign.settle(w, p.campaign_id, KEY, token["owner"], {"known": True})
    with transaction() as db:
        phase = db.scalar(select(ProviderPhaseRow).where(ProviderPhaseRow.eval_run_id == p.campaign_id))
        assert phase.state == "COMPLETED" and phase.usage == dict(prompt_tokens=100, completion_tokens=1)
        case = db.get(EvalCaseRow, (p.campaign_id, KEY))
        assert case.result["provider_outputs"]["interpretation"] == raw
    assert len(sent) == 1 and p.grant.calls == 0
    with pytest.raises(CoreConflict):
        calls.call("interpretation", BODY["messages"])
    assert len(sent) == 1
