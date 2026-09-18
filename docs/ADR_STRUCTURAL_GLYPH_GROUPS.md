# Verified ligature groups in the new structural parser

Explicitly approved on 2026-09-18 after official-source inspection found PDF ToUnicode mappings such as one `fi` glyph mapped to two Unicode codepoints. The original one-codepoint-per-glyph restriction would reject otherwise source-locatable release PDFs.

The narrow delta permits known Latin ligature mappings (`ff`, `fi`, `fl`, `ffi`, `ffl`, `st`) in the new `glyph-structure-v2` parser. Canonical text retains the PDF mapping literally. Each member codepoint references the original shared glyph box; no artificial sub-glyph coordinates are interpolated. An explicit group records its codepoint range, mapped text and original box in the immutable artifact. Atom splitting, including token-driven splitting, must not divide a group. Selecting the group highlights its actual single glyph.

Unrecognized multi-codepoint mappings, replacement characters, missing geometry and invalid coordinates remain unsupported. This is not OCR or guessed text recovery. The legacy parser, EvidenceSpan binding algorithm and historical versions are unchanged; the new normalizer revision applies only to new versions. The earlier frozen design record is retained rather than edited.

Acceptance includes group-preserving atom boundaries, exact bind/resolve, original geometry retention, and real release-source parsing. This amendment does not relax token budgets or allow silent truncation.
