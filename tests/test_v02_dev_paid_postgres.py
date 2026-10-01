"""Prove the actual paid State-only settlement blocker without provider I/O."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from test_conversation_postgres import isolated_pg as isolated_pg
from test_conversation_postgres import pytestmark as pytestmark
from test_v02_dev_postgres import original_sources as original_sources

from citeweave import conversation_provider as ledger
from citeweave.conversation_contract import Admission, CoreConflict
from citeweave.conversation_models import ConversationAcceptanceRow, ConversationRunRow
from citeweave.db import transaction
from citeweave.evaluation.dev_arms import arm
from citeweave.evaluation.dev_dataset import load_dev
from citeweave.evaluation.dev_postgres import PgBackend
from citeweave.settings import ROOT


@pytest.mark.parametrize("view_id", ["D1.V2", "D3.V1"])
def test_completed_paid_state_artifact_cannot_be_disguised_as_failed_or_published(original_sources, view_id):
    data, _ = load_dev(ROOT)
    view = next(v for v in data.views if v.id == view_id)
    backend = PgBackend(data, view, arm("cp-a-v1"))
    run = backend.begin(
        Admission(question=view.question, scope=backend.scope(view.scope), expected_head=backend.previous.id)
    )
    ledger.authorize_run(
        backend.workspace,
        run,
        ledger.RunAuthorization(
            id=uuid4(),
            run_id=run.id,
            expires_at=run.deadline,
            max_calls=1,
            max_input_tokens=1,
            max_output_tokens=1,
            max_yuan=Decimal("0.00001"),
        ),
    )
    phase = ledger.prepare(
        backend.workspace,
        run,
        ledger.CallAuthorization(
            id=uuid4(),
            run_id=run.id,
            purpose="generation",
            provider="deepseek",
            model="deepseek-flash",
            price_revision="deepseek-flash-CNY-2026-09-13",
            prompt_revision="SYNTHETIC_NO_PROVIDER",
            request_hash="0" * 64,
            input_tokens=1,
            output_tokens=1,
            max_yuan=Decimal("0.00001"),
            expires_at=run.deadline,
        ),
    )
    ledger.dispatch(backend.workspace, run, phase.id)  # Durable marker only; NO transport.
    ledger.complete(backend.workspace, run, phase.id, ledger.Observation(result_hash="1" * 64))
    with pytest.raises(CoreConflict, match="provider_outcome_requires_unknown"):
        backend.fail(run, "evaluation_state_output_not_product_acceptance")
    with transaction() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ConversationAcceptanceRow)
                .where(ConversationAcceptanceRow.run_id == run.id)
            )
            == 0
        )
        assert db.get(ConversationRunRow, run.id).status == "ADMITTED"
    # The owner may record uncertainty; it may not manufacture a product acceptance.
    from citeweave import conversations as core

    core.finish(backend.workspace, backend.conversation, run.turn_id, run.id, run.owner, run.fence, "UNKNOWN")
