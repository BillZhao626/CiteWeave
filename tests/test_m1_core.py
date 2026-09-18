from uuid import UUID

import pytest

from citeweave.blobs import LocalBlobStore
from citeweave.evidence import Block, Scope
from citeweave.pipeline import JobStatus, chunk_blocks, transition_allowed


def test_blob_roundtrip_integrity_and_path_escape(tmp_path):
    store = LocalBlobStore(tmp_path)
    key = store.put(b"original bytes")
    assert store.put(b"original bytes") == key
    assert store.exists(key) and store.get(key) == b"original bytes"
    with pytest.raises(ValueError):
        store.get("../secret")
    store.path(key).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="blob_integrity"):
        store.get(key)
    store.delete(key)
    assert not store.exists(key)


def test_state_machine_terminal_and_retry_boundaries():
    assert transition_allowed(JobStatus.PENDING, JobStatus.PARSING)
    assert transition_allowed(JobStatus.INDEXING, JobStatus.READY)
    assert transition_allowed(JobStatus.EMBEDDING, JobStatus.RETRY_WAIT)
    assert not transition_allowed(JobStatus.PARSING, JobStatus.READY)
    assert not transition_allowed(JobStatus.READY, JobStatus.PARSING)
    assert not transition_allowed(JobStatus.FAILED_FINAL, JobStatus.PARSING)


def test_chunk_identity_and_exact_unicode_mapping():
    scope = Scope(workspace_id=UUID(int=1), kb_id=UUID(int=2), revision_id=UUID(int=3))
    block = Block(scope=scope, source_sha256="a" * 64, block_id="p1", text="中文😀" * 120)
    chunks = chunk_blocks([block], max_chars=160)
    assert "".join(c["text"] for c in chunks) == block.text
    assert len({c["id"] for c in chunks}) == len(chunks)
    assert chunks == chunk_blocks([block], max_chars=160)
    for c in chunks:
        e = c["evidence"]
        assert c["text"] == block.text[e["start_offset"] : e["end_offset"]]
