# Final release-source suitability decision

The approved final corpus revision `2026-09-18-approved-final-2` replaces RFC 9000 with [RFC 9114 — HTTP/3](https://www.rfc-editor.org/info/rfc9114/). The public name remains **CiteWeave independent public telecom corpus**. The preceding manifest is preserved under `corpus/revisions/2026-09-18-approved-delta-1.json`; previous private design and blocker evidence remain historical records.

RFC 9000's acquired official PDF contains twelve unverifiable Unicode mappings in author-role metadata under the strict glyph contract. This is a source-quality and release-suitability issue, not a claim that RFC 9000's technical content is incorrect. The identical full-document probe finds zero missing/FFFD mappings in the approved RFC 9114 PDF. Alternatives RFC 9002 and RFC 9001 reproduce the metadata mapping problem.

RFC 9114 contributes four-level protocol hierarchy, including 7 → 7.2 → 7.2.4 → 7.2.4.1, and HTTP/3 framing and QUIC-stream coverage. Its HTTP semantics overlap with RFC 9110 is accepted because faithful source mapping and real hierarchy have higher priority than minimum topical redundancy. It is not a topic-equivalent replacement for the full QUIC transport specification.

The exact official PDF is `https://www.rfc-editor.org/rfc/rfc9114.pdf`, SHA-256 `ecc538dc3d8e9cb3f8d73c3c10189f91bdc7b81f80c570ce658760e5d6f5db84`, 57 pages. The manifest records acquisition time, byte length, first-page identity/hash, category and copyright-notice location. Six retained source records and their acquired bytes are unchanged. Complete PDFs remain private.

No opaque-glyph, OCR, Unicode guessing or alternate-representation policy is introduced. The approved source-mapped ligature policy remains unchanged. A model-free source-preflight command reports mapping, geometry and structural confidence before ingestion. Preflight success alone does not establish tokenizer, membership, index or atomic publication acceptance.
