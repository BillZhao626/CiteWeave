# CiteWeave independent public telecom corpus

The fixed release-source metadata is in `corpus/public_telecom_manifest.json`. Fetch and verify with:

```powershell
.venv\Scripts\python.exe scripts/fetch_public_telecom.py
```

The default destination is `.runtime/private/public-telecom`, excluded from Git. Existing files must match exactly; the downloader refuses changed bytes and never selects a newer edition automatically. Network/identity failures are recorded explicitly in the private acquisition report. SHA-256 establishes reproducible acquired bytes, not a publisher signature.

RFC sources are official RFC Editor PDFs. Their Copyright Notice refers to the IETF Trust Legal Provisions applicable on publication. MQTT 5.0 OS is the fixed OASIS Standard dated 07 March 2019; its Notices appear on PDF page 3. Keep notices with privately acquired sources. Public downloadability is not permission to redistribute complete derived corpora.

This repository distributes independently written parser code, original fixtures and source metadata only. Do not commit downloaded PDFs, extracted standards text, page images, vectors or bulk span exports. Runtime structural evidence is private. No benchmark questions, gold answers or proprietary source data are used by the parser.

See `docs/ADR_PUBLIC_TELECOM_CORPUS_DELTA.md` and `docs/ADR_PUBLIC_TELECOM_FINAL_REPLACEMENT.md` for the approved source changes. Previous selections are preserved; the active manifest is a new revision.

Before ingesting another PDF, run the read-only, model-free diagnostic:

```powershell
.venv\Scripts\python.exe -m citeweave.source_preflight path/to/document.pdf
```

It reports the PDF signature/hash, pages, replacement and unverifiable mappings, geometry failures, and parser confidence. It never repairs text, calls models, writes database rows or builds indexes. Its success is source preflight only, not ingestion acceptance. Keep reports containing local source metadata in the private evidence area.
