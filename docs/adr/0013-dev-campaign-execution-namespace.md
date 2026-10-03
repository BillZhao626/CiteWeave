# ADR 0013 — Evaluation campaign execution namespace

Status: **ACCEPTED — Human campaign-isolation decision incorporated, 2026-10-02**. No migration0013. Accepted ADR0012 and shared product provenance semantics remain unchanged. The Owner withdraws cross-campaign byte equality only for campaign execution UUIDs and separately authorizes the [bounded dynamic-provenance contract](../V02_DYNAMIC_PROVENANCE_CONTRACT.md).

## Context

The existing DEV conversation key identifies dataset/view/arm/runtime/mode but omits independently authorized execution campaign. Fresh paid admission therefore resolves a historical FAILED target Run and correctly rejects retry. The Owner authorizes evaluation-only namespace repair, with immutable historical evidence and same-campaign recovery, conditional on byte-identical frozen provider requests and token measurements.

## Candidate decision

Add an optional campaign UUID only at the evaluation PgBackend/RealDevBackend seam and pass the paid policy campaign ID from the launcher. Combine the UUID with a digest of the existing semantic key, staying within the existing128-character key limit. Different campaigns isolate conversations and target Runs; the same campaign resolves the same stored prefix and execution. Existing unscoped callers retain their path; shared core behavior is unchanged.

The original provider-free candidate6f9ccac proved isolation/recovery and rejected its then-current byte-invariant paid admission. That negative evidence remains preserved. The subsequent Human decision explicitly accepts different execution UUIDs and permits a new, finite provenance envelope, without changing Gold, prompts, schemas or source semantics.

The new evaluation serializer restores frozen History/Working State enumeration by semantic prefix role. Core group members enumerate by random Acceptance UUID; namespace changes otherwise invert the same correction group's wire order. Selection, ranks, groups, Context and core guards are untouched. Actual new UUIDs stay on the wire; no old SourceRef is remapped. Semantic canonicalization replaces only explicitly listed UUID value paths and still compares arrays in order.

## Alternatives

- Campaign scope only the target Run key: smaller, but shares the historical FAILED conversation and mutable head/state across campaigns; fails the required conversation isolation.
- Rewrite serialized provenance UUIDs to old aliases: changes the frozen interpretation/generation contract and source resolution; not an authorized guard bypass.
- Copy old prefix IDs into a new conversation: existing PK/composite foreign-key ownership prevents this inside the same authority. Reassigning ownership in a separate database is not proof that immutable SourceRefs preserve their meaning. A runtime recreation alone does not establish eligibility.
- Reset/delete the failed target or redispatch UNKNOWN: explicitly prohibited and not considered a repair.

## Consequences and migration impact

No schema, DTO, shared core, Gold, prompt or ranking change. Historical STOPPED/UNKNOWN/FAILED rows remain immutable. Concrete wire hashes and pinned-tokenizer counts are retained per dispatch; certified UUID locality adds1464 input tokens across38 slots. New input6198361/output777079/total6975440; derived peak18.613354 CNY, fresh hard ceiling18.70 and separate historical exposure≤0.016110. Unknown immediately stops; known target failures may continue only under intact campaign accounting/deadlines. No retries, Judge, repair or refetch calls are added. Execution evidence and Human quality review are separate.
