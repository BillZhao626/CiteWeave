# ADR 0032 — Read-only context observations

Status: local product improvement; no release or schema migration.

The public durable Trace records the chosen query, interpretation identity,
used historical source identities and state item IDs. It does not persist the
complete preselection candidate set or model reference bindings. Inferring those
from recency would make an inspector misleading.

Add an authenticated read-only context endpoint and a reusable Context Inspector.
The durable Run and immutable source versions are authorized first. Optional
existing opt-in interpretation receipts provide candidate and reference detail
only after hash checks against the durable completed provider phase's exact
request/response hashes, exact current-request/scope/head binding, comparison of
each source with its immutable authorized Acceptance/Admission, and replay of the
pure local interpreter to match the published interpretation fingerprint, query,
used historical identities and used state items. No provider is called during
inspection. Missing, oversized or inconsistent receipts produce explicit
NOT_RECORDED/UNVERIFIABLE states; they never produce inferred empty collections.

The response is an allowlist: historical original requests and identities,
actual A-branch recent membership, explicit relevant_sources membership,
projected input state, reference mention offsets/values, and interpretation
identity. It excludes provider bodies/prompts, historical answers, documentary
Evidence, secrets and invented numeric relevance weights. Current Evidence and
Citation identities are displayed separately from the durable current Run Trace.
Local receipts remain optional observations; PostgreSQL Acceptance remains the
business authority. Structural identity checks do not prove semantic relevance.

Alternatives: timestamp-based reconstruction cannot prove historical selection;
serving raw receipts exposes unnecessary provider input/output; changing durable
Acceptance or adding a schema solely for capture would expand this task. The
optional projection provides reusable inspection while retaining explicit
availability limits. Receipt collection remains opt-in and existing receipts
are never overwritten. Existing publication, history, scope, retrieval, fencing,
retry and Acceptance semantics are unchanged. No migration is required.

Validation covers recent versus relevant roles, input state empty/nonempty,
reference binding, current Evidence separation, unavailable observations,
receipt/source mismatches, authenticated fixed-scope reads and no dispatch.
Synthetic fixtures prove engineering boundaries, not model-quality performance.
