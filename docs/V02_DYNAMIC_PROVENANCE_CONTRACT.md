# DEV dynamic execution provenance contract

Human authorization: **2026-10-02**, accepting campaign isolation in candidate6f9ccac and withdrawing the obsolete cross-campaign UUID byte invariant. Dataset/Gold, accepted0012, prompts, retrieval/ranking, source/citation semantics, output reserves and no-retry/UNKNOWN rules remain frozen. This is one bounded DEV execution authority, not production deployment, #5d, tuning or a winner decision.

Current execution status, exact clean candidate, positive authorization and eventual Human output packet are in ignored `.runtime/evaluation/dynamic-provenance/`. Historical admission/UNKNOWN receipts remain at their original paths. No real output is claimed by contract or test acceptance alone.

## Semantic and wire identities

The evaluation-only `dev_provenance` module operates on the production serializer's JSON structure. Its explicit value-path allowlist covers:

- `history[*].source.{acceptance_id,turn_id}`;
- `history[*].relations[*].target.{acceptance_id,turn_id}` and `state_item_ids[*]`;
- `working_state[*].item.id` / `item.replaces[*]`;
- `working_state[*].{introduced_by,changed_by}.{acceptance_id,turn_id}`;
- generation `interpretation.facts[*].source.{acceptance_id,turn_id}` and `state_item_id`.

Every variable value must be a canonical36-character lowercase UUID. Typed alpha labels preserve equality, distinctness and reference relationships. Scope/KB/document/version/citation IDs, schema definitions, questions, factual text, signals, relation kinds, array order and every other field remain literal. Non-allowlisted drift and broken alias graphs fail closed. Canonical labels are offline evidence only and never enter a provider request.

Source roles come from the fresh campaign's durable prefix Acceptances and exact Turn pairs. The evaluation wire adapter restores the historical serialized History/Working State order by these frozen roles. This fixes random UUID enumeration of the same group (observed at D3.V2/AB0) without modifying selection, ranking, groups, Context or core validators. It never deletes a member or rewrites an ID. Canonical checking still rejects array reordering after this adapter.

Interpretation requests and the eight exact no-I generation requests compare completely after approved UUID canonicalization. Future generation requests depend on actual validated model interpretation: their frozen question/prompt/context shell must match, selected history/state must be ordered subsets of that shell, and facts' provenance must belong to it. Existing interpretation/EvidencePack/citation validators retain authority. Actual facts/query/pack remain in the full canonical wire digest; they are not erased or equated to a fake reference answer. Different real model decisions are outputs for review.

Before each POST, existing EvalCase JSON durably records exact wire SHA256, pinned input count, output reserve, campaign/phase IDs, semantic request/contract digests, actual UUID path bindings, Conversation/Run/Turn context and provider/model/tokenizer/rate identities. PREPARED and DISPATCHED independently reserialize/recount the full request. New-contract phases reserve the frozen per-slot input/output upper caps; concrete pinned measurement remains a separate exact wire field. Provider usage is checked against the immutable reservation, with five campaign sums still enforced. This changes no shared Observation semantics or output allowance. The dispatch guard requires the matching durable wire evidence. Known transport output and these records survive FAILED settlement; UNKNOWN retains request evidence and full reservation.

## Certified input bounds

Pinned official V4.1 ByteLevel tokenizer SHA256 remains `81f64d1248a68ce3663e07ab3ee48b851e5df0e32d27cb98e4c9a268151e8d99`. No new measurements are inferred from1815/1824/1818/1826 samples.

For each frozen concrete request, locate only allowlisted UUID value spans in the exact compact production JSON. Each replacement remains36 ASCII bytes. Extend its left boundary across contiguous ASCII punctuation and merge overlapping islands. The pinned numeric-isolation/letter/punctuation pretokenizer has cuts at both outer alphanumeric→punctuation boundaries for every hex/hyphen UUID. The implementation verifies those cuts in the original specimen; unsupported shapes fail closed. Numeric splits and punctuation-prefixed letter matches stay inside islands. Pieces outside the islands cannot change; BPE does not merge between pieces. With the certified byte vocabulary, an island needs at most one token per UTF8 byte.

Thus each new concrete-slot cap is its exact original input count minus exact original island-token counts plus the fixed island byte lengths. Only the affected islands pay extra, rather than adding padding to all request text. Adversarial all-digit/all-letter/alternating UUID tests exercise tokenizer branches; they supplement the shape proof and do not define its maximum.

For future generation, the accepted conservative whole-UTF8 symbolic method is unchanged: fixed shell bytes + bounded interpretation insertion + escaped query + current EvidencePack + five framing tokens. UUID lengths and occurrence counts are unchanged, and this byte envelope already permits their worst BPE segmentation. Provenance overhead there is therefore zero; output reserves remain interpretation1561/generation32768.

| Dimension | Re-frozen campaign limit |
| --- | ---: |
| Physical calls | 38 |
| Input tokens | 6,198,361 |
| Output tokens | 777,079 |
| Total tokens | 6,975,440 |
| Certified input increment | 1,464 |
| Derived worst-case CNY | 18.613354 |
| Fresh hard CNY ceiling | 18.70 |
| Historical unresolved exposure | ≤0.016110 |
| Cumulative hard exposure ceiling | 18.716110 |

Fifteen interpretation +23 generation slots remain the same population, with the original conditional guards/skips. Unused allowance cannot fund another phase/target/campaign. Judge/retry/repair/refetch0, repeat1. Endpoint/model/rate/temperature-thinking behavior are unchanged; account applicability/funds are Human attestations, not account-API measurements.

## Known failure and Human review

An invalid local schema/output/citation after durably COMPLETED transport may close its target FAILED, retain raw output/usage/wire receipts and proceed only if campaign integrity and deadlines remain valid. Safety/drift/accounting failures do not use that continuation. All24 COMPLETED/FAILED targets with known phases can close execution and prohibit further spending. UNKNOWN always stops and is never interpreted as zero spend or automatically redispatched. Shared DTO/migration0012 are unchanged.

Focused tests and pre-paid receipts report actual passes/failures. Earlier synthetic test failure caused by deliberately attempting redispatch before continuation was corrected by moving that fencing probe after completion; it was not a production retry. A provider-free wire-order admission failure was investigated and repaired without changing ranking. Original failed artifacts are retained. Real semantic quality, billing and arm superiority are not established by provider-free checks. Human receives final outputs/known failures, interpretation/History/State/B attribution, physical citation checks and complete accounting, and makes the quality decision next.
