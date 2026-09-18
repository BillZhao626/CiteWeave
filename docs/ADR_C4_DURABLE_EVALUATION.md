# Durable evaluation and source-support measurement

Status: implemented for the Stage-C engineering gate. Quality/default promotion
and paid-provider bulk evaluation remain outside this change.

The old evaluator could return an expired case to PENDING indefinitely and mark
a batch COMPLETED despite failed cases. Migration 0008 adds a finite PG-clock
policy, dispatch outbox and provider-phase ledger. Migrations 0001–0007 and
published source/artifact/index identities are unchanged. Historical terminal
rows keep their results and legacy policy; migration invents no historical
attempts or provider calls. Previously live evaluations receive a created-time
four-hour deadline so they cannot remain pending forever.

Execution attempts (maximum three), transport attempts (maximum thirty with ten
consecutive failures) and admission deferrals (maximum twelve) are distinct.
The first dispatch fixes the active deadline at at most ten minutes within the
run deadline. Owners have UUID/fence/30-second leases and a ten-second heartbeat.
The sweeper checks cancellation and deadlines before recovery or dispatch, even
without a worker. PG unavailability prevents new authorized side effects; after
recovery, the first sweep expires overdue work before sending notifications.

Outbox intent and pre-send attempt accounting commit before Redis publication.
Publication is outside the transaction. Its ACK must match the case generation
and publisher fence. A successful send followed by failed ACK persistence can
duplicate transport messages; generation/state/ownership admission prevents
duplicate effective execution. Celery remains at-least-once transport, with
per-task evaluation soft/hard limits 180/210 seconds. Accepted ingestion timing
and broker visibility settings remain unchanged.

Each logical answer/judge call has at most two phase attempts. PREPARED and
DISPATCHED commit before provider I/O; the active owner, cancellation and
deadlines are rechecked. The wrapper disables DeepSeek's internal retry loop
for the new `provider-phases-v1` runtime. Confirmed pre-execution failures and
rejections can use a remaining phase attempt. A timeout, uncertain 5xx, stream
break or process loss after DISPATCHED becomes UNKNOWN and terminates the case
as OUTCOME_UNKNOWN. Automatic recovery never resends that logical phase.
Visible partial usage stays recorded, while unknown outcomes retain their cost
reservation. An unledgered existing judge reservation is conservatively unknown.

There is an unavoidable commit/send crash window. A request may never have left
the process even though its phase becomes UNKNOWN. Conversely, a request already
sent cannot be recalled by cancellation. This deliberately favors avoiding
duplicate paid requests; it is not distributed exactly-once. Late results append
audit events and cannot overwrite a terminal case. Completion/cancellation races
use PG commit order. A durably completed QueryRun is reused with its original
answer, EvidencePack and citations; only an eligible missing judge runs.

The independent evaluation schema addresses source bytes, published version,
frozen parser/canonical identity and exact source ranges. Support groups admit
alternate range sets and required aspects. Candidate children project through
their atom memberships; unions can span multiple atoms/children, and overlapping
children do not repeatedly earn the same support. Revalidation uses the frozen
canonical geometry plus original source-byte hash, never today's parser over an
old version. Physical citation validity remains separate from semantic judgment.

There are 72 visible AI/source-grounded cases: Development 32, Regression 24,
Safety 16 (8 unanswerable, 4 injection, 4 version/boundary). No real human review
is claimed. Holdout's remaining 24 cases are NOT_YET_SEALED and contain no
implementation-visible content. The procedural freeze/hash/one-decision receipt
mechanism is tested only with an original dummy fixture. Independent Stage-D
custody is still required; local filesystem receipts are not cryptographic access
control. The complete target remains 96 cases, not a completed quality study.

The benchmark harness calls product retrieval/answering and defaults to mock
generation. Every request outcome is preserved; raw-to-summary statistics use
nearest-rank, separate successful latency from all termination latency, and use
wall-clock workload duration for throughput. Dirty-tree diagnostic runs cannot
be final release evidence. Small C4 smokes do not establish speedup, production
P99, eight-person capacity, or target quality improvement.

Rollback requires a reader/executor compatible with the new terminal states.
Stop scheduling or fix forward; never downgrade schema and replay terminal or
UNKNOWN cases with an older worker. A deliberately repeated paid evaluation
requires a new run/key/budget and must retain the original unknown outcome.
