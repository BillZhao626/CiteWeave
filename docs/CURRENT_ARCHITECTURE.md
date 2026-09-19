# Current engineering architecture

React/TypeScript uses generated OpenAPI types. Ask calls FastAPI SSE directly;
ingestion and evaluation execute asynchronously through Celery notifications on
Redis 8.2.9. PostgreSQL is authoritative for snapshots, task states, ownership,
deadlines and results. Qdrant contains rebuildable typed indexes. LocalBlobStore
retains immutable source bytes and canonical geometry.

The structural profile preserves source/version/parser/canonical identity.
Section/Clause nodes organize real Parents; RetrievalChildren map through
ChildSpan membership to immutable EvidenceSpans. E5 Dense and child BM25 fuse
with RRF k=60. Pinned BGE reranks the candidate pool; bounded Parent expansion
adds original spans to an EvidencePack. Final Citation IDs are span IDs, never
Child IDs. PDF.js renders the original PDF with its stored geometry.

The evaluation outbox commits before publication. Duplicate delivery is safe
through generation, owner/fence and state checks. ProviderPhase commits before
send; uncertain outcomes retain reservations and cannot automatically resend.
All attempt/admission/dispatch/deadline limits remain those accepted in C4.

Product read models add authorized, bounded inspection only. They neither
schedule work nor change source identities. Every displayed rank belongs to a
recorded retrieval candidate; Parent-added context gets no invented rank.
Late-result audit and cancellation remain PostgreSQL facts.

Target model revisions, image digests and runtime limits are in the existing
locks, deployment files and profile contracts. General Assistant V2 and M0–M3
are historical references only. The current target has no quality/default
promotion, production SLA or final concurrency claim.
