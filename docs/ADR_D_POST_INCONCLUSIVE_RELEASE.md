# Post-INCONCLUSIVE product release contract

Frozen 2026-09-21, AFTER historical `STAGE_D1_INCONCLUSIVE`, on evaluated
commit `314b9617af9d9883794cb92761c622f2aed5e797` / tree
`3ea9a68b5473911f828de40672d5aed1441eb6b2`. This is a prospective protocol,
not a reinterpretation, correction or promotion of D1. Historical artifacts
and missing/failed results remain immutable.

## Governing product objective

CiteWeave finishes an external-facing product portfolio evolving General
Assistant V2 and supporting the resume. Priorities are polished React +
TypeScript, Answer → Citation → Evidence → PDF highlight, Documents/Structure,
Runs/Retrieval/Evidence Trace, traceable FastAPI/Qdrant/PostgreSQL/Redis/Celery,
and asynchronous jobs with durable state/recovery. Experiments validate these
claims; they do not create headline metrics. See STAGE_E_CLAIM_CONTRACT.md.

## Prospective release gates

- Engineering: full-visible completion >= 95%, with failures in the denominator.
  This is an internal production-oriented alpha target, not an industry RAG
  standard. Final accepted Evidence Citations must be 100% physically resolvable.
  A systemic blocker prevents promotion even if numerical thresholds pass.
- Regression is the primary quality-protection set: target minus B1 paired
  correctness AND completeness point estimates must each be >= -0.03. Report
  95% CIs as uncertainty; their lower bounds are not mandatory gates for this
  small set. No new critical factual failure. Improvement is desirable, optional.
- Development supports design decisions. Positive retrieval, evidence coverage
  or answer quality is desirable; neither every metric improving nor statistical
  significance is required. It is not the final generalization claim.
- Safety is an event-level gate, never hidden in averages: no new critical
  factual error, fabricated secret or unsupported forced answer; all unanswerable
  cases semantically refused. Explicitly report wrong refusals on answerable cases.
- Apply the same Regression, Safety, completion and Citation gates to T1/T2.
  If only one qualifies, freeze it. If both qualify, prefer T2 only if Parent
  behavior is not worse on Safety/wrong refusals and no semantic reason favors T1.
  Coverage benefit alone cannot override answer quality. If neither qualifies,
  freeze no target. Missing judgments remain N/A, not fabricated successes;
  disclose paired sample sizes and exclusions separately from full completion.
- Holdout stays sealed until one candidate is frozen. Its eventual role is
  confirmation: no material regression, stable/positive unseen point estimate,
  no new critical failure. A target-baseline correctness or completeness point
  difference below -0.03 is material regression; non-negative is preferred.
  Small-sample significance is not required. Do not tune after seeing Holdout
  and represent that same evidence as confirmatory.

## Citation namespace decision and migration

Only ASCII `[E<positive integer>]` is an Evidence Citation: token regex
`\[E[1-9][0-9]*\]`. E is uppercase, decimal digits are ASCII, with no leading
zeros, signs or whitespace. Labels are matched by identity, never renumbered.
Every literal `[E` starts the reserved namespace and must form a complete valid
token: `[Efoo]`, `[E-1]`, `[E0]`, `[E01]`, `[E１]`, `[E1 ]`, and unclosed `[E1`
are malformed. This rule also applies inside code/Markdown text.

Other bracket text, including `[RFC7252]`, `[HTTP]`, `[MQTT-3.1.2-18]`,
`[ ":" port ]` and `[fake]`, is ordinary text, not evidence. No case allowlist.
At least one available valid citation is required for non-refusal answers;
syntactically valid unavailable labels such as `[E999]` reject the answer.
The existing exact-refusal (after outer whitespace stripping) exception remains.

Preserve EvidenceSpan identity, authorized source/version, exact quotes/offsets,
provisional/final publication, and durable CitationRow semantics. The frontend
only links valid tokens backed by final citations; it does not validate/publish
drafts. The old `[fake]` rejection test explicitly migrates to ordinary-text
acceptance, with unavailable and malformed reserved-label negatives replacing it.

Alternatives rejected: continuing to treat every bracket as evidence, adding
observed-case allowlists, or silently ignoring malformed/unknown E references.
This changes product acceptance semantics; it is not a historical measurement
fix. No schema/data migration, prompt change, retrieval change or UI redesign.

## Scope and stop

Commit this protocol before code hardening. This task authorizes deterministic
offline tests and optional saved-output compatibility replay only: zero provider
calls, no retrieval rerun, no Holdout contents, no D2/D3, no quality matrix,
no Resume/Portfolio edits. Replay does not alter historical completion/quality.
Stop at `STAGE_D_CITATION_HARDENING_READY` after validation.
The next authorized step is a full B1/T1/T2 visible quality rerun using the
existing frozen EvidencePacks, in a subsequent execution task with new run
identities; do not splice successful replays into D1 or start that step here.
