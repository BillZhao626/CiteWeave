# Provenance and publication boundary

CiteWeave is an independently implemented personal application. The initial planning phase included a review of a prior project; therefore this work is not represented as a formally isolated clean-room process. Subsequent implementation and M3 changes use this project's new specifications, code, original fixtures and public references; former employer/lab source, prompts, private data and credentials are excluded from the public candidate. Familiar public engineering patterns are used through public libraries and original application code. This is a process record, not a determination of employment-contract ownership or exclusive rights to upstream libraries, models or standards.

First-party application code, original documentation and the original synthetic handbook use the root MIT license. Third-party code, assets, model weights and quoted standard passages retain their own licenses/rights. No attribution is removed by the first-party license. See THIRD_PARTY.md and the generated dependency inventory.

The benchmark's questions, reference answers and gold annotations were AI-assisted and frozen before M2. The 24 M2 Dev review files were submitted by the project owner and explicitly describe AI-assisted material review. Preserve their byte hashes and provenance. They are Human Reference for this workflow, not independently collected human research labels. Calibration on these 24 cases cannot establish general Judge accuracy. Candidate answers never inherit a baseline human label.

Raw RFC/NIST PDFs are fetched only into the ignored runtime corpus and verified against the frozen source manifest. They are not redistributed in the public candidate. Quoted gold passages and report excerpts retain their source and physical location, attribution and original terms; see [data notices](DATA_NOTICES.md). Initial local review/planning files and private audits are retained locally and excluded by `scripts/public_candidate.py`. Do not publish the complete working directory or its local history in place of the scanned source candidate.

## M3 public references

- MIT license text: https://opensource.org/license/mit (first-party licensing template).
- E5-small pinned model card: https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3 (MIT metadata).
- BGE reranker pinned model card: https://huggingface.co/BAAI/bge-reranker-v2-m3/tree/953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e (Apache-2.0 metadata).
- Gitleaks documented directory scanning: https://github.com/gitleaks/gitleaks (scan the explicit candidate because this local repository has no committed history).
- Tailwind explicit source directory: https://tailwindcss.com/docs/detecting-classes-in-source-files (scope the CSS build to application source, independent of checkout location).
- CycloneDX 1.6 official schema: https://github.com/CycloneDX/specification/blob/1.6/schema/bom-1.6.schema.json (validate the installed-component SBOM).

No external RAG implementation was copied for M3 deduplication, context expansion, evaluation or UI comparison. Decisions and rejected experiments are recorded in ADR 0005 and the M3 experiment journal. External references support licenses/tool operation; they are not a substitute for local regression evidence.
