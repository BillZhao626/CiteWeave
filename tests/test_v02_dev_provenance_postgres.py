"""Durable wire evidence and known-failure completion; synthetic, zero grant."""

import hashlib

import pytest
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import metadata
from test_v02_dev_campaign_postgres import BODY, KEY, Accounting, start
from test_v02_dev_remediation import policy

from citeweave.conversation_contract import CoreConflict
from citeweave.db import transaction
from citeweave.domain import EvalCaseRow, ProviderPhaseRow
from citeweave.evaluation import dev_campaign as campaign
from citeweave.evaluation.dev_campaign_models import DevCampaignRow
from citeweave.evaluation.dev_launcher import can_continue_known_failure

pytestmark = pytest.mark.integration


def prepared():
    w, p, token = start()
    campaign.record_context(
        w, p.campaign_id, KEY, token["owner"], dict(history="synthetic_attribution", raw_fetches=[])
    )
    phase = campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
    proof = dict(
        campaign_id=str(p.campaign_id),
        measurement=Accounting().measure(BODY),
        semantic_request_sha256="1" * 64,
        execution_provenance=[],
        execution_provenance_sha256="2" * 64,
        semantic_contract_sha256="3" * 64,
    )
    campaign.record_request(w, p.campaign_id, KEY, token["owner"], phase, proof)
    return w, p, token, phase


def test_wire_evidence_precedes_dispatch_and_survives_known_failed_target():
    w, p, token, phase = prepared()
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase).state == "PREPARED"
        recorded = db.get(EvalCaseRow, (p.campaign_id, KEY)).result["request_evidence"]
        assert recorded["generation"]["phase_id"] == str(phase)
    campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
    raw = "invalid local output after known completion"
    campaign.observe(
        w,
        p.campaign_id,
        KEY,
        token["owner"],
        phase,
        dict(
            result_hash=hashlib.sha256(raw.encode()).hexdigest(),
            usage=dict(prompt_tokens=100, completion_tokens=1),
        ),
        known=True,
        output=raw,
    )
    campaign.settle(
        w, p.campaign_id, KEY, token["owner"], dict(error_code="known_schema_failure"), failed=True
    )
    with transaction() as db:
        case = db.get(EvalCaseRow, (p.campaign_id, KEY))
        assert case.result["request_evidence"] == recorded
        assert case.result["provider_outputs"]["generation"] == raw
        assert case.result["target_context"]["history"] == "synthetic_attribution"
        assert db.get(ProviderPhaseRow, phase).state == "COMPLETED"
    assert can_continue_known_failure(
        w, p.campaign_id, KEY, CoreConflict("dev_interpretation_invalid_json_or_schema")
    )
    assert not can_continue_known_failure(w, p.campaign_id, KEY, CoreConflict("dev_semantic_request_drift"))
    for key in p.cases:
        if key == KEY:
            assert campaign.begin(w, p.campaign_id, key)["status"] == "FAILED"
            continue
        current = campaign.begin(w, p.campaign_id, key)
        campaign.settle(w, p.campaign_id, key, current["owner"], dict(guard="synthetic_no_provider"))
    campaign.close_execution(w, p.campaign_id)
    with transaction() as db:
        assert db.get(DevCampaignRow, p.campaign_id).status == "COMPLETE"
    with pytest.raises(CoreConflict):
        campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
    with pytest.raises(CoreConflict):
        campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())


def test_unknown_preserves_wire_evidence_and_cannot_be_completed_or_resumed():
    w, p, token, phase = prepared()
    campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
    campaign.observe(w, p.campaign_id, KEY, token["owner"], phase, {}, known=False)
    with transaction() as db:
        case = db.get(EvalCaseRow, (p.campaign_id, KEY))
        assert case.status == "OUTCOME_UNKNOWN" and case.result["request_evidence"]["generation"][
            "phase_id"
        ] == str(phase)
        assert db.get(DevCampaignRow, p.campaign_id).status == "STOPPED"
        assert case.result["target_context"]["history"] == "synthetic_attribution"
    assert not can_continue_known_failure(w, p.campaign_id, KEY, ValueError("local"))
    with pytest.raises(CoreConflict):
        campaign.close_execution(w, p.campaign_id)


def test_mismatched_wire_evidence_fails_before_dispatch():
    w, p, token = start()
    phase = campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
    bad = dict(
        campaign_id=str(p.campaign_id), measurement={**Accounting().measure(BODY), "request_hash": "0" * 64}
    )
    with pytest.raises(CoreConflict, match="evidence_identity"):
        campaign.record_request(w, p.campaign_id, KEY, token["owner"], phase, bad)
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase).state == "PREPARED"
        assert not db.get(EvalCaseRow, (p.campaign_id, KEY)).result


def test_dynamic_contract_requires_durable_request_evidence_at_dispatch():
    w, scope = metadata()
    baseline = policy("SYNTHETIC")
    p = policy("SYNTHETIC", identities={**baseline.identities, "semantic_contract": "a" * 64})
    campaign.create(w, scope.kb_id, p)
    token = campaign.begin(w, p.campaign_id, KEY)
    phase = campaign.prepare(w, p.campaign_id, KEY, token["owner"], "generation", BODY, Accounting())
    with pytest.raises(CoreConflict, match="request_evidence_missing"):
        campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase).state == "PREPARED"
    proof = dict(
        campaign_id=str(p.campaign_id),
        measurement=Accounting().measure(BODY),
        semantic_request_sha256="1" * 64,
    )
    campaign.record_request(w, p.campaign_id, KEY, token["owner"], phase, proof)
    campaign.dispatch(w, p.campaign_id, KEY, token["owner"], phase, BODY, Accounting(), p.identities)
    with transaction() as db:
        assert db.get(ProviderPhaseRow, phase).state == "DISPATCHED"
        assert db.get(ProviderPhaseRow, phase).input_tokens == 200
        assert (
            db.get(EvalCaseRow, (p.campaign_id, KEY)).result["request_evidence"]["generation"]["measurement"][
                "input_tokens"
            ]
            == 100
        )
    campaign.observe(
        w,
        p.campaign_id,
        KEY,
        token["owner"],
        phase,
        dict(result_hash="1" * 64, usage=dict(prompt_tokens=180, completion_tokens=1)),
        known=True,
    )
    with transaction() as db:
        assert db.get(DevCampaignRow, p.campaign_id).status == "SYNTHETIC"
        assert db.get(ProviderPhaseRow, phase).usage["prompt_tokens"] == 180
