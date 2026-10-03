# P0 interpretation format repair and one full DEV rerun

Human authorization2026-10-02 freezes Adjudication v1 for baseline campaign `f9863f8c-416f-4b23-86fa-045cd6c67f29`:10 COMPLETED/14 FAILED,23 known calls, estimate0.10563280 CNY. Older STOPPED/UNKNOWN≤0.016110 CNY remains separate. Historical receipts and Human labels are immutable.

## Intervention

Only the evaluation launcher opts into `interpretation-format-v2`. Original interpretation prompt, production default messages, shared Draft/IntentFact DTOs, semantic validators, history/State, query/retrieval/ranking, generation/citation policies and schema0012 are unchanged. The additive format prompt, wire schema and adapter identities are frozen/rechecked before POST. [ADR0014](adr/0014-interpretation-wire-format.md).

Facts explicitly choose current/history/state origin. An exact current value plus zero-based occurrence becomes a Unicode codepoint span; overlapping occurrences count. No fuzzy match, offset guessing, dropped claim or inferred origin. History still requires supplied structured signals. State carries exact item ID/value/introduced_by pair; adapter checks value/source equality, and core retains kind/active/superseded/source/correction guards.

Wire omits rewrite/scope/retained. Code serializes the existing exact completion rule: original question + newline + distinct explicitly inherited values, with original scope/required terms. Dependency, topic, candidates, ambiguity, put and corrections still come from model and core. Code never changes none to required or clears pending ambiguity. Known completion precedes parsing; invalid local output becomes FAILED with raw output/usage preserved. UNKNOWN stops without replay.

## Engineering audit

This assessment does not relabel Human Adjudication. Raw claims, actual Context/State/SourceRefs, failed boundary and offline re-expression live in `.runtime/evaluation/p0-rerun/p0-audit.json`. Re-expression is diagnostic only; runtime never repairs old output heuristically.

| Original P0 | Baseline error | Boundary / remaining claim | Assessment |
| --- | --- | --- | --- |
| D1.V1/A | interpretation_current_provenance_invalid | Wrong spans and rewrite format; exact current values/State pass unchanged core in actual Context | FIXED |
| D1.V1/AB0 | dev_interpretation_invalid_json_or_schema | Missing origins; abstract cooling duration lacks literal/signal origin | RECLASSIFIED_NOT_ENGINEERING |
| D3.V1/AB0 | dev_interpretation_invalid_json_or_schema | Missing literal topic origin and inherited completion | FIXED |
| D4.V2/AB0 | interpretation_incomplete_provenance | valve test is prose, not constraint signal; ambiguity policy remains | RECLASSIFIED_NOT_ENGINEERING |
| D5.V1/A | dev_interpretation_invalid_json_or_schema | Literal before24 hours lacks origin; completion/retention formatting | FIXED |
| D5.V1/AB0 | interpretation_current_provenance_invalid | Exact quotes expose relay check task conflict with D5-task | RECLASSIFIED_NOT_ENGINEERING |
| D5.V2/A | dev_interpretation_invalid_json_or_schema | none conflicts with inherited Quill m4; cannot guess required | RECLASSIFIED_NOT_ENGINEERING |
| D5.V2/AB0 | interpretation_current_provenance_invalid | Exact quotes expose task conflict | RECLASSIFIED_NOT_ENGINEERING |

Tests reproduce all eight old failures before demonstrating format conversion and invalid neighbors. Foreign source, wrong State value, missing/mixed origin, nonexistent quote, inherited independent query and task conflict still fail. Unicode/repeated/overlapping quote tests establish codepoint conversion. Synthetic PG transport proves known observation is durable before v2 schema rejection and no replay occurs. Actual passes/failures/skips are in receipts; private baseline/tokenizer-dependent public tests may skip when artifacts are absent.

Nine Human-PASS locks: D2.V1/V2 both arms, D3.V2/A, D6.V1/V2 both arms. D2/D6 retain exact generation requests/slots/independent reviewed drafts; provider-free replay preserves USE_ORIGINAL and baseline D6 evidence/refusal. D3.V2/A remains incomplete_group/no slot/zero calls. Seven P1 cases are marked not optimized; no decision policy is altered.

## Envelope and delivery

Same38 conditional slots and reserves I1561/G32768. New I requests use production serialization, pinned tokenizer and certified UUID island envelope; provenance allowlist is unchanged. Each concrete request is independently measured before PREPARED/DISPATCHED/POST. Input6202651/output777079/total6979730, derived peak18.621934 CNY, fresh hard18.70. Format increment4290 input versus namespace contract. Historical UNKNOWN≤0.016110 and baseline known estimate0.10563280 are retained separately; unused authority cannot fund other experiments.

Generation's unchanged symbolic fact bound remains sound: normalized current facts add bounded-question spans and nullable defaults; minimum wire fact bytes exceed added punctuation/default fields, so normalized bytes≤2×wire fact bytes. History/State already carry full source pairs, and State carries its item UUID; conversion removes origin wrappers and adds only bounded nullable fields. Values remain literal fixed ASCII corpus/question values. Reference-derived facts are deduplicated by existing core. Complete response retains pinned per-output-token decoded-byte bound. Tests exercise all three origin expansions; actual G body still must fit its frozen cap.

Exact clean candidate, schema/Gold, two prior campaign snapshots, seven bindings, fresh authorization/expiry/deadline and full24 results live in `.runtime/evaluation/p0-rerun/`. Human review shows baseline/new side by side, original P0 highlights, PASS mechanical regression flags, P1 not optimized and accounting. Complete requires all24 known terminal cases and no UNKNOWN. No automatic Judge, winner, tuning, promotion/release or #5d.
