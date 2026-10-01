# Owner data-review revision record — 2026-10-01

The Human Product Owner first reviewed the v1 proposal and returned **HUMAN_DATA_REVIEW = REVISE**. The Owner explicitly permitted active bounded State intent/rewrite across the recent-2 raw boundary in ordinary D1.V2 and D3.V1, with no raw-history rematerialization, old/raw/B coverage or Evidence authority. D3.V2 remains an atomic correction-chain test: R/A incomplete_group before interpretation/generation; AB0 complete T1/T4 via B. D4.V2 removes T2 from the required-history denominator while keeping branch provenance and South evidence.

[V1 review](V02_DEV_DATA_REVIEW_V1.md), [v1 readiness](V02_DEV_READINESS_V1.md) and its exact manifest bytes/hash remain historical. The revised proposal is version 2 and unsigned; [current review](V02_DEV_DATA_REVIEW.md) and [current readiness](V02_DEV_READINESS.md) report exact identity, diagnostic outcomes, evaluation-only State output boundary and remaining paid gates. This is an appended Owner clarification, not an accepted protocol rewrite, Human Gold signature or execution/spending grant. Prior REVISE actual workload is unknown pending Owner reconciliation; no review pool reset.

## Earlier blocker and clarification record (preserved below)

# v0.2a DEV readiness — R window / provenance boundary

Status: **RESOLVED — Human Owner clarification incorporated; historical stop preserved** · 2026-10-01

## Accepted Owner clarification (2026-10-01)

The Owner explicitly resumed the same provider-free readiness task in this chat.
For `cp-r-v1`, recent-2 limits **all raw historical members**, not just roots:
no outside-window provenance fetch and no partial correction group. Missing
members cause incomplete-group/search-incomplete failure, an expected diagnostic
limitation. `cp-a-v1` has the same raw boundary; bounded current Working State
may be carried but must not rematerialize outside-window text. Memory/State is
non-Evidence. `cp-ab0-v1` may admit outside-window relevant sources through B,
then apply complete atomic correction/provenance closure. Production AB0 stays
unchanged.

Unavailable R/A members receive no candidate/final history coverage or historical
text input/token cost. Incomplete groups never count as partial success. AB0's
outside-window and complete-group recovery is attributed to B; state coverage,
correction/supersession and source coverage remain separate. No dataset-label
approval or provider execution permission is implied. The following stop record
and its tests retain what was observed before that clarification; the current
readiness delivery is documented in HANDOFF and V02_DEV_READINESS.md.

## Historical stop record

This is the stop record for the independently authorized provider-free DEV
readiness task. It is not a Comparison Protocol amendment, DEV manifest, dataset
label approval, executable arm registration or candidate result. DEV/HARD/REG
remain NOT_RUN; #5d remains NOT_STARTED. No provider/model/Judge call was made.

## Verified starting point

- HEAD, main and origin/main: `0bfca12302067b9883644def6d313fefdbd78a7e`.
- Accepted tree: `78f44cd46114e1c6d3688612045e09ceb7d1987f`.
- Remote `refs/heads/main` independently matched that commit on 2026-10-01.
- Working tree was clean before this task; single Alembic head: `0011`.
- Created the requested branch: `eval/v0.2a-dev-readiness`.
- Read the accepted Preflight conclusion and current repository contracts. The
  earlier smoke's one-call authorization is consumed and grants this task nothing.

## Exact question that prevents freezing labels and arm identity

[Evaluation §6](specs/08_V02_Conversational_Evaluation.md) defines R as using only
the most recent N accepted Turns, without cross-window state or B. [Comparison
§3](V02_COMPARISON_PROTOCOL.md) specifies recent-2 only, no state/B, with the other
behavior shared with AB0. Its §4 specifies that N controls A and that a correction
or supersession source group is atomic: retain the replaced original and its edges
without activating the replaced hypothesis. D3.V2 requires the complete correction
chain; D3's specific dialogue and labels have not yet been authored or approved.

The unresolved boundary is **whether R's recent-2 restriction applies to every
materialized source member, or only to the source-group roots**. In particular,
when a recent correction points to an accepted Turn outside recent-2:

| Reading requiring an explicit decision | Selection / trace consequence |
| --- | --- |
| All R source members must be recent-2 | Do not fetch the older member. The existing complete-group guard detects the missing member and fails closed. No partial correction group may be used. |
| Recent-2 limits roots; complete provenance closure may cross the window | Fetch the older member solely as correction provenance, without state/B selection. The complete group can be selected and the older member appears in candidate/final source coverage. |

Both preserve the physical indivisibility invariant: the first refuses the
incomplete group; the second keeps it complete. They produce different R failure,
old-source coverage, input/token/cost and B-contribution measurements. Merely
calling the outside-window member "provenance" does not remove its original text
from the interpretation input or from required-source coverage.

This record does **not** assert that both readings are approved, or that the
accepted protocol is invalid. It records the unresolved interpretation before
silently assigning a concrete arm contract or per-arm expectation. The literal
member-limited reading is consistent with Evaluation's "only recent N" language;
the root-limited reading follows the existing AB0 complete-group implementation.
An explicit owner clarification must settle the boundary and metric attribution.
It need not authorize execution, increase N/C/K or change product behavior.

## Bounded provider-free evidence

The new [diagnostic tests](../tests/test_v02_dev_readiness.py) use three original
synthetic accepted history DTOs, independently of D1–D6, CAL and G/REG:

1. T1: "Use Lattice release amber."
2. T2: "Unrelated display task."
3. T3: "Correct the earlier Lattice choice to release violet.", with a correction
   edge to T1. Recent-2 is T2/T3; T1 is distance 3 from the next target.

The existing `select_history` returns `incomplete_group / search_incomplete` when
given T2/T3 only. When given the T1/T3 closure and T2, it selects the intact T1/T3
group, marks T1 superseded, retains only `A` origins and has no state projection.
No gold interpretation, answer or DEV label is supplied by these tests.

The current [PG history adapter](../src/citeweave/conversation_history_pg.py)
uses recursive connected groups followed by root-based recent selection and
member expansion. That is implementation evidence for AB0, not an executable R
contract. [The domain guard](../src/citeweave/conversation_history.py) refuses a
missing relation target. Neither was modified.

These are pure domain DTO diagnostics. They do not prove PostgreSQL authority,
physical PDF validity, a working evaluation runner or semantic answer quality.
They read no dataset file or sealed content and contact no database, index,
tokenizer service or external provider.

## Validation and delivery state

Final provider-free regression: **122 passed, 0 failed, 0 skipped**, including
the two diagnostics; Ruff lint and format passed (182 Python files). Final
commands and audit scope are recorded in HANDOFF. PostgreSQL/Qdrant, frontend,
OpenAPI drift, release script and real-tokenizer payload measurement were not run
and are not claimed PASS. Initial TDD scaffolding failed
collection because the proposed readiness module did not exist. After identifying
the stop condition, that scaffold was replaced with the two bounded domain
diagnostics above; the failed collection is not counted as passing implementation
evidence. No readiness implementation module was introduced.

| Requested deliverable | Exact status at stop |
| --- | --- |
| Commit/tree | No new commit; accepted baseline/tree above, with uncommitted stop record and diagnostics |
| DEV manifest ID/hash | NOT_CREATED / NOT_FROZEN; no substitute legacy or CAL manifest |
| D1–D6 / 12 views | Protocol slots only: D1.V1/V2, D2.V1/V2, D3.V1/V2, D4.V1/V2, D5.V1/V2, D6.V1/V2; no authored labels |
| Hard membership | Unchanged planning identities: D1.V2, D3.V1, D3.V2, D4.V1, D5.V2, D6.V1, D6.V2 |
| Owner data review | NOT_PREPARED / NOT_APPROVED; no AI signature and no complete 12-view review surface |
| Executable V0/R/A/AB0 | Existing V0 single-turn product path only; no new DEV arm/config identity |
| Harness / metrics / comparison | NOT_IMPLEMENTED; no winner, futility or dominance claim |
| Holdout isolation | No sealed content inspected/materialized; no new runner isolation proof |
| Exact external call requirement | UNKNOWN until cases and runtime paths are frozen; protocol ceiling only: interpretation ≤24, generation ≤24, Judge/retry/refetch=0, total ≤48 |
| Token / worst-case CNY | NOT_BOUND; current task actual dispatch=0 and incurred provider cost=0 CNY |
| Review workload | No new owner review consumed; protocol ceiling only: 48 units / 384 minutes, not an exact materialized plan |
| Changed files | HANDOFF.md, docs/README.md, this stop record, tests/test_v02_dev_readiness.py |

The existing pinned accounting/tokenizer identity remains available in production
code. Smoke's `306/1024` and `0.008804 CNY` do not bound DEV; Comparison §5 explicitly
does not allow promoting old `1024` to a conversation safety reserve. No official
rate refresh or new monetary estimate was needed for this stop diagnostic.

Stop follows the user's instruction to record genuine semantic underspecification
before inventing labels. First settle the R window/closure boundary (and its
source-coverage attribution), then resume the already requested provider-free
readiness work. Dataset human review, complete payload/token/deadline/cost binding
and a separate provider execution authorization remain subsequent gates. Do not
commit/push/PR, run DEV/HARD/REG, merge/tag/release or resume Calibration from this
record.
