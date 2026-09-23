# Post-Holdout offline answer-consistency fixtures

All ten cases are independently authored synthetic material. No historical,
evaluation, or Holdout questions/wording were reused. Provenance is recorded per
case. These are test fixtures, not additions to an evaluation dataset.

Each question has evidence, scoped proposition meanings, a consistent control,
and an incompatible answer. The partial-answer case also includes an over-refusal
control. Each answer section carries manually authored semantic annotations;
these are test metadata only, not a public response schema. Scope is part of the
proposition key; values retain normative strength and scoped uncertainty.

The deterministic tests compare those authored annotations with the evidence
expectations. They distinguish the intended invariant on this finite fixture set;
they do not parse arbitrary prose, validate model semantics, or demonstrate that
the prompt improves generated answers. Existing Citation checks intentionally
accept well-cited contradictory examples too: semantic publication enforcement
remains absent. Future visible regression must review actual generated text
against the question/evidence, not copy these annotations onto model output or
rely on the historical Judge alone.

The new prompt is explicitly selected for the existing structural query profile
with `CW_TELECOM_ANSWER_PROMPT=answer-telecom-consistency-v1`. The default remains
`answer-telecom-v1`. Set configuration before starting a process (Settings is
cached). Runtime receipts capture both the selected identity and its SHA256;
historical profile definitions and saved runtime configurations are not rewritten.
This selection produces a post-Holdout variant, not frozen T2.

No provider run is authorized here. A separately authorized bounded visible
comparison may use these synthetic cases and already-visible examples, retain all
failures, and assess consistency, completeness, over-refusal, Citation validity,
prompt limits and latency against the unchanged baseline. No Holdout rerun, D3,
release, or claim of semantic guarantees follows from offline tests.
