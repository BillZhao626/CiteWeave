# M1 audit and execution plan · 2026-09-13

Scope: one browser Golden Path, not M2. No old source was read. Git is initialized main with uncommitted M0 files and no remote; no existing AGENTS.md. Environment has DeepSeek key (presence checked without printing); Docker is currently stopped.

| Slice | Current gap | Planned modules | Acceptance |
|---|---|---|---|
| A Contract + DB | KB API partly implemented with inline DDL; no versions/migrations | schemas, domain, db, Alembic, AGENTS | empty DB upgrade; KB auth/idempotency preserved |
| B Ingestion | M0 recovery has deterministic test effect only | blob store, chunking, ingestion, worker/supervisor, index adapter | real PDF to READY; bounded failures; invisible partial indices |
| C Retrieval + Answer | model/retrieval code only experiment scripts | model gateway, index retriever, LLM provider, prompt, query runs | real dense/sparse/RRF/rerank and DeepSeek stream; budgets/errors |
| D Evidence | M0 original fixtures only | persistent chunks/citations, authorized content/evidence routes | citation to original immutable PDF with exact boxes |
| E React | read-only M0 report dashboard | router, query client, generated types, upload/chat/PDF viewer | all user operations in browser; lint/typecheck/build |
| F Fault acceptance | M0 task tests not ingestion tests | isolated fault controls/tests, clean-start script, reports | kill parsing/embedding/indexing; convergence/no fake READY; resource report |

Reuse evidence.py, BM25/RRF math, pinned models and simple PDF adapter. Do not tune dev qrels. Retain M0 experiments for provenance. First increment is A: tests before DB/blob/state implementation. Then verify each slice before connecting the next.

Risks: 16 GB host memory; Docker stale sockets seen in M0; stale worker Qdrant writes; partial index publication; unsupported PDF layout; late/invalid streamed citations; uncertain paid requests. Address with bounded model gateway and queues, per-attempt staging collection plus fenced publication, parser capability limits, provisional deltas/final validation, and conservative cost reservation. No architecture swap without ADR.

Required final report: status, stage checklist, real architecture, decisions, changed modules, passed/failed/skipped tests, all three failure injections, RAM/ports/cost, limitations and 3–5 M2 priorities.

## Implementation record · 2026-09-14

A–E implemented and integrated. F's three real SIGKILL scenarios passed; final cold-start / browser observations and all acceptance results are consolidated in [M1_ACCEPTANCE](reports/M1_ACCEPTANCE.md), which is the delivery status authority. The initial audit above remains an as-of-start snapshot.

Observed issues addressed during integration: TypeScript compiler API incompatibility (ADR 0003); silent reranker truncation risk (ADR 0002); Windows native recursive PDF asset copy crash (Python asset staging); HTTP/SSE nullable contract drift (shared serialization); unknown retry cost accounting (retain reservation); Windows path separators in model-process Stop matching; launcher test pipe inheritance (write real log files). These are resolved integration findings, not evidence for unrelated performance claims.
