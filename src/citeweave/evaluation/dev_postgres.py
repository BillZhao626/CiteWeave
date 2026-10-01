"""Isolated L1 adapter: existing PG admission/acceptance; no production changes.

Metadata search cannot read old questions/answers. Actual raw fetches are restricted
by dev_arms before execution. The scan/statement envelope is the accepted existing
isolated L1 envelope (512 acceptances, 1000ms), not a product deployment policy.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy import select, text

from citeweave import conversations as core
from citeweave.conversation_contract import (
    Acceptance,
    Admission,
    CoreConflict,
    Execution,
    HistoryRelation,
    ProducedResult,
    ResolvedConversationDelta,
    ResolvedSignals,
    RunStatus,
    SourceRef,
    StateSnapshot,
    StateValue,
)
from citeweave.conversation_history import HistorySource, match_reasons, project_state, within
from citeweave.conversation_models import ConversationAcceptanceRow as Accepted
from citeweave.conversation_models import ConversationRunRow as Run
from citeweave.conversation_models import ConversationTurnRow as Turn
from citeweave.db import transaction
from citeweave.evaluation.dev_arms import select_arm
from citeweave.evaluation.dev_dataset import DATASET_HASH, digest, identity
from citeweave.evaluation.dev_execution import DtoBackend, frozen_runtime
from citeweave.settings import ROOT


def require_isolated():
    with transaction() as db:
        row = db.execute(
            text("""SELECT current_database(),
            (SELECT count(*) FROM (SELECT 1 FROM cw5_acceptances LIMIT 513) a),
            (SELECT count(*) FROM (SELECT 1 FROM cw5_turns LIMIT 513) t),
            (SELECT count(*) FROM (SELECT 1 FROM cw5_runs LIMIT 1025) r)""")
        ).one()
    prefix = "cw_conversation_test_"
    if not row[0].startswith(prefix) or len(row[0][len(prefix) :]) != 32:
        raise ValueError("dev_isolated_database_required")
    if (
        UUID(row[0][len(prefix) :]).hex != row[0][len(prefix) :]
        or row[1] > 512
        or row[2] > 512
        or row[3] > 1024
    ):
        raise ValueError("dev_isolated_envelope_exceeded")


class PgBackend(DtoBackend):
    authority = "EXISTING_POSTGRES_ADMISSION_ACCEPTANCE"

    def __init__(self, data, view, config, *, mode="FIXED_PREFIX_L1"):
        require_isolated()
        self.data, self.view, self.config = data, view, config
        self.mode = mode
        self.workspace = identity("workspace")
        key = (
            "l1:"
            + DATASET_HASH[:16]
            + ":"
            + view.sha256[:16]
            + ":"
            + config.config_hash[:16]
            + ":"
            + digest(frozen_runtime(ROOT))[:16]
            + ":"
            + mode
        )
        self.conversation = core.create(self.workspace, key).id
        self.refs, self.raw_fetches = {}, []
        self.prefix_acceptances = {}
        self.previous = None
        for prefix in view.prefix:
            request = Admission(
                question=prefix.question,
                scope=self.scope(prefix.scope),
                expected_head=self.previous.id if self.previous else None,
            )
            run = core.admit(self.workspace, self.conversation, prefix.id, request, self.execution())
            if run.status == RunStatus.ACCEPTED:
                self.previous = core.read_run_id(self.workspace, self.conversation, run.id).accepted
                self.refs[prefix.id] = SourceRef(
                    acceptance_id=self.previous.id, turn_id=self.previous.turn_id
                )
                self.prefix_acceptances[prefix.id] = self.previous
                continue
            if run.status != RunStatus.ADMITTED:
                raise CoreConflict("dev_prior_prefix_not_reexecutable")
            puts = []
            if config.state:
                for v in prefix.state:
                    puts.append(
                        StateValue(
                            id=identity(str(self.conversation) + ":" + prefix.id + ":" + v.key),
                            kind=v.kind,
                            key=v.key,
                            value=v.value,
                            replaces=(identity(str(self.conversation) + ":" + v.replaces),)
                            if v.replaces
                            else (),
                        )
                    )
            delta = ResolvedConversationDelta(
                source_turn_id=run.turn_id,
                previous_snapshot_id=request.expected_head,
                signals=prefix.signals,
                put=tuple(puts),
                relations=(HistoryRelation(target=self.refs[prefix.correction], kind="correction"),)
                if prefix.correction
                else (),
            )
            accepted = core.accept(
                self.workspace,
                self.conversation,
                run.turn_id,
                run.id,
                run.owner,
                run.fence,
                ProducedResult(
                    kind="clarification",
                    text="Manual fixed-prefix intent seed; not generated documentary evidence",
                ),
                StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=request.expected_head),
                delta=delta,
            )
            self.refs[prefix.id] = SourceRef(acceptance_id=accepted.id, turn_id=accepted.turn_id)
            self.previous = accepted
            self.prefix_acceptances[prefix.id] = accepted
        self.run = None
        self.recovered = None

    @staticmethod
    def execution():
        # Protocol campaign absolute per-attempt bound, not a product SLO.
        return Execution(owner=uuid4(), deadline=datetime.now(timezone.utc) + timedelta(seconds=45))

    def begin(self, request):
        self.run = core.admit(self.workspace, self.conversation, self.view.id, request, self.execution())
        if self.run.status == RunStatus.ACCEPTED:
            truth = core.read_run_id(self.workspace, self.conversation, self.run.id)
            self.last_acceptance = truth.accepted
            self.recovered = dict(
                authority=self.authority,
                accepted_id=str(truth.accepted.id),
                durable=True,
                result=truth.accepted.result.model_dump(mode="json"),
                head_id=str(truth.conversation.head.id),
                fence=truth.run.fence,
            )
            return self.run
        if self.run.status != RunStatus.ADMITTED:
            raise CoreConflict("dev_prior_outcome_requires_review_no_retry")
        checked, self.previous = core.execution_input(self.workspace, self.run)
        if checked != request:
            raise CoreConflict("dev_request_identity_mismatch")
        return self.run

    def history(self, query):
        if self.config.b:
            # AB0 is the accepted production history adapter, not a replica of
            # its SQL. Only evaluation-origin attribution is enriched below.
            from citeweave.conversation_history_pg import RuntimeHistoryRead, read_history

            result = read_history(
                self.workspace,
                self.conversation,
                query,
                permit=RuntimeHistoryRead(run=self.run, scan_limit=512, statement_ms=1000),
            )

            def attribute(group):
                if "B" not in group.origins:
                    return group
                return group.model_copy(
                    update={
                        "sources": tuple(
                            s.model_copy(update={"origins": tuple(sorted(set(s.origins) | {"B"}))})
                            for s in group.sources
                        )
                    }
                )

            self.raw_fetches.extend(dict.fromkeys(s.ref for g in result.candidates for s in g.sources))
            return result.model_copy(
                update={
                    "candidates": tuple(attribute(g) for g in result.candidates),
                    "selected": tuple(attribute(g) for g in result.selected),
                }
            )
        # No question/result/old state-entry JSON is selected by this query.
        with transaction() as db:
            db.execute(text("SELECT set_config('statement_timeout','1000',true)"))
            metadata = (
                db.execute(
                    text("""SELECT a.id, a.turn_id, r.fence,
                a.state->'delta'->'signals' AS signals, t.request->'scope' AS scope
                FROM cw5_acceptances a JOIN cw5_turns t ON t.id=a.turn_id
                JOIN cw5_runs r ON r.id=a.run_id
                WHERE a.conversation_id=:conversation AND r.status='ACCEPTED'
                ORDER BY r.fence DESC,a.id LIMIT 513"""),
                    {"conversation": self.conversation},
                )
                .mappings()
                .all()
            )
        if len(metadata) > 512:
            raise CoreConflict("dev_scan_envelope_exceeded")
        recent = []
        b = []
        for index, row in enumerate(metadata):
            from citeweave.conversation_contract import Scope

            ref = SourceRef(acceptance_id=row["id"], turn_id=row["turn_id"])
            if not within(Scope.model_validate(row["scope"]), query.scope):
                continue
            if index < self.config.n:
                recent.append(ref)
            signals = ResolvedSignals.model_validate(row["signals"] or {})
            if self.config.b and match_reasons(SimpleNamespace(ref=ref, signals=signals), query):
                b.append(ref)
        projection = (
            project_state(self.previous.state, query.scope) if self.previous and self.config.state else ()
        )
        trips = 2

        def fetch(refs):
            nonlocal trips
            if trips + 2 > 8:
                raise CoreConflict("dev_history_round_trip_cap")
            trips += 2
            self.raw_fetches.extend(refs)
            with transaction() as db:
                db.execute(text("SELECT set_config('statement_timeout','1000',true)"))
                rows = db.execute(
                    select(Accepted, Turn.request)
                    .join(Turn, Turn.id == Accepted.turn_id)
                    .join(Run, Run.id == Accepted.run_id)
                    .where(
                        Accepted.conversation_id == self.conversation,
                        Accepted.id.in_([r.acceptance_id for r in refs]),
                        Run.status == "ACCEPTED",
                    )
                ).all()
                return tuple(
                    HistorySource(
                        acceptance=Acceptance.model_validate(a), request=Admission.model_validate(q)
                    )
                    for a, q in rows
                )

        result = select_arm(
            self.config.id,
            tuple(recent),
            tuple(b),
            query,
            projection,
            fetch,
            state_only_intent=self.view.state_only_intent,
        )
        return result.model_copy(update={"round_trips": trips})

    def accept(self, run, context, result, decision, draft):
        accepted = core.accept(
            self.workspace,
            self.conversation,
            run.turn_id,
            run.id,
            run.owner,
            run.fence,
            result,
            StateSnapshot(source_turn_id=run.turn_id, previous_snapshot_id=run.expected_head),
            delta=decision.delta,
            interpretation=(context, draft),
        )
        truth = core.read_run_id(self.workspace, self.conversation, run.id)
        if truth.accepted != accepted or truth.run.status != RunStatus.ACCEPTED:
            raise CoreConflict("dev_durable_readback_mismatch")
        self.last_acceptance = accepted
        return dict(
            authority=self.authority,
            accepted_id=str(accepted.id),
            durable=True,
            result=result.model_dump(mode="json"),
            head_id=str(truth.conversation.head.id),
            fence=truth.run.fence,
        )

    def fail(self, run, code):
        core.finish(
            self.workspace, self.conversation, run.turn_id, run.id, run.owner, run.fence, RunStatus.FAILED
        )
