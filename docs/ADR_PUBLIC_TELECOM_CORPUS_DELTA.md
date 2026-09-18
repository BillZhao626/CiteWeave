# Approved public telecom corpus revision

Decision: 2026-09-18, explicitly approved release-corpus design. The public name remains **CiteWeave independent public telecom corpus**. Manifest revision `2026-09-18-approved-delta-1` records actual acquired hashes. The prior frozen design and failed acquisition evidence are retained privately and are not overwritten.

| Previous source | Approved source | Reason and structural coverage impact |
|---|---|---|
| RFC 8200 | [RFC 9673](https://www.rfc-editor.org/info/rfc9673/) | Official reproducible IPv6 standards-track PDF, updates RFC 8200; focuses coverage on nested Hop-by-Hop processing procedures rather than the complete IPv6 specification. |
| RFC 8446 | [RFC 9846](https://www.rfc-editor.org/info/rfc9846/) | TLS 1.3 specification explicitly obsoleting RFC 8446; preserves extensive nested clauses, cross-page sections, appendices and conditional normative requirements. |
| RFC 8323 | [RFC 9175](https://www.rfc-editor.org/info/rfc9175/) | Official CoAP standards-track PDF updating RFC 7252; shifts coverage from transports to Echo, Request-Tag and Token processing with nested numbered structure. |

RFC 9293, RFC 9000, RFC 9110 and MQTT 5.0 OASIS Standard retain their previously verified bytes and hashes. The corpus exercises source-bound structural parsing; it does not reproduce a historical corpus or assert topic equivalence between replaced specifications.

Provenance: `corpus/public_telecom_manifest.json` records official info/PDF URLs, edition/date/category, actual retrieval time, byte length, pages, SHA-256, signature, first-page identity/hash and copyright-notice location. `scripts/fetch_public_telecom.py` verifies fixed editions and never silently replaces mismatching local bytes. Downloaded PDFs and acquisition reports stay under `.runtime/private/public-telecom`.

Original fixtures and available verified sources may drive implementation independently of corpus completeness. Final structural acceptance still requires every release source's provenance and real structure/tokenizer/index evidence. Download success alone is not implementation acceptance.

Redistribution policy is unchanged: no complete PDFs, extracted full text, vectors or bulk chunks in the repository. No locally rendered replacement is labeled an official PDF. This decision changes corpus membership only, not evidence identity or the parser's geometry contract.
