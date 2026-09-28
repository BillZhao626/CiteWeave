# ADR 0006: conversation state authority and effective-turn commit

Status: **PROPOSED / awaiting ADR Human Review** · 2026-09-28

## Context and accepted constraints

[Accepted Architecture](../V02_CONVERSATIONAL_RAG_ARCHITECTURE.md), sections 4, 8 and 11, makes PostgreSQL the durable authority and admits one active Turn/Run per Conversation. A logical Turn may have explicitly retried Runs but at most one effective accepted result. SSE is observation, not acceptance. This ADR text has not been accepted; it is a prerequisite for the [first Feature slice](../specs/07_V02_First_Conversational_Slice.md).

## Proposed decision

Preserve immutable user submissions and input/output state versions. Admission durably captures original intent, scope/profile, expected head, operation identity and execution ownership. Interpretation and generation produce provisional patches only. Accept a validated answer, clarification or evidence-insufficient control result together with its permitted state patch, Citation relationships, head movement and slot release in one PostgreSQL transaction.

Commit checks current authorization, expected head and relevant control version, active Run, owner/fence, deadline and accepted-result uniqueness. Failed/cancelled/stale/invalid Runs cannot advance accepted state; cleanup cannot release another Run's slot. Clarification advances head with unresolved intent, never a guessed entity. Evidence-insufficient results do not turn retrieval absence into a documentary fact.

Same operation identity and fingerprint resolves to the same durable outcome; different content conflicts. Concurrent independent submissions conflict without silent queueing or rebasing. Explicit retry creates a new Run for an unaccepted Turn only while original head/scope assumptions remain valid. UNKNOWN provider outcomes are not automatically sent again. Effective idempotency does not promise physical exactly-once model execution.

The opt-in conversation runtime is managed in-process with bounded ownership, deadlines, cleanup and observation buffers. Disconnection does not cancel. Startup and relevant reads/admission reconcile lost execution idempotently, fence it and expose interrupted state; a connection loss alone is not proof another owner died. Commit outcome uncertainty requires durable readback before further action. Already committed final survives notification loss; automatic provider continuation across restart is not promised.

## Alternatives and consequences

| Alternative | Reason not proposed for this slice |
| --- | --- |
| Browser/Redis authority or latest mutable state only | Cannot preserve accepted identity and historical inputs through refresh/restart |
| Advance state before validation | Failed interpretation/generation contaminates later intent |
| Separate uncoordinated answer and state commits | Answer can succeed while state disappears; needs a different recovery protocol |
| Full event sourcing / branching / silent queue rebase | Adds projection/version/UX obligations without the accepted first-slice need |
| Celery conversation execution | Would add delivery/stream/retry coordination; current restart guarantee needs no new broker responsibility |

This decision requires real transaction/race/restart verification, not only mocks. It keeps more immutable data and needs explicit retention, recovery and conflict UX. Proposed retention/semantic correction behavior belongs to the Feature Spec and must be accepted there; provenance does not prove semantic truth.

## Empirical and deferred details

Timeouts, per-Turn and total Conversation budgets, explicit retry limits and reconciliation scan bounds follow the [Evaluation freeze](../specs/08_V02_Conversational_Evaluation.md). Tables, unique constraints, indexes, lock order and runtime APIs remain implementation design after review; they must enforce the above behavior rather than change it.

All durable additions require Alembic. Preserve optional conversation linkage for new Runs without manufacturing conversation history for v0.1. Before implementation delivery, test isolated PG/blobs backup, v0.1 upgrade, legacy read, new write, pending/commit crashes, retry/cancel races, UNKNOWN, stale head/fence and restore. A code rollback is not a data downgrade; use a reviewed forward fix or matching backup restoration if lossless downgrade is unavailable.

Reevaluate execution transport only after an accepted requirement for automatic cross-restart completion or measured scheduling limits. Do not reopen accepted uniqueness/authority guarantees to improve latency. Acceptance record: **none; Human ADR Review required**.
