"""Explicit opt-in PDF policies; legacy identities and limits are unchanged."""

import json
from hashlib import sha256

from citeweave.pipeline import PIPELINE_VERSION, PROFILE

PARSER_REVISION = "glyph-structure-v2"
CHILD_POLICY = "structural-child-v1"
STRUCTURAL_PIPELINE = "pdf-structure-e5-child-v1"
TARGETS = ("general-text-pdf-v1", "telecom-protocol-pdf-v1")


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value):
    return sha256(canonical_json(value).encode()).hexdigest()


def canonical_block_bytes(blocks):
    yield b"["
    for i, block in enumerate(blocks):
        if i:
            yield b","
        yield canonical_json(block.model_dump(mode="json")).encode()
    yield b"]"


def canonical_blocks_hash(blocks):
    result = sha256()
    for part in canonical_block_bytes(blocks):
        result.update(part)
    return result.hexdigest()


def document_profile(name=PIPELINE_VERSION):
    if name == PIPELINE_VERSION:
        return dict(PROFILE)
    if name not in TARGETS:
        raise ValueError("unknown_ingestion_profile")
    return {
        **PROFILE,
        "pipeline": STRUCTURAL_PIPELINE,
        "document_profile": name,
        "parser_revision": PARSER_REVISION,
        "child_policy": CHILD_POLICY,
        "unit_kind": "structural_child",
        "bm25_scope": "index_build",
        "limits": {
            "bytes": 32 * 1024 * 1024,
            "pages": 600,
            "atoms": 100000,
            "children": 20000,
            "deadline_seconds": 7200,
            "child_atoms": 24,
            "child_chars": 960,
            "e5_body": 192,
            "e5_heading": 32,
            "e5_input": 256,
            "bge_body": 320,
            "bge_query": 128,
            "bge_pair": 512,
            "parent_tokens": 4096,
            "parent_children": 24,
        },
    }


def structural(profile):
    return profile.get("document_profile") in TARGETS


def validate_profile(profile):
    expected = document_profile(profile.get("document_profile", PIPELINE_VERSION))
    if profile != expected:
        raise ValueError("ingestion_profile_mismatch")
    return expected
