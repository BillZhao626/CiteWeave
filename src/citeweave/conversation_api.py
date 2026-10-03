"""Thin public adapter; default runtime is unavailable, durable reads stay usable."""

import logging
from typing import Protocol
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse

from citeweave import conversations as core
from citeweave.conversation_contract import Execution, RunView
from citeweave.conversation_public import (
    AcceptedResult,
    ConversationEvent,
    ConversationTrace,
    LifecycleEvent,
    PublicConversation,
    PublicRun,
    ResultEvent,
    TurnSubmit,
    accepted_result,
    conversation_view,
    run_view,
    trace_view,
)


class ConversationalRuntime(Protocol):
    def prepare(self) -> Execution:
        """Local side-effect-free server policy; never dispatch under the PG lock."""
        ...

    def execute(self, workspace: UUID, run: RunView) -> None:
        """Use existing core acceptance/finish. Called only for a new admission.

        Exceptions cannot establish a terminal outcome; recover with durable
        readback and explicit core reconciliation. No implicit redispatch.
        """
        ...


class UnavailableRuntime:
    def prepare(self) -> Execution:
        raise HTTPException(503, "conversation_runtime_unavailable")

    def execute(self, workspace: UUID, run: RunView) -> None:
        raise HTTPException(503, "conversation_runtime_unavailable")


def mount(app, principal, runtime: ConversationalRuntime | None = None):
    if runtime is None:
        from citeweave.conversation_runtime import build_runtime

        runtime = build_runtime()

    @app.post("/v1/conversations", response_model=PublicConversation)
    def create(idempotency_key: str = Header(min_length=1, max_length=128), workspace=Depends(principal)):
        return conversation_view(core.create(workspace, idempotency_key))

    @app.get("/v1/conversations/{conversation_id}", response_model=PublicConversation)
    def conversation(conversation_id: UUID, workspace=Depends(principal)):
        return conversation_view(core.read_conversation(workspace, conversation_id))

    @app.post(
        "/v1/conversations/{conversation_id}/turns",
        response_model=PublicRun,
        responses={202: {"model": PublicRun, "description": "Durably admitted; result not yet accepted"}},
    )
    def submit(
        conversation_id: UUID,
        body: TurnSubmit,
        response: Response,
        idempotency_key: str = Header(min_length=1, max_length=128),
        workspace=Depends(principal),
    ):
        run, created = core.admit_once(
            workspace, conversation_id, idempotency_key, body.admission(), runtime.prepare
        )
        if created:
            try:
                runtime.execute(workspace, run)
            except Exception as exc:
                # Do not infer failure/UNKNOWN from a lost commit receipt, expose
                # raw provider errors, or retry. Replaying the key recovers identity.
                logging.error("conversation_runtime_error run=%s class=%s", run.id, type(exc).__name__)
                raise HTTPException(503, "conversation_runtime_outcome_unavailable") from None
        value = run_view(core.read_run_id(workspace, conversation_id, run.id))
        response.status_code = 202 if value.status == "ADMITTED" else 200
        return value

    @app.get("/v1/conversations/{conversation_id}/runs/{run_id}", response_model=PublicRun)
    def run(conversation_id: UUID, run_id: UUID, workspace=Depends(principal)):
        return run_view(core.read_run_id(workspace, conversation_id, run_id))

    @app.post("/v1/conversations/{conversation_id}/runs/{run_id}/cancel", response_model=PublicRun)
    def cancel(conversation_id: UUID, run_id: UUID, workspace=Depends(principal)):
        core.cancel(workspace, conversation_id, run_id)
        return run_view(core.read_run_id(workspace, conversation_id, run_id))

    @app.get("/v1/conversations/{conversation_id}/runs/{run_id}/result", response_model=AcceptedResult)
    def result(conversation_id: UUID, run_id: UUID, workspace=Depends(principal)):
        value = accepted_result(core.read_run_id(workspace, conversation_id, run_id))
        if value is None:
            raise HTTPException(409, "conversation_result_unavailable")
        return value

    @app.get("/v1/conversations/{conversation_id}/runs/{run_id}/trace", response_model=ConversationTrace)
    def trace(conversation_id: UUID, run_id: UUID, workspace=Depends(principal)):
        return trace_view(core.read_run_id(workspace, conversation_id, run_id))

    @app.get(
        "/v1/conversations/{conversation_id}/runs/{run_id}/events",
        response_model=ConversationEvent,
        response_class=StreamingResponse,
        responses={
            200: {
                "content": {
                    "text/event-stream": {"schema": {"$ref": "#/components/schemas/ConversationEvent"}}
                }
            }
        },
    )
    def events(conversation_id: UUID, run_id: UUID, workspace=Depends(principal)):
        # One authorized durable snapshot, no producer tied to this connection.
        value = run_view(core.read_run_id(workspace, conversation_id, run_id))
        values = [ConversationEvent(event=LifecycleEvent(run=value))]
        if value.accepted:
            values.append(ConversationEvent(event=ResultEvent(accepted=value.accepted)))
        return StreamingResponse(
            iter("data: " + event.model_dump_json() + "\n\n" for event in values),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )
