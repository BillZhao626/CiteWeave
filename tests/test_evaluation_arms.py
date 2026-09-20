from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from citeweave.evaluation.arms import budget_legacy
from citeweave.evidence import Block, Scope
from citeweave.pipeline import chunk_blocks


def test_document_scale_changes_no_glyph_boundaries():
    scope = Scope(workspace_id=uuid4(), kb_id=uuid4(), revision_id=uuid4())
    blocks = [Block(scope=scope, source_sha256="a" * 64, block_id="original", text="a" * 160001)]
    with pytest.raises(ValueError, match="chunk_count"):
        chunk_blocks(blocks)
    large = chunk_blocks(blocks, max_chunks=100000)
    assert len(large) == 1001
    assert [len(c["text"]) for c in large] == [160] * 1000 + [1]
    assert [c["evidence"]["start_offset"] for c in large] == list(range(0, 160001, 160))
    small = [blocks[0].model_copy(update={"text": "original fixture"})]
    assert chunk_blocks(small) == chunk_blocks(small, max_chunks=100000)


def test_B1_proxy_gate_counts_serialization_and_preserves_whole_spans():
    class Tokens:
        def count(self, texts):
            return [{"bge": len(t) * 3} for t in texts]

    chunks = [
        NS(
            id=str(n),
            version_id="v",
            text="x" * 150,
            evidence={"start_offset": n * 150, "boxes": [dict(page_index=0, top=n / 1000, left=0)]},
        )
        for n in range(10)
    ]
    chosen, pack = budget_legacy(chunks[:6], chunks, "original fixture", Tokens())
    assert pack["serialized_tokens"] <= 2048
    assert pack["serialized_chars"] <= 6400 and len(chosen) <= 96
    assert len(chosen) < 6
    assert all(c.text == "x" * 150 for c in chosen)
