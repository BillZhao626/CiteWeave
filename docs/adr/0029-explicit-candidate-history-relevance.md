# ADR 0029 — Explicit relevance resolution over bounded history candidates

Status: local implementation pending regression and the real two-turn product
gate; not released. No test result or provider success is certified by this ADR.

## Observed missing boundary

ADR 0008 separates bounded A+B candidate generation from final context selection
and requires relevance before recency. The existing experimental architecture is
design evidence for that separation; it does not establish that the production
provider path implements it.

The real accepted first turn remained a legitimate recent A candidate after the
compact read projection in ADR 0028 reduced its history payload from 206,083 to
1,371 bytes. Its Working State had no entries, and the default `HistoryQuery` had
no already-resolved signals or explicit source. The legacy selector consequently
returned `no_active_relevance`, leaving the interpretation model no historical
context from which to resolve a natural pronoun follow-up. Promoting recency to
relevance, injecting a source from the demo harness, or rewriting the old accepted
state would conceal this missing product boundary.

## Decision

Add an internal product-only path in `history_relevance.py`. The ordinary
provider-driven runtime reads history with `candidate_mode=True`; the legacy
selected-history path remains the default for existing callers and reviewed
interpretation drafts. Candidate mode preserves the existing SQL branches,
compact projection, connected provenance groups, scope filtering, deterministic
ordering and budget accounting. It retains eligible groups for inspection even
when their relevance is not yet resolved, and returns `selected=()`.

The existing conservative bounds remain N=2 recent turns, C=8 inspection groups
and K=2 resolved groups. The history payload remains limited to 131,072 bytes,
64 materialized rows, 8 read round trips, 8 members per connected group and 16
active projected state entries. Existing finite scan envelopes, deadlines,
statement timeouts and incomplete-search handling remain in force. The additional
model-visible candidate serialization is also checked against 131,072 bytes.
No string truncation, answer summary or parameter retuning is introduced.

`CandidateHistory` binds the query and history result to the exact interpretation
input. Before sending, it validates the current scope/head, history completeness,
candidate/group bounds, source identities, Conversation, complete relation targets
and active-state projection through the existing source guards. It also recomputes
canonical connected groups and correction/mandatory metadata from the bounded
visible source records, the legitimate query and active state, without another
history search. Split groups or forged supersession/mandatory metadata cannot be
accepted as caller assertions. Explicit and
mandatory query sources, and provenance sources required by projected Working
State, must be present in the supplied candidate set. A failed or incomplete read
cannot become a provider input.

The typed model-visible `CandidateInput` contains complete groups. Each group
has its Acceptance identity set, original source/Turn pairs, original user
questions, scope, structured intent signals, relations, and full/partial
supersession markers. Active Working State and its provenance are a separate
input. Historical answers, Citation, EvidencePack, PDF geometry, retrieval
rankings and old Trace are excluded. Internal candidate records continue to use
the compact `AcceptedHistory` projection; no durable Acceptance is modified.

### Explicit decision and application validation

`RelevanceDraft` extends the existing provider `FormatDraft` only with required
`relevant_sources`. An explicit empty collection means no historical source is
used. Omission is a schema error. The product prompt explains that these are
inspection candidates, recency is not relevance, sources establish intent only,
and genuinely competing referents must use the existing ambiguity/clarification
contract rather than an arbitrary choice.

The application accepts only exact Acceptance/Turn pairs in the candidate set
actually supplied to that call. Duplicates, forged pairs and sources omitted from
that input fail closed. Selecting a member retains its entire connected
provenance/correction group; the model cannot publish a partial group. Mandatory
state/source groups also remain available to the existing guards. This does not
grant permission to inherit facts from an unchosen source. More than K resolved
groups is a failure, not silent pruning.

Historical and state fact origins, including reference and ambiguity candidates,
must be listed in `relevant_sources`. Conversely, every declared relevant source
must justify an inherited origin or correction of an active state item; unused
source declarations are rejected. Active Working State is not treated as a second
history transcript, and selection does not reactivate superseded or out-of-scope
items. Required groups preserve existing constraints and correction provenance
without making every member semantically relevant.

Only the declared relevance field is removed before using the existing
`decode_format` converter. Current literal quotes/occurrences still determine
exact spans; historical facts still match supplied signals; state facts still
match active item value, ID and provenance. Existing `interpret` validation
remains authoritative for dependency, correction, topic-return, ambiguity and
rewrite rules. The original current request is preserved and inherited values
are appended by the existing deterministic converter. No old-domain schema,
experimental formatter, evaluation prompt or arbitrary JSON fallback is changed.

These checks establish admissible identity and intent provenance. They do not
independently prove that the model's natural-language relevance judgment is
correct. Controlled regressions and the real product gate must assess that
behavior, with single-case limits recorded separately.

### Current documentary authority and publication

After resolving history and validating the interpretation, the existing
`produce` workflow runs documentary retrieval for the current selected query.
It constructs and validates a current `EvidencePack` and supplies current
evidence to real generation. Historical intent remains a separate typed input;
the candidate decision never becomes documentary Evidence.

Citation/source validation and the Acceptance transaction retain their existing
checks, including durable provenance lookup, effective-result atomicity, state,
Conversation head, owner/fence and current evidence binding. UNKNOWN,
idempotency, retry/no-redispatch, cancellation and recovery semantics are
unchanged. The reviewed-draft runtime path continues to consume legacy selected
history and the supplied draft without invoking this relevance resolver.

### Accounting and local receipts

Candidate inspection and interpretation share the existing single interpretation
provider phase; this adds no separate relevance provider call. The normal grant,
request identity, token, monetary and deadline bounds continue to apply.

Opt-in `CW_INTERPRETATION_CONTEXT_RECEIPTS=1` writes an exclusive local
`.runtime/interpretation-context/<run-id>/receipt.json` after interpretation
validation. It records the actual candidate messages, candidate/history input
fingerprints, resolved history and its fingerprint, the parsed relevance decision,
and the exact raw interpretation response with its SHA-256. It supplies
traceability, not factual authority or a public artifact.
It does not include request headers or credential configuration. Defaults remain
off; existing files are not overwritten; receipt I/O failure logs the Run identity
without replacing the execution result. Existing opt-in interpretation failure
diagnostics remain local. Publication requires a separate explicit artifact
allowlist and credential review; raw local receipts are not automatically exported.

## Recall limitations and alternatives

A+B generation remains intact. The bounded recent branch gives the resolver
unresolved nearby candidates; PostgreSQL B still uses the legitimate query's
explicit references and task/entity/constraint/topic signals to find older
matching groups across accepted history. This change does not infer search
signals before candidate generation, perform arbitrary semantic search over all
older questions, add vector memory, or promise recall of an older source omitted
from the legitimate bounded candidate set. Older-relevant/newer-noise and topic
return regressions must state the query/state inputs that made the older source
available. C cutoff remains visible, and incomplete searches still fail closed.

Automatic selection of the latest turn is rejected because it equates recency
with relevance. Passing all inspected candidates into generation is rejected
because candidate availability is not a relevance decision. Full transcripts,
historical answers, bigger C/K/byte caps, harness-injected references and edited
accepted state are unnecessary and violate the demonstrated boundary. A second
model phase would add authorization and cost without being needed for this
combined interpretation contract. Experimental selectors/formatters and frozen
evaluation receipts remain available unchanged for comparison.

## Validation and change impact

Planned focused coverage includes natural pronouns, unrelated recent history,
older relevant history with newer noise, no relevant source, competing referents,
correction closure, topic return, scope narrowing, forged/omitted identities,
incomplete searches, Working State, payload limits, current Evidence authority,
and the existing UNKNOWN/Acceptance/retry/idempotency/no-redispatch protections.
Passing provider-free fixtures alone will not certify real model behavior. The
approved real follow-up must resolve the legitimate first-turn candidate, retrieve
new current evidence, generate, validate citations, accept, and return identical
accepted identities/result after refresh before the portfolio gate can pass.

This is a local internal runtime/adapter contract change with no public API,
database schema or migration. It does not alter the existing v0.2.0 tag/Release,
create a new release, or certify production capacity. Portfolio-facing copy should
explain the engineering problem of inheriting only useful history, while keeping
experiment labels and this ADR's bookkeeping in internal traceability records.
