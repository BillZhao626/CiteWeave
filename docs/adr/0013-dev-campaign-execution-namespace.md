# ADR 0013 — Evaluation campaign execution namespace

Status: **PROVIDER-FREE CANDIDATE; NOT PAID-ELIGIBLE**. No migration0013. No amendment to accepted ADR0012, product provenance semantics or the frozen DEV request contract.

## Context

The existing DEV conversation key identifies dataset/view/arm/runtime/mode but omits independently authorized execution campaign. Fresh paid admission therefore resolves a historical FAILED target Run and correctly rejects retry. The Owner authorizes evaluation-only namespace repair, with immutable historical evidence and same-campaign recovery, conditional on byte-identical frozen provider requests and token measurements.

## Candidate decision

Add an optional campaign UUID only at the evaluation PgBackend/RealDevBackend seam and pass the paid policy campaign ID from the launcher. Combine the UUID with a digest of the existing semantic key, staying within the existing128-character key limit. Different campaigns isolate conversations and target Runs; the same campaign resolves the same stored prefix and execution. Existing unscoped callers retain their path; shared core behavior is unchanged.

Provider-free isolated PG tests prove isolation and recovery across24 cases. They also disprove conditional paid eligibility: new prefix provenance UUIDs enter existing production interpretation serialization. Request hashes and official tokenizer counts differ from the frozen contract. The candidate repairs the collision but cannot be used for the currently authorized paid campaign.

## Alternatives

- Campaign scope only the target Run key: smaller, but shares the historical FAILED conversation and mutable head/state across campaigns; fails the required conversation isolation.
- Rewrite serialized provenance UUIDs to old aliases: changes the frozen interpretation/generation contract and source resolution; not an authorized guard bypass.
- Copy old prefix IDs into a new conversation: existing PK/composite foreign-key ownership prevents this inside the same authority. Reassigning ownership in a separate database is not proof that immutable SourceRefs preserve their meaning. A runtime recreation alone does not establish eligibility.
- Reset/delete the failed target or redispatch UNKNOWN: explicitly prohibited and not considered a repair.

## Consequences and migration impact

No schema, DTO, shared core, Gold, prompt or ranking change. No historical row mutation. New namespace requires new prefix provenance and therefore a separately reviewed solution for wire identity before paid use. Retain the provider-free candidate and negative admission evidence; do not grant money or generate outputs under a substituted contract.
