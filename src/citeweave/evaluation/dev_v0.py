"""V0 delegates to the existing structural single-turn SSE execution contract.

Caller supplies an already admitted QueryRun and explicit provider/retriever.
No parallel retrieval, serialization, citation validation or acceptance stack.
The isolated L1 test seeds the legacy admission row and proves execution/readback;
it does not claim a real model tokenizer or paid admission has been verified.
"""

import json

from citeweave.answering import stream_answer


async def execute_v0(run, *, provider, retriever):
    if run.trace_schema_revision != "structural-trace-v1":
        raise ValueError("dev_v0_structural_contract_required")
    events = []
    async for wire in stream_answer(run, provider=provider, retriever=retriever):
        events.append(json.loads(wire.removeprefix("data: ").strip()))
    finals = [e for e in events if e["type"] in {"final", "error"}]
    if len(finals) != 1:
        raise ValueError("dev_v0_terminal_receipt_invalid")
    return dict(
        arm_id="EXISTING_V01_CONTRACT",
        run_id=str(run.id),
        conversation_id=None,
        turn_id=None,
        terminal=finals[0],
        provisional_delta_count=sum(e["type"] == "delta" for e in events),
        serializer="existing-answering.stream_answer",
    )
