"""Campaign isolation and explicit request-identity incompatibility; zero transport."""

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import test_conversation_postgres as pg
from sqlalchemy import func, select, text
from test_v02_dev_postgres import original_sources as original_sources

from citeweave import conversations as core
from citeweave.conversation_contract import Admission, CoreConflict
from citeweave.conversation_models import ConversationAcceptanceRow, ConversationRow, ConversationRunRow
from citeweave.db import transaction
from citeweave.evaluation.dev_arms import arm
from citeweave.evaluation.dev_dataset import load_dev
from citeweave.evaluation.dev_postgres import PgBackend
from citeweave.evaluation.dev_real import context_for
from citeweave.evaluation.dev_state import evaluation_messages
from citeweave.llm import completion_payload
from citeweave.provider_accounting import DeepSeekAccounting, serialize_request

isolated_pg = pg.isolated_pg
pytestmark = pg.pytestmark
ROOT = Path(__file__).resolve().parents[1]


def backend(view_id, aid, campaign_id=None):
    data, _ = load_dev(ROOT)
    view = next(v for v in data.views if v.id == view_id)
    return PgBackend(data, view, arm(aid), mode="REAL_DEV_FIXED_PREFIX_V1", campaign_id=campaign_id)


def admit(b):
    return b.begin(
        Admission(
            question=b.view.question,
            scope=b.scope(b.view.scope),
            expected_head=b.previous.id if b.previous else None,
        )
    )


@pytest.mark.parametrize("view_id", [f"D{i}.V{j}" for i in range(1, 7) for j in (1, 2)])
@pytest.mark.parametrize("aid", ["cp-a-v1", "cp-ab0-v1"])
def test_all_cases_two_campaigns_isolated_same_campaign_stable(original_sources, view_id, aid):
    first_id, second_id = uuid4(), uuid4()
    a, b = backend(view_id, aid, first_id), backend(view_id, aid, second_id)
    again = backend(view_id, aid, first_id)
    assert a.conversation == again.conversation != b.conversation
    assert a.prefix_acceptances == again.prefix_acceptances
    assert a.prefix_acceptances.keys() == b.prefix_acceptances.keys()
    assert not {s.id for s in a.prefix_acceptances.values()} & {s.id for s in b.prefix_acceptances.values()}
    if (view_id, aid) in {("D1.V2", "cp-a-v1"), ("D3.V1", "cp-a-v1"), ("D3.V2", "cp-a-v1")}:
        with transaction() as db:
            heads = list(db.execute(select(ConversationRow.id, ConversationRow.head_id)))
            count = db.scalar(select(func.count()).select_from(ConversationAcceptanceRow))
        context_for(a)
        with transaction() as db:
            assert list(db.execute(select(ConversationRow.id, ConversationRow.head_id))) == heads
            assert db.scalar(select(func.count()).select_from(ConversationAcceptanceRow)) == count
            assert not db.scalar(
                select(ConversationRunRow.id).where(
                    ConversationRunRow.conversation_id == a.conversation,
                    ConversationRunRow.key == view_id,
                )
            )
    else:
        ra, rb = admit(a), admit(b)
        assert ra.id != rb.id
        assert admit(again).id == ra.id


def test_failed_old_target_is_not_reopened_and_new_campaign_has_new_run(original_sources):
    old = backend("D1.V1", "cp-a-v1")
    old_run = admit(old)
    core.finish(
        old.workspace, old.conversation, old_run.turn_id, old_run.id, old_run.owner, old_run.fence, "FAILED"
    )
    with transaction() as db:
        before = db.scalar(text("SELECT to_jsonb(r) FROM cw5_runs r WHERE id=:id"), {"id": old_run.id})
    new_id = uuid4()
    fresh = backend("D1.V1", "cp-a-v1", new_id)
    new_run = admit(fresh)
    assert new_run.id != old_run.id and fresh.conversation != old.conversation
    core.finish(
        fresh.workspace,
        fresh.conversation,
        new_run.turn_id,
        new_run.id,
        new_run.owner,
        new_run.fence,
        "FAILED",
    )
    with pytest.raises(CoreConflict, match="prior_outcome_requires_review_no_retry"):
        admit(backend("D1.V1", "cp-a-v1", new_id))
    with transaction() as db:
        assert (
            db.scalar(text("SELECT to_jsonb(r) FROM cw5_runs r WHERE id=:id"), {"id": old_run.id}) == before
        )


def test_new_prefix_identity_changes_frozen_serializer_request_bytes(original_sources, record_property):
    """Counterexample to conditional paid admission, not an approved hash update."""
    a, b = backend("D1.V1", "cp-a-v1", uuid4()), backend("D1.V1", "cp-a-v1", uuid4())
    ca, cb = context_for(a, run=admit(a), purpose="target"), context_for(b, run=admit(b), purpose="target")
    messages = [evaluation_messages(c) for c in (ca, cb)]
    assert messages[0][0] == messages[1][0]  # identical accepted prompt
    bodies = [completion_payload(m, "deepseek-flash", 1561) for m in messages]
    hashes = [hashlib.sha256(serialize_request(body)).hexdigest() for body in bodies]
    assert hashes[0] != hashes[1]
    # Provenance UUIDs are actually sent, not merely local metadata.
    for c, m in zip((ca, cb), messages):
        refs = [s.ref for g in c.history.selected for s in g.sources]
        assert refs and all(str(r.acceptance_id) in m[1]["content"] for r in refs)
    path = ROOT / ".runtime/provider-accounting/static_tokenizers_v41_tokenizer.json"
    if path.exists():
        accounting = DeepSeekAccounting(path)
        measured = [accounting.measure(body) for body in bodies]
        assert measured[0]["request_hash"] != measured[1]["request_hash"]
        for i, receipt in enumerate(measured):
            record_property(f"campaign_{i}_measurement", json.dumps(receipt))
        frozen = ROOT / ".runtime/evaluation/0012-accepted-runtime/contracts.json"
        if frozen.exists():
            packet = json.loads(frozen.read_bytes())
            probe = next(p for p in packet["probes"] if p["view"] == "D1.V1" and p["arm"] == "cp-a-v1")
            old = probe["interpretation_request"]
            assert bodies[0]["messages"][0] == old["messages"][0]

            def semantic(value):
                if isinstance(value, dict):
                    return {k: semantic(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [semantic(v) for v in value]
                if isinstance(value, str):
                    try:
                        UUID(value)
                        return "<provenance-uuid>"
                    except ValueError:
                        pass
                return value

            assert semantic(json.loads(bodies[0]["messages"][1]["content"])) == semantic(
                json.loads(old["messages"][1]["content"])
            )
            expected = probe["interpretation_measurement"]
            assert measured[0]["request_hash"] != expected["request_hash"]
            record_property("frozen_measurement", json.dumps(expected))
            record_property("conditional_paid_admission", "FAIL_REQUEST_HASH_INVARIANCE")
