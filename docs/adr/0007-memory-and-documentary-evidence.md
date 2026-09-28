# ADR 0007: Memory and documentary Evidence trust boundary

Status: **PROPOSED / awaiting ADR Human Review** · 2026-09-28

## Context and accepted constraints

[Accepted Architecture](../V02_CONVERSATIONAL_RAG_ARCHITECTURE.md), sections 5 and 9, and [Governance](../ENGINEERING_GOVERNANCE.md) distinguish intent memory from documentary truth. A valid quote or Citation is not proof of semantic support. This separate trust-boundary ADR is a prerequisite for the [first Feature slice](../specs/07_V02_First_Conversational_Slice.md); its wording awaits its own Human Review.

## Proposed decision

Type and separate user intent/constraints, interpreted state, historical assistant text and documentary Evidence throughout selection, serialization and validation. Memory may resolve references; no historical answer, user premise, inferred entity or future Summary can acquire Evidence authority. Documentary claims require currently authorized immutable source Evidence in the current Run's pack. Historical `[E1]` labels stay local to their old Run and cannot inject current labels or scope.

Query text and authorized KB/document/version scope are independent inputs. Capture explicit scope per Turn; check authorization at admission, source/result reads and acceptance. Scope changes revalidate state applicability without mutating old snapshots. Reading an old Run is not permission to retrieve its documents in a new scope; requested old versions cannot silently map to new ones. Untrusted memory/document instructions cannot change policy.

Keep 100% physical resolution of accepted Citation → expected Evidence → immutable source version/span/PDF, and 0 accepted critical evidence/semantic-boundary violations. No-citation output has no automatic semantic pass. Runtime guards block detectable drift/unsupported claims; human evaluation is still needed and no general automatic entailment guarantee is claimed. Later invalidation preserves the original failure and excludes invalid derived assumptions from future state rather than erasing the record.

## Alternatives and consequences

| Alternative | Reason not proposed |
| --- | --- |
| Trust old cited assistant answers as reusable facts | Old authorization, scope, versions and semantic mistakes could be inherited |
| Treat all serialized text as one evidence list | Memory labels could impersonate current Evidence or instructions |
| Authorize snapshots forever | Retained text can bypass current access restrictions |
| Treat valid Citation as semantic proof | Correct bytes/offsets may still support a different entity or claim |

The proposed boundary costs current evidence validation and explicit unavailable states. It favors inspectable narrow answers/clarification over confident unsupported continuity. It does not add full RBAC infrastructure or claim the existing single-workspace system already provides it.

## Empirical and deferred details

Interpretation confidence/activation, detection strategies and semantic quality margins are evaluated under the [Evaluation Spec](../specs/08_V02_Conversational_Evaluation.md); trust/authorization are not ablation variables. Prompt wording and exact type layout are deferred, while typed separation and source identity are mandatory.

No rewriting of existing Evidence offsets, canonical bytes, Citation IDs or ranking. New durable provenance/access associations require Alembic if schema changes. Normal retirement retains referenced dependencies. Missing/corrupt source bytes must not be rebound to similar documents; explicitly deny/mark unavailable and repair from matching backups. Genuine erasure requires a separate accepted retention/retraction policy: do not retain an assertion of valid available final while breaking its Citation. The Feature proposes no automatic first-slice TTL/deletion; approval of that product policy is still required.

Verification includes cross-conversation isolation, changed scope/version, failed drafts/old answers/hostile instructions as data, historical read versus current query access, lost source, authorization change versus commit, quote-valid but unsupported claim, and Citation→PDF identity. Synthetic cases prove only finite checks. Reevaluate Evidence reuse optimization only with proof of current authority/identity and a new reviewed contract; Memory non-Evidence remains invariant. Acceptance record: **none; Human ADR Review required**.
