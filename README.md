# CiteWeave · Trace every citation to its source

CiteWeave is an **independent public engineering reconstruction** of a local evidence-grounded RAG product. React Ask, immutable PDF citations, structural inspection, retrieval trace and durable evaluation share one PostgreSQL source of truth. This is a local engineering release candidate; remote publication and Stage-D quality promotion have not occurred.

```text
Official PDF → immutable EvidenceSpans → Section / Clause → Parent → RetrievalChild
                                    ↓
Ask scope → E5 Dense + BM25 → RRF k=60 → BGE → seeds + bounded Parent context
        → EvidencePack → streamed provisional answer → validated Citation → original PDF
```

The structural path is selectable as `telecom-structural-v1`. Existing knowledge bases retain their legacy profile. Target ingestion, retrieval parameters and C1–C4 durable semantics are preserved. Structure inspection does not reparse or edit a source. Citation geometry validity is separate from semantic support.

## Run locally

Supported acceptance environment: Windows 11, PowerShell 7, Python 3.12, Node ≥22.20, pnpm 11.19, Docker Desktop, 16 GB RAM and an RTX 4060 Laptop with 8 GB VRAM. CPU-only and Linux one-command setup have not been accepted. Dependencies, images and model revisions are pinned; no models or dependency binaries are redistributed.

```powershell
.\scripts\m1.ps1 -Setup          # install locked dependencies, start services
.\scripts\m1.ps1 -Action Up      # subsequent start; applies forward migrations
.\scripts\m1.ps1 -Action Verify  # real database/models, mocked generation tests
.\scripts\m1.ps1 -Action Stop    # preserve volumes and original documents
```

The historical script name preserves the existing deployment/data layout. Open [the local workbench](http://127.0.0.1:18080/), then use the generated local `CW_ADMIN_TOKEN`. Do not paste tokens into source or frontend variables. `.env.example` documents optional settings. `DEEPSEEK_API_KEY` is optional: without it, existing runs and evidence remain inspectable, but real generation is unavailable. Configuring a key and starting Ask/evaluation can incur charges; Stage-C evidence uses explicitly mocked generation.

For an initial functional check, create a knowledge base and upload the original handbook from the UI. For the structural corpus, follow [source acquisition and ingestion](docs/CURRENT_OPERATIONS.md). Official downloaded PDFs stay private; the repository includes metadata, original parser fixtures and source-grounded evaluation annotations, not complete third-party PDFs or bulk extracted text.

## Product surfaces

- **Ask:** knowledge-base/document scope, structural or legacy path, streamed provisional text, final citations and source PDF highlights. A loaded run preserves its recorded profile and version identities.
- **Documents / Structure:** Section/Clause hierarchy, Parent context, Child text and original EvidenceSpan membership.
- **Runs / Trace:** per-build Dense/BM25 ranks, RRF/BGE, seed decisions, Parent additions, source gaps and evidence budgets. Degraded runs do not display fabricated BGE values.
- **Evaluation / Tasks:** finite execution/dispatch/admission accounting, provider outcomes, cancellations, explicit OUTCOME_UNKNOWN and missing semantic judgment. Redis/Celery transport work; PostgreSQL owns business state.

## Engineering evidence and limits

C1–C4 engineering gates established the real Redis/Celery runtime, structural ingestion/typed Qdrant, real E5/BGE retrieval and finite evaluation recovery. Batch 4 passed 167 backend and four frontend tests, plus 18 real-service fault scenarios. Its tiny benchmark smokes prove the harness only. Current UI acceptance is documented in [the product ADR](docs/ADR_C5_PRODUCT_INSPECTION.md); private runtime/screenshots are not bundled into a public source candidate.

The independent telecom dataset has **72 visible cases**: Development 32, Regression 24 and Safety 16. The remaining 24 Holdout cases are **NOT_YET_SEALED**. Labels are AI/source-grounded, not human Gold. Missing judgments remain missing. The full 96-case quality study, final capacity matrix, paid model evaluation and default-profile promotion belong to Stage D and are not claimed here.

Earlier M0–M3 and General Assistant V2 material, where referenced in repository history, is historical. Earlier corpus scores, screenshots and environment inventories do not describe this structural release candidate. No production SLA, enterprise readiness, quality improvement or eight-user capacity is claimed.

## Architecture and reproducibility

- [Current architecture](docs/CURRENT_ARCHITECTURE.md) · [Setup / operations](docs/CURRENT_OPERATIONS.md)
- [Corpus acquisition](docs/data/public_telecom_sources.md) · [Source manifest](corpus/public_telecom_manifest.json)
- [Structural ingestion](docs/ADR_STRUCTURAL_INGESTION.md) · [Structural retrieval](docs/ADR_C3_STRUCTURAL_QUERY_EVIDENCE.md)
- [Durable evaluation](docs/ADR_C4_DURABLE_EVALUATION.md) · [Benchmark harness](benchmarks/README.md)
- [Generated OpenAPI](contracts/openapi.json) · [Third-party terms](THIRD_PARTY.md) · [MIT](LICENSE)

Prepare a reviewed local source candidate with `python scripts/public_candidate.py --stage-only`. It uses an explicit documentation allowlist, rejects active credentials/private machine paths and scans with locally installed Gitleaks. It does not publish, tag, copy Git history or redistribute runtime evidence. No public repository URL exists yet. Preserve third-party rights and notices; source scans are not a legal or security certification.
