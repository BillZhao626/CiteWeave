import pytest

from citeweave.evidence import Block, Box, CitationError, Scope, bind_span


def test_partial_pdf_geometry_is_sliced_at_character_positions():
    scope = Scope(
        workspace_id="00000000-0000-0000-0000-000000000001",
        kb_id="00000000-0000-0000-0000-000000000002",
        revision_id="00000000-0000-0000-0000-000000000003",
    )
    boxes = tuple(Box(page_index=0, left=i / 10, top=0.1, right=(i + 1) / 10, bottom=0.2) for i in range(4))
    block = Block(
        scope=scope,
        source_sha256="a" * 64,
        block_id="p0",
        text="中文定位",
        locator_kind="pdf_bbox",
        boxes=boxes,
        char_boxes=boxes,
    )
    assert bind_span(block, 1, 3, "文定").boxes == boxes[1:3]
    coarse = block.model_copy(update={"char_boxes": ()})
    with pytest.raises(CitationError, match="partial_pdf_span_requires_char_map"):
        bind_span(coarse, 1, 3, "文定")
    assert bind_span(coarse, 0, 4, "中文定位").boxes == boxes
