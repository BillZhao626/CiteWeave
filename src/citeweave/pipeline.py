"""Pure pipeline invariants; no database, broker or SDK dependencies."""

from enum import StrEnum

from citeweave.embeddings import E5
from citeweave.evidence import Block, bind_span

PIPELINE_VERSION = "pdf-glyph160-e5small-bm25-rrf60-bgev2-v1"
PROFILE = {
    "pipeline": PIPELINE_VERSION,
    "embedding": E5["model"],
    "embedding_revision": E5["revision"],
    "dimension": E5["dimension"],
    "reranker": "BAAI/bge-reranker-v2-m3",
    "reranker_revision": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
    "chunk_chars": 160,
    "reranker_max_tokens": 512,
    "bm25_scope": "document_version",
    "rrf_k": 60,
    "branch_limit": 40,
    "rerank_limit": 20,
    "evidence_limit": 6,
}


class JobStatus(StrEnum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    RETRY_WAIT = "RETRY_WAIT"
    READY = "READY"
    FAILED_FINAL = "FAILED_FINAL"


ACTIVE = {JobStatus.PARSING, JobStatus.CHUNKING, JobStatus.EMBEDDING, JobStatus.INDEXING}
NEXT = {
    JobStatus.PENDING: JobStatus.PARSING,
    JobStatus.RETRY_WAIT: JobStatus.PARSING,
    JobStatus.PARSING: JobStatus.CHUNKING,
    JobStatus.CHUNKING: JobStatus.EMBEDDING,
    JobStatus.EMBEDDING: JobStatus.INDEXING,
    JobStatus.INDEXING: JobStatus.READY,
}


def transition_allowed(old: JobStatus, new: JobStatus):
    return NEXT.get(old) == new or (old in ACTIVE and new in {JobStatus.RETRY_WAIT, JobStatus.FAILED_FINAL})


def chunk_blocks(blocks: list[Block], max_chars: int = 160) -> list[dict]:
    if not 1 <= max_chars <= 160:
        raise ValueError("invalid_chunk_limit")
    result = []
    for block in blocks:
        if not block.text.strip():
            continue
        for start in range(0, len(block.text), max_chars):
            end = min(len(block.text), start + max_chars)
            evidence = bind_span(block, start, end, block.text[start:end])
            result.append(
                {
                    "id": str(evidence.id),
                    "text": evidence.quote,
                    "block": block.model_dump(mode="json"),
                    "evidence": evidence.model_dump(mode="json"),
                }
            )
    if not result or len(result) > 1000:
        raise ValueError("chunk_count_out_of_range")
    return result
