# ADR 0008: bounded context, relevant history and optional Summary

Status: **PROPOSED / awaiting ADR Human Review** · 2026-09-28

## Context and accepted constraints

[Accepted Architecture](../V02_CONVERSATIONAL_RAG_ARCHITECTURE.md), sections 6–7, accepts A+B history and Relevance first, Recency second. The [first Feature](../specs/07_V02_First_Conversational_Slice.md) must work without Summary. Candidate retrieval, state and actual generation context are different bounded inputs; a bounded EvidencePack alone does not bound the whole prompt.

## Proposed decision

Use recent accepted Turns and structured state (A), plus PostgreSQL-backed retrieval/filtering over the searchable accepted history of the same Conversation (B). Bound reads and candidate materialization without restricting searchable history to a recent window. Keep original Turn provenance and supersession relations so an old topic remains findable after leaving active state. No vector conversation index or new memory database.

Separate candidate generation from final context selection. Record branch counts, source groups, selection/exclusion reasons, budget losses and search incompleteness. Relevance must be established before recency can break ties. A recent-only arm is an evaluation diagnostic, not permission to drop the accepted A+B product boundary.

The assembler takes original query, explicit constraints, validated interpreted state, selected historical source groups, current documentary EvidencePack and output reserve. Preserve mandatory query/negation/entity/version/time/scope and necessary reference provenance. Bound state and treat nonessential history as elastic. Count full serialization/framing with an identified tokenizer, separately for interpretation and generation. Retain the existing complete pack/coverage/offset contract; no fixed percentage allocation or silent evidence shrinkage.

If mandatory content plus complete pack cannot fit, follow the Feature's explicit overflow failure; do not manufacture evidence-insufficient success. Clarification is for genuine ambiguity within its own bounded payload. Current state snapshots remain immutable even when a particular Run serializes only a bounded projection.

Summary is absent in the first slice. A future Summary may only be a versioned lossy derivative with source coverage, retained originals and old Run input versions, independent publication, validation and fallback. This ADR does not authorize its implementation, automatic jobs or Celery extension.

## Alternatives and consequences

| Alternative | Trade-off / why deferred or rejected |
| --- | --- |
| Full transcript or ever-growing state | Easy assembly but unbounded cost and topic contamination |
| Recent-only or recency-led score | Cheap but systematically excludes old relevant constraints |
| Single opaque score for retrieval and selection | Hides whether missing information was never found or later discarded |
| Fixed budget percentages / cut any string until it fits | Cannot preserve constraints, pack coverage and immutable quote boundaries |
| Vector memory / mandatory rolling Summary | Extra authorization/version/rebuild/semantic-loss burden; no demonstrated first-slice need |

Selection can still miss lexical paraphrases. Refusing overflow can reduce completion rate. These limitations must remain visible in the evaluation, not be hidden by unsupported answers or an inflated state snapshot.

## Empirical and deferred details

N/C/K, lexical/metadata branches, deduplication, rule priority, recency tie-break, component caps, output reserve, truncation order among optional content and limited refetch follow [E1–E12 and calibration](../specs/08_V02_Conversational_Evaluation.md). They are UNSELECTED; this ADR freezes no numeric weights, prompt or candidate grid. Ranking/pack changes to existing documentary retrieval need a new reviewed profile, not an assembler workaround.

Durable selected contexts, state provenance or derived lookup metadata may require Alembic; concrete schema/index design is deferred. Rebuilding lookup/state creates new versions and must not replace inputs actually used by old Runs. No vector migration or Summary table/job is required for this slice. Test true model accounting, boundary payloads, old-relevant/new-noise, correction dependencies, scope changes and incomplete searches; proxy tokenizer fixtures cannot establish provider limits.

Reevaluate vector retrieval only after controlled evidence isolates A+B recall gaps and simpler metadata/lexical changes fail within accepted budgets. Reevaluate Summary only after measured necessary-history pressure survives better selection/deduplication and a controlled source-preserving compression proposal can justify its risk/cost. Both require new Feature/Evaluation review. Acceptance record: **none; Human ADR Review required**.
