# ADR0014: Explicit interpretation wire origins and deterministic formatting

Status: implemented under bounded Human P0 authorization2026-10-02; DEV output review pending.

Baseline receipts show omitted origins, incorrect character offsets and rewrite formatting incompatible with the existing exact completion contract. Formatting is separate from semantic validity.

Use a separate tagged-origin wire DTO in evaluation. Current facts use exact value+occurrence; history/State copy exact identities. Deterministically convert into existing InterpretationDraft and serialize its existing exact completion-only rewrite from explicit inherited facts. Keep shared DTOs, core validators and Acceptance unchanged; record prompt/schema/adapter as the intervention.

Alternatives: instructions alone retain unreliable numeric offsets and implicit origin exclusivity; fuzzy repair/dropping fields guesses intent; validator relaxation permits unsupported facts. Topic/ambiguity/retrieval changes are outside this P0 authority.

No migration, durable DTO or API change. Existing JSON retains raw output, wire/semantic/provenance evidence and known accounting before parsing. No retry/Judge/provider repair/refetch. Historical receipts remain immutable; production v1 default stays unchanged. One finite full24 rerun is granted independently; later independent/Human review owns semantic quality.
