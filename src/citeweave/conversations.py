"""PostgreSQL conversation authority. No execution dispatch, provider or public API.

All commands lock Conversation first. The partial unique index is the active slot;
the monotonically increasing Conversation fence invalidates old owners. Each public
function owns its short transaction and returns detached, validated durable DTOs.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from citeweave.catalog import authorized_kb
from citeweave.catalog import fingerprint as json_fingerprint
from citeweave.conversation_contract import (
    Acceptance,
    Admission,
    ConversationView,
    CoreConflict,
    DocumentaryResult,
    Execution,
    Operation,
    ProducedResult,
    Readback,
    ResolvedConversationDelta,
    RunStatus,
    RunView,
    Scope,
    SourceRef,
    StateSnapshot,
    TurnView,
    WorkingState,
    fingerprint,
    require_fence,
    require_head,
    require_owner,
    transition,
)
from citeweave.conversation_models import (
    ConversationAcceptanceRow as Accepted,
)
from citeweave.conversation_models import (
    ConversationRow as Conversation,
)
from citeweave.conversation_models import (
    ConversationRunRow as Run,
)
from citeweave.conversation_models import (
    ConversationTurnRow as Turn,
)
from citeweave.db import transaction
from citeweave.domain import DocumentRow, VersionRow

if TYPE_CHECKING:
    from citeweave.conversation_interpretation import InterpretationDraft, InterpretationInput


def _clock(db):
    return db.scalar(select(func.clock_timestamp()))


def _conversation(db, workspace, identity):
    row = db.scalar(
        select(Conversation)
        .where(Conversation.id == identity, Conversation.workspace_id == workspace)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "conversation_not_found")
    return row


def _scope(db, workspace, scope: Scope, *, current=False):
    # KB -> documents -> versions matches the existing catalog lock direction.
    # Hold authorization/source rows through commit, not across external work.
    authorized_kb(db, scope.kb_id, workspace, lock=True)
    query = (
        select(VersionRow, DocumentRow)
        .join(DocumentRow, DocumentRow.id == VersionRow.document_id)
        .where(VersionRow.id.in_(scope.version_ids), VersionRow.kb_id == scope.kb_id)
        .order_by(DocumentRow.id, VersionRow.id)
        .with_for_update()
    )
    rows = db.execute(query).all()
    if len(rows) != len(scope.version_ids) or any(doc.kb_id != scope.kb_id for _, doc in rows):
        raise HTTPException(404, "conversation_scope_unavailable")
    if current and any(v.status != "READY" or doc.active_version_id != v.id for v, doc in rows):
        raise CoreConflict("scope_changed")


def _active(db, conversation_id):
    return db.scalar(select(Run).where(Run.conversation_id == conversation_id, Run.status == "ADMITTED"))


def _turn(db, conversation_id, turn_id):
    row = db.get(Turn, turn_id)
    if row is None or row.conversation_id != conversation_id:
        raise HTTPException(404, "turn_not_found")
    return row


def _run(db, conversation_id, turn_id, run_id):
    row = db.get(Run, run_id)
    if row is None or row.conversation_id != conversation_id or row.turn_id != turn_id:
        raise HTTPException(404, "conversation_run_not_found")
    return row


def _accepted(db, turn_id):
    return db.scalar(select(Accepted).where(Accepted.turn_id == turn_id))


def _run_view(run, turn):
    value = {field: getattr(run, field) for field in RunView.model_fields if field != "expected_head"}
    return RunView(**value, expected_head=turn.expected_head)


def _view(db, workspace, conversation):
    head = db.get(Accepted, conversation.head_id) if conversation.head_id else None
    if head:
        body = Admission.model_validate(_turn(db, conversation.id, head.turn_id).request)
        _scope(db, workspace, body.scope)
    active = _active(db, conversation.id)
    active_view = None
    if active:
        turn = _turn(db, conversation.id, active.turn_id)
        _scope(db, workspace, Admission.model_validate(turn.request).scope)
        active_view = _run_view(active, turn)
    return ConversationView(
        id=conversation.id,
        head=Acceptance.model_validate(head) if head else None,
        active=active_view,
    )


def create(workspace: UUID, key: str) -> ConversationView:
    key = Operation(key=key).key
    with transaction() as db:
        db.execute(
            insert(Conversation)
            .values(id=uuid4(), workspace_id=workspace, key=key, fence=0)
            .on_conflict_do_nothing(index_elements=["workspace_id", "key"])
        )
        row = db.scalar(
            select(Conversation)
            .where(Conversation.workspace_id == workspace, Conversation.key == key)
            .with_for_update()
        )
        return _view(db, workspace, row)


def _replay(db, conversation_id, key, digest):
    row = db.scalar(select(Run).where(Run.conversation_id == conversation_id, Run.key == key))
    if row is not None and row.fingerprint != digest:
        raise CoreConflict("idempotency_conflict")
    return row


def _new_run(db, conversation, turn, key, digest, execution, retry_of=None):
    if execution.deadline <= _clock(db):
        raise CoreConflict("deadline_elapsed")
    conversation.fence += 1
    run = Run(
        id=uuid4(),
        conversation_id=conversation.id,
        turn_id=turn.id,
        retry_of=retry_of,
        key=key,
        fingerprint=digest,
        owner=execution.owner,
        fence=conversation.fence,
        deadline=execution.deadline,
        status=RunStatus.ADMITTED,
    )
    db.add(run)
    db.flush()
    from citeweave.runtime_reliability import event

    event(db, run, "admitted", to_state="ADMITTED")
    return _run_view(run, turn)


def admit(workspace: UUID, conversation_id: UUID, key: str, body: Admission, execution: Execution) -> RunView:
    return admit_once(workspace, conversation_id, key, body, lambda: execution)[0]


def admit_once(
    workspace: UUID,
    conversation_id: UUID,
    key: str,
    body: Admission,
    execution_factory: Callable[[], Execution],
) -> tuple[RunView, bool]:
    """Core admission receipt: replay never creates or dispatches another attempt.

    The server-only factory supplies ownership/deadline after authorization and
    conflict checks. It must be local and side-effect free (no external work).
    """
    key = Operation(key=key).key
    with transaction() as db:
        conversation = _conversation(db, workspace, conversation_id)
        _scope(db, workspace, body.scope)
        existing = _replay(db, conversation_id, key, fingerprint(body))
        if existing:
            return _run_view(existing, _turn(db, conversation_id, existing.turn_id)), False
        require_head(conversation.head_id, body.expected_head)
        if _active(db, conversation_id):
            raise CoreConflict("conversation_busy")
        _scope(db, workspace, body.scope, current=True)
        execution = execution_factory()
        turn = Turn(
            id=uuid4(),
            conversation_id=conversation_id,
            expected_head=body.expected_head,
            request=body.model_dump(mode="json"),
        )
        db.add(turn)
        db.flush()
        return _new_run(db, conversation, turn, key, fingerprint(body), execution), True


def retry(workspace, conversation_id, turn_id, prior_run_id, key, execution: Execution) -> RunView:
    """Explicit retry of a known terminal attempt. UNKNOWN requires later resolution."""
    key = Operation(key=key).key
    digest = json_fingerprint({"operation": "retry", "turn": str(turn_id), "prior_run": str(prior_run_id)})
    with transaction() as db:
        conversation = _conversation(db, workspace, conversation_id)
        turn = _turn(db, conversation_id, turn_id)
        body = Admission.model_validate(turn.request)
        _scope(db, workspace, body.scope)
        existing = _replay(db, conversation_id, key, digest)
        if existing:
            return _run_view(existing, turn)
        prior = _run(db, conversation_id, turn_id, prior_run_id)
        if _accepted(db, turn_id):
            raise CoreConflict("already_accepted")
        require_head(conversation.head_id, turn.expected_head)
        if _active(db, conversation_id):
            raise CoreConflict("conversation_busy")
        if db.scalar(select(Run.id).where(Run.retry_of == prior.id)) is not None:
            raise CoreConflict("retry_superseded")
        if prior.status not in {"FAILED", "CANCELLED", "INTERRUPTED", "STALE"}:
            raise CoreConflict("retry_not_allowed")
        from citeweave.conversation_provider import blocks_retry

        if blocks_retry(db, prior.id):
            raise CoreConflict("retry_not_allowed")
        _scope(db, workspace, body.scope, current=True)
        return _new_run(db, conversation, turn, key, digest, execution, prior.id)


def accept(
    workspace,
    conversation_id,
    turn_id,
    run_id,
    owner,
    fence,
    result: ProducedResult | DocumentaryResult,
    state: StateSnapshot,
    *,
    delta: ResolvedConversationDelta | None = None,
    interpretation: tuple["InterpretationInput", "InterpretationDraft"] | None = None,
) -> Acceptance:
    # Revalidate nested JSON even when a caller used unchecked model_copy.
    result = type(result).model_validate(result.model_dump(mode="json"))
    if isinstance(result, DocumentaryResult) and interpretation is None:
        raise CoreConflict("documentary_interpretation_required")
    with transaction() as db:
        conversation = _conversation(db, workspace, conversation_id)
        turn = _turn(db, conversation_id, turn_id)
        run = _run(db, conversation_id, turn_id, run_id)
        _scope(db, workspace, Admission.model_validate(turn.request).scope, current=True)
        if _accepted(db, turn_id):
            raise CoreConflict("already_accepted")
        require_head(conversation.head_id, turn.expected_head)
        require_owner(
            run.status, run.owner, run.fence, owner, fence, conversation.fence, run.deadline, _clock(db)
        )
        from citeweave.conversation_provider import unresolved

        if unresolved(db, run.id):
            raise CoreConflict("provider_outcome_unknown")
        if state.source_turn_id != turn.id or state.previous_snapshot_id != turn.expected_head:
            raise CoreConflict("snapshot_identity_conflict")
        acceptance_id = uuid4()
        previous = db.get(Accepted, turn.expected_head) if turn.expected_head else None
        if interpretation is not None:
            from citeweave.conversation_interpretation import interpret, selected_sources

            context, draft = interpretation
            if (
                context.conversation_id != conversation_id
                or context.turn_id != turn_id
                or context.request != Admission.model_validate(turn.request)
                or context.previous != (Acceptance.model_validate(previous) if previous else None)
            ):
                raise CoreConflict("interpretation_input_conflict")
            # Bounded exact identity reads, NOT a second history search/admission.
            # Head lock and immutable bundles make the earlier selection stable;
            # never trust a caller-supplied Acceptance DTO as durable authority.
            sources = selected_sources(context)
            rows = (
                db.execute(
                    select(Accepted, Turn.request, Run.status)
                    .join(Turn, Turn.id == Accepted.turn_id)
                    .join(Run, Run.id == Accepted.run_id)
                    .where(
                        Accepted.conversation_id == conversation_id,
                        Accepted.id.in_([s.acceptance.id for s in sources]),
                    )
                ).all()
                if sources
                else []
            )
            durable = {
                a.id: (Acceptance.model_validate(a), Admission.model_validate(q), status)
                for a, q, status in rows
            }
            for source in sources:
                if durable.get(source.acceptance.id) != (
                    source.acceptance,
                    source.request,
                    RunStatus.ACCEPTED,
                ):
                    raise CoreConflict("interpretation_durable_provenance_conflict")
            checked = interpret(context, draft=draft)
            if (
                checked.delta != delta
                or (checked.mode == "CLARIFY" and checked.control_result != result)
                or (
                    checked.mode != "CLARIFY"
                    and result.kind != "evidence_insufficient"
                    and not isinstance(result, DocumentaryResult)
                )
            ):
                raise CoreConflict("interpretation_control_conflict")
            if isinstance(result, DocumentaryResult):
                from citeweave.conversation_evidence_pg import validate_durable_result

                validate_durable_result(db, workspace, run_id, context, checked, result)
        if delta is not None:
            from citeweave.conversation_history import reduce_state, within

            scope = Admission.model_validate(turn.request).scope
            targets = {r.target.acceptance_id for r in delta.relations}
            if len(targets) > 64:
                raise CoreConflict("relation_cap")
            referenced = (
                db.execute(
                    select(Accepted.id, Accepted.turn_id, Turn.request["scope"])
                    .join(Turn, Turn.id == Accepted.turn_id)
                    .where(Accepted.conversation_id == conversation_id, Accepted.id.in_(targets))
                ).all()
                if targets
                else []
            )
            refs = {SourceRef(acceptance_id=a, turn_id=t) for a, t, _ in referenced}
            if any(r.target not in refs for r in delta.relations):
                raise CoreConflict("accepted_provenance_unavailable")
            if any(not within(Scope.model_validate(s), scope) for _, _, s in referenced):
                raise CoreConflict("relation_scope_unavailable")
            state = reduce_state(
                Acceptance.model_validate(previous) if previous else None,
                SourceRef(acceptance_id=acceptance_id, turn_id=turn.id),
                scope,
                delta,
            )
        elif previous and previous.state.get("revision") == "conversation-state-v2":
            raise CoreConflict("state_revision_downgrade")
        elif isinstance(state, WorkingState):
            raise CoreConflict("resolved_delta_required")
        accepted = Accepted(
            id=acceptance_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            run_id=run_id,
            result=result.model_dump(mode="json"),
            state=state.model_dump(mode="json"),
        )
        db.add(accepted)
        db.flush()
        # Recheck after the insert too: an unexpectedly slow write must not make
        # an expired result effective. A raised conflict rolls the bundle back.
        require_owner(
            run.status, run.owner, run.fence, owner, fence, conversation.fence, run.deadline, _clock(db)
        )
        conversation.head_id = accepted.id
        run.status = transition(run.status, RunStatus.ACCEPTED)
        run.completed_at = _clock(db)
        conversation.fence += 1
        from citeweave.runtime_reliability import event

        event(db, run, "accepted", from_state="ADMITTED", to_state="ACCEPTED")
        db.flush()
        if _clock(db) >= run.deadline:
            raise CoreConflict("deadline_elapsed")
        return Acceptance.model_validate(accepted)


def execution_input(workspace, supplied: RunView):
    """Short preflight; commit repeats all guards after external work."""
    with transaction() as db:
        conversation = _conversation(db, workspace, supplied.conversation_id)
        turn = _turn(db, conversation.id, supplied.turn_id)
        run = _run(db, conversation.id, turn.id, supplied.id)
        request = Admission.model_validate(turn.request)
        _scope(db, workspace, request.scope, current=True)
        require_head(conversation.head_id, turn.expected_head)
        require_owner(
            run.status,
            run.owner,
            run.fence,
            supplied.owner,
            supplied.fence,
            conversation.fence,
            run.deadline,
            _clock(db),
        )
        if supplied != _run_view(run, turn):
            raise CoreConflict("documentary_run_identity_conflict")
        previous = db.get(Accepted, turn.expected_head) if turn.expected_head else None
        return request, Acceptance.model_validate(previous) if previous else None


def finish(
    workspace, conversation_id, turn_id, run_id, owner, fence, target: RunStatus, *, error_class=None
) -> RunView:
    """Owner reports a non-accepted outcome; no stale cleanup may release a new slot."""
    target = RunStatus(target)
    if target not in {RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.UNKNOWN, RunStatus.STALE}:
        raise CoreConflict("illegal_transition")
    with transaction() as db:
        conversation = _conversation(db, workspace, conversation_id)
        turn = _turn(db, conversation_id, turn_id)
        run = _run(db, conversation_id, turn_id, run_id)
        _scope(db, workspace, Admission.model_validate(turn.request).scope)
        # A still-current owner may record UNKNOWN after its deadline. This is
        # terminal bookkeeping, never permission to accept a late result.
        require_fence(run.status, run.owner, run.fence, owner, fence, conversation.fence)
        from citeweave.conversation_provider import blocks_retry

        if target != RunStatus.UNKNOWN and blocks_retry(db, run.id):
            raise CoreConflict("provider_outcome_requires_unknown")
        run.status = transition(run.status, target)
        run.completed_at = _clock(db)
        conversation.fence += 1
        from citeweave.runtime_reliability import event

        event(db, run, "finished", from_state="ADMITTED", to_state=target, error_class=error_class)
        db.flush()
        return _run_view(run, turn)


def reconcile_expired(workspace, conversation_id) -> ConversationView:
    """One bounded durable check. Expiry fences work; never infer death from a socket.

    INTERRUPTED says local ownership ended, not that a provider request failed.
    Durable provider dispatch can require UNKNOWN; accepted results stay authoritative.
    """
    with transaction() as db:
        conversation = _conversation(db, workspace, conversation_id)
        active = _active(db, conversation_id)
        if active and active.deadline <= _clock(db):
            from citeweave.conversation_provider import permanent_failure, reconcile

            target = (
                RunStatus.UNKNOWN
                if reconcile(db, active.id)
                else RunStatus.FAILED
                if permanent_failure(db, active.id)
                else RunStatus.INTERRUPTED
            )
            active.status = transition(active.status, target)
            active.completed_at = _clock(db)
            conversation.fence += 1
            from citeweave.runtime_reliability import event

            event(db, active, "recovered", from_state="ADMITTED", to_state=target)
            db.flush()
        return _view(db, workspace, conversation)


def read_conversation(workspace, conversation_id) -> ConversationView:
    # Lock for a consistent multi-query view under the existing READ COMMITTED
    # default. Readback does not dispatch or change execution state.
    with transaction() as db:
        return _view(db, workspace, _conversation(db, workspace, conversation_id))


def read_run(workspace, conversation_id, key: str) -> Readback:
    key = Operation(key=key).key
    return _read_run(workspace, conversation_id, Run.key == key)


def read_run_id(workspace: UUID, conversation_id: UUID, run_id: UUID) -> Readback:
    return _read_run(workspace, conversation_id, Run.id == run_id)


def _read_run(workspace, conversation_id, identity) -> Readback:
    with transaction() as db:
        conversation = _conversation(db, workspace, conversation_id)
        run = db.scalar(select(Run).where(Run.conversation_id == conversation_id, identity))
        if run is None:
            raise HTTPException(404, "conversation_run_not_found")
        turn = _turn(db, conversation_id, run.turn_id)
        _scope(db, workspace, Admission.model_validate(turn.request).scope)
        accepted = _accepted(db, turn.id)
        from citeweave.runtime_reliability import read_events

        events, truncated = read_events(db, run.id)
        return Readback(
            conversation=_view(db, workspace, conversation),
            turn=TurnView.model_validate(turn),
            run=_run_view(run, turn),
            accepted=Acceptance.model_validate(accepted) if accepted else None,
            unfinished=run.status == RunStatus.ADMITTED,
            deadline_elapsed=run.status == RunStatus.ADMITTED and run.deadline <= _clock(db),
            reliability_events=tuple(e.model_dump(mode="json") for e in events),
            reliability_truncated=truncated,
        )


def start_execution(workspace, supplied: RunView):
    """Claim once under the same durable guards as dispatch; restart never reclaims."""
    from citeweave.conversation_provider import _owned
    from citeweave.runtime_reliability import event

    with transaction() as db:
        run, now = _owned(db, workspace, supplied)
        if run.execution_started_at is not None:
            raise CoreConflict("execution_already_started")
        run.execution_started_at = now
        event(db, run, "execution_started", from_state="ADMITTED", to_state="ADMITTED")
        db.flush()


def cancel(workspace, conversation_id, run_id):
    """Client intent wins only while active; never conceals an unresolved dispatch."""
    from citeweave.conversation_provider import reconcile
    from citeweave.runtime_reliability import event

    with transaction() as db:
        conversation = _conversation(db, workspace, conversation_id)
        run = db.get(Run, run_id)
        if run is None or run.conversation_id != conversation_id:
            raise HTTPException(404, "conversation_run_not_found")
        turn = _turn(db, conversation_id, run.turn_id)
        _scope(db, workspace, Admission.model_validate(turn.request).scope)
        if run.status == RunStatus.ADMITTED:
            reconcile(db, run.id, code="cancel_requested")
            run.status = transition(run.status, RunStatus.CANCELLED)
            run.completed_at = _clock(db)
            conversation.fence += 1
            event(db, run, "cancelled", from_state="ADMITTED", to_state="CANCELLED")
            db.flush()
        return _run_view(run, turn)


def reconcile_batch(workspace, *, limit=32):
    """Bounded operator entry; durable readback, no transport or automatic retry."""
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError("recovery_batch_limit_invalid")
    with transaction() as db:
        identities = list(
            db.scalars(
                select(Conversation.id)
                .join(Run, Run.conversation_id == Conversation.id)
                .where(
                    Conversation.workspace_id == workspace,
                    Run.status == RunStatus.ADMITTED,
                    Run.deadline <= _clock(db),
                )
                .order_by(Run.deadline, Run.id)
                .limit(limit)
            )
        )
    return tuple(reconcile_expired(workspace, identity) for identity in identities)
