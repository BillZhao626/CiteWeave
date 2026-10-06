# ADR 0027 — Explicit origins at the production interpretation boundary

Status: locally implemented for the authorized E2.4 compatibility fix; not released.

## Observed problem

A new diagnostic production request reproduced a validation failure. The provider
returned valid bare JSON but placed scope IDs into `document`/`version` facts with
neither a current span nor a historical source. `IntentFact.origin` rejected both
with `exactly_one_intent_origin_required`. Other proposed facts paraphrased the
question despite carrying numeric offsets. The old failed Run has no retained raw
output, so its particular invalid fields remain unknown.

The old JSON schema did not express the model validator's exclusive-origin rule.
It also asked the model to count Unicode offsets and serialize an exact rewrite,
although these are deterministic representation operations.

## Decision

Production requests now advertise the existing `FormatDraft` tagged-origin schema
and a dedicated product prompt. The existing `decode_format` converter finds exact
quoted occurrences and constructs the existing completion-only rewrite from the
unchanged question and explicitly inherited values. It does not infer provenance,
choose referents, paraphrase values or grant access. The existing `interpret`
validator, current history selection and Acceptance boundary remain authoritative.

Do not call `format_messages`: it adds an evaluation-only State-origin policy.
The product path retains the stricter selected-history-source requirement. The
old `interpretation_messages` function/prompt remain unchanged for existing users
of that legacy contract. No fallback accepts an originless legacy result.

With `CW_INTERPRETATION_DIAGNOSTICS=1`, failed parsing/conversion writes exact raw
UTF-8 output and structured validation errors to the fixed ignored directory
`.runtime/interpretation-diagnostics/<run-id>/`. Files are exclusive-create,
contain no request headers or configuration, and are never product state. The
switch defaults off. Diagnostic I/O errors cannot replace the original failure.
Operators must retain these potentially sensitive model outputs locally and
never export them automatically; public evidence uses hashes and error locations.

## Alternatives and limits

- JSON mode or code-fence stripping cannot fix the observed valid-JSON provenance
  errors. Transport/accounting configuration therefore stays unchanged.
- Making provenance optional or guessing it would weaken the domain contract and
  is rejected. Missing required fields and unknown wrappers remain errors.
- No demo-specific interpretation, reviewed draft, prompt search, model change or
  change to UNKNOWN/retry/Acceptance/fence/cancellation/recovery is introduced.
- There is no database migration or public API change. The provider wire schema
  and prompt identity change and are recorded in each new request hash.

## Validation

Focused tests reproduce the observed shape with synthetic identifiers, preserve
required fields, reject paraphrases, malformed JSON and unsupported wrappers,
verify exact-span conversion and optional collection defaults, and check local
diagnostic isolation. Production-adapter/PostgreSQL tests cover both accepted
interpretation→generation and UNKNOWN without redispatch. Existing reliability
and regression suites remain in place. Real-model acceptance is recorded separately
from mocked-transport tests in the local E2.4 evidence package.
