"""Immutable source-bound spans. Text validity is deliberately separate from truth."""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator


def digest(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


class CitationError(ValueError):
    pass


class Scope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workspace_id: UUID
    kb_id: UUID
    revision_id: UUID


class Box(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    page_index: int = Field(ge=0)
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("empty_or_inverted_box")
        return self


class TableCell(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    table_id: str = Field(min_length=1)
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    row_header: str = Field(min_length=1)
    column_header: str = Field(min_length=1)


class Block(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    scope: Scope
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    block_id: str
    text: str
    locator_kind: Literal["paragraph", "pdf_bbox", "table_cells"] = "paragraph"
    boxes: tuple[Box, ...] = ()
    char_boxes: tuple[Box, ...] = ()
    table_cell: TableCell | None = None
    normalizer_revision: str = "literal-codepoints-v1"

    @model_validator(mode="after")
    def layout_contract(self):
        if self.locator_kind == "pdf_bbox" and not self.boxes:
            raise ValueError("pdf_bbox_requires_boxes")
        if self.char_boxes and len(self.char_boxes) != len(self.text):
            raise ValueError("char_map_length_mismatch")
        if (self.locator_kind == "table_cells") != (self.table_cell is not None):
            raise ValueError("table_locator_mismatch")
        return self


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: UUID
    scope: Scope
    block_id: str
    source_sha256: str
    canonical_text_sha256: str
    normalizer_revision: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    quote: str = Field(min_length=1)
    quote_sha256: str
    locator_kind: Literal["paragraph", "pdf_bbox", "table_cells"]
    boxes: tuple[Box, ...]
    table_cell: TableCell | None = None
    support_status: Literal["not_assessed"] = "not_assessed"


def bind_span(block: Block, start: int, end: int, quote: str) -> EvidenceSpan:
    if not (0 <= start < end <= len(block.text)) or block.text[start:end] != quote:
        raise CitationError("quote_or_range_mismatch")
    boxes = block.boxes
    if block.locator_kind == "pdf_bbox":
        if block.char_boxes:
            boxes = block.char_boxes[start:end]
        elif start != 0 or end != len(block.text):
            raise CitationError("partial_pdf_span_requires_char_map")
    identity = json.dumps(
        [
            block.scope.model_dump(mode="json"),
            block.source_sha256,
            block.block_id,
            block.normalizer_revision,
            digest(block.text),
            start,
            end,
        ],
        sort_keys=True,
        ensure_ascii=False,
    )
    return EvidenceSpan(
        id=uuid5(NAMESPACE_URL, identity),
        scope=block.scope,
        block_id=block.block_id,
        source_sha256=block.source_sha256,
        canonical_text_sha256=digest(block.text),
        normalizer_revision=block.normalizer_revision,
        start_offset=start,
        end_offset=end,
        quote=quote,
        quote_sha256=digest(quote),
        locator_kind=block.locator_kind,
        boxes=boxes,
        table_cell=block.table_cell,
    )


def resolve_span(span: EvidenceSpan, block: Block, authorized_scope: Scope) -> str:
    if span.scope != authorized_scope or block.scope != authorized_scope:
        raise CitationError("scope_denied")
    expected = bind_span(block, span.start_offset, span.end_offset, span.quote)
    if expected != span:
        raise CitationError("evidence_identity_mismatch")
    return expected.quote


def utf16_range(text: str, start: int, end: int) -> tuple[int, int]:
    if not 0 <= start <= end <= len(text):
        raise CitationError("invalid_range")
    return len(text[:start].encode("utf-16-le")) // 2, len(text[:end].encode("utf-16-le")) // 2
