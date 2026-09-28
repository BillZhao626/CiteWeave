# ADR 0009: conversation profile and Trace version semantics

Status: **ACCEPTED — Human ADR Review incorporated** · 2026-09-28

## Context and accepted constraints

[Accepted Architecture](../V02_CONVERSATIONAL_RAG_ARCHITECTURE.md), sections 10–11, preserves historical Run interpretation and separates conversation policy from documentary retrieval. [Current readers](../../src/citeweave/query_evidence.py) already distinguish `legacy-v1` and `structural-trace-v1`. Controlled first-slice experiments need reproducible inputs rather than labels referring to mutable defaults.

## Accepted decision

Introduce a distinct versioned conversation profile resolved and captured at admission, alongside unchanged retrieval/index profile identities. Capture interpretation/history/state/context strategies, prompt content hash plus resolvable version, provider/model identity, tokenizer/accounting revision, all stage/output/resource budgets and experimental variant identity. No current default silently changes an already admitted Run.

Freeze both interpretation input and actual generation input: original/rewritten/used query, incoming head/state snapshot, considered and selected source groups, spans/order/content hashes with retrievable content, exclusion/truncation/overflow, scope/version bindings and EvidencePack. Record output state separately. Trace retains decision outcomes and provenance, not hidden chain-of-thought.

Trace also records Conversation/Turn/Run/retry, ownership/fence and final outcome categories, stage timing, call attempts/usage/estimated cost/unknowns and validation results. Bounded candidate details plus aggregate counts avoid copying the entire transcript just for diagnostics. Authorization/retention cover source text in Trace; public logs/CI get safe identities/counts/categories, never raw private history, credentials or provider errors.

Three operations remain distinct: historical view reads committed outcomes; input reconstruction uses exact historical snapshots and serializer/profile versions; reexecution creates a new Run/comparison with current authorization. Missing inputs or unavailable model revisions mean not reconstructable/not repeatable, not permission to synthesize old inputs. Reexecution does not promise identical model output.

## Alternatives and consequences

| Alternative | Reason not proposed |
| --- | --- |
| One mutable global profile/prompt | Cannot attribute differences or reconstruct old decisions |
| Merge conversation policy into retrieval profile | Blurs an interpretation change with altered evidence ranking/version |
| Hash only, without retained/resolvable content | Identifies missing bytes but cannot reconstruct model input |
| Save all provider requests/errors in generic logs | Unbounded privacy/secret exposure without a proper access contract |
| Recompute old state/history with latest selector | Changes the meaning of historical Runs |

This adds versioned storage/reader obligations and more identity fields in diagnostics, while keeping the normal conversation UI concise. Empirical results remain tied to precise arms even when a later strategy wins.

## Empirical and deferred details

Actual profile/schema names, DTOs, serialization and frontend Trace components are implementation choices after review. Strategy values and measurement limits follow the [Evaluation Spec](../specs/08_V02_Conversational_Evaluation.md); identity/reconstruction guarantees are not tunable. Exact input receipt format must be validated against full framing/token measurement before experiments.

If durable schema expands, use Alembic and explicit conversation reader revisions; keep v0.1 readers and optional new Run association. Do not backfill fabricated conversation state or reinterpret legacy evidence fields. Backup/restore must include retained prompt/template/input artifacts and PG/blobs together; format changes need a reader compatibility test. Test old reader display, hash/content mismatch, input-versus-output state, budget/profile capture, same input reconstruction, current authorization on reexecution and unavailable-source diagnostics.

Reevaluate representation only if measured combinations or storage cost become unmaintainable, using a new version/migration while keeping historical readers. This fourth ADR remains separate because it spans all strategies, evaluation and v0.1 compatibility rather than only commit transactions. Acceptance record: **APPROVED**, 2026-09-28, by the maintainer through the explicitly authorized Human ADR Review instruction, for the exact ADR text at **`aa5755cbf70e552827f03211d2770a4dcff3626f`**; public record: [PR #3](https://github.com/BillZhao626/CiteWeave/pull/3). This records acceptance without expanding scope or authorizing implementation/experiments; empirical choices remain UNSELECTED pending Evaluation freezes.
