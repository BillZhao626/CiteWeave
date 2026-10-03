# ADR0015: Unique bookkeeping and explicit semantic decisions

Status: implemented under Human Runtime Stabilization authorization 2026-10-02; real DEV semantic review pending.

The preserved P0 rerun has malformed JSON, an incompatible task identity and an occurrence index on a unique literal. Only the last failure is mechanically recoverable from that exact output. Malformed JSON remains rejected; task selection remains a semantic model decision.

Evaluation wire v3 derives offsets and source/State IDs only for one exact available kind/value origin. Supplied IDs constrain lookup. Repeated quotes and ambiguous origins require explicit selection. Duplicate keys, malformed JSON, fuzzy matches and missing origins fail closed. No case identities or expected answers enter the rules.

Expose current head signals and whether active items originated at that head. General instructions distinguish continuing that activity from returning to earlier intent, stable task labels from action phrases, alternatives from explicit selection, and active corrections from superseded state. A declared continue incompatible with a task/topic and earlier inherited intent is rejected, never changed to return. An explicitly chosen supported active entity with literal current-turn proof and a unique pending ambiguity key maps to the existing StateCorrection. The core reducer and validators retain authority; remaining ambiguity is not removed automatically. State-only intent does not reconstruct raw history or substitute for atomic correction provenance.

Alternatives: prompt-only offsets/UUIDs retain bookkeeping failures; bracket guessing or dropping invalid claims obscures unsupported outputs; heuristic prose classification or code-selected candidates substitutes for semantic intent; broad Acceptance changes exceed authority. This contract cannot guarantee model compliance or semantic quality.

Migration impact: none. Shared DTOs/Acceptance, schema0012, retrieval/ranking, EvidencePack, generation policy and A/AB0 history definitions stay frozen. V2 remains for historical replay; the authorized launcher pins v3 prompt/schema/module. Known observation/accounting precedes normalization. No provider repair, retry or redispatch.

Omitted IDs can expand in normalization, invalidating the old response-byte multiplier by itself. Explicitly cap compact unique normalized facts, including reference/ambiguity candidates, at the frozen generation insertion envelope399616 UTF8 bytes before generation. Core facts are a subset of this deduplicated set. Existing query/pack/history byte envelopes and ByteLevel proof apply; each actual request is measured before dispatch. Oversized normalized facts cause known failure rather than extra allowance. Re-freeze fifteen interpretation requests under the approved UUID-path allowlist; decision_context adds no UUIDs. Eight independent generation wires remain identical and incomplete correction has no dispatch slot.

Both provider-free gates precede one fresh full24 campaign: calls38/input6207864/output777079/total6984943, derived peak18.632360 CNY, fresh hard18.70. Historical known estimates and UNKNOWN exposure remain separate. No automatic Human labels, Judge, winner or final Compare.
