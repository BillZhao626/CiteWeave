from uuid import uuid4

import pytest

from citeweave.evidence import Block, CitationError, Scope, bind_span, resolve_span, utf16_range


def block(text="条款😀：等待十秒。等待十秒。", **extra):
    return Block(
        scope=Scope(workspace_id=uuid4(), kb_id=uuid4(), revision_id=uuid4()),
        source_sha256="a" * 64,
        block_id="paragraph-1",
        text=text,
        **extra,
    )


def test_duplicate_quote_needs_exact_offset():
    source = block()
    start = source.text.rindex("等待十秒")
    span = bind_span(source, start, start + 4, "等待十秒")
    assert resolve_span(span, source, source.scope) == "等待十秒"
    assert span.start_offset == start
    assert utf16_range(source.text, 0, 3) == (0, 4)


@pytest.mark.parametrize("start,end,quote", [(-1, 2, "条款"), (0, 500, "条款"), (0, 2, "条文"), (3, 3, "")])
def test_invalid_quote_or_range_fails(start, end, quote):
    with pytest.raises(CitationError):
        bind_span(block(), start, end, quote)


def test_revision_and_acl_must_match_even_for_identical_text():
    source = block()
    span = bind_span(source, 0, 2, "条款")
    changed = source.model_copy(update={"text": "条款已经变更"})
    with pytest.raises(CitationError):
        resolve_span(span, changed, source.scope)
    with pytest.raises(CitationError):
        resolve_span(
            span,
            source,
            Scope(workspace_id=uuid4(), kb_id=source.scope.kb_id, revision_id=source.scope.revision_id),
        )


def test_span_identity_changes_with_revision_and_offset():
    one = block("相同相同")
    two = block("相同相同")
    assert bind_span(one, 0, 2, "相同").id != bind_span(one, 2, 4, "相同").id
    assert bind_span(one, 0, 2, "相同").id != bind_span(two, 0, 2, "相同").id
