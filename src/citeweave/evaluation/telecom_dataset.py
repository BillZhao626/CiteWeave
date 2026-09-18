"""Independent source support schema; never accepts retrieval child identities."""

from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATASET_ID = "citeweave-public-telecom-eval-v1"
TARGET = {"dev": 32, "regression": 24, "holdout": 24, "safety": 16}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRange(Strict):
    source_id: str
    source_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    source_version: str
    parser_revision: str
    canonical_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    block_id: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    quote_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    page_number: int = Field(ge=1)

    @model_validator(mode="after")
    def nonempty(self):
        if self.end_offset <= self.start_offset:
            raise ValueError("empty_source_range")
        return self


class SupportGroup(Strict):
    group_id: str
    alternatives: list[list[SourceRange]] = Field(min_length=1)

    @model_validator(mode="after")
    def nonempty(self):
        if any(not a for a in self.alternatives):
            raise ValueError("empty_support_alternative")
        return self


class Aspect(Strict):
    aspect_id: str
    description: str
    required_groups: list[str] = Field(min_length=1)


class TelecomCase(Strict):
    case_id: str
    split: Literal["dev", "regression", "safety"]
    clause_groups: list[str] = Field(min_length=1)
    primary_source: str
    question: str = Field(min_length=8, max_length=512)
    question_type: Literal[
        "single_fact", "multi_aspect", "comparison", "location", "unanswerable", "injection", "boundary"
    ]
    answerable: bool
    reference_answer: str
    support_groups: list[SupportGroup]
    required_aspects: list[Aspect]
    required_sources: list[str]
    rubric: dict[str, str]
    label_origin: Literal["AI_source_grounded_not_human_reviewed"]

    @model_validator(mode="after")
    def support_integrity(self):
        ids = [g.group_id for g in self.support_groups]
        if len(set(ids)) != len(ids) or any(
            not set(a.required_groups) <= set(ids) for a in self.required_aspects
        ):
            raise ValueError("invalid_support_groups")
        if self.answerable and (not ids or not self.required_aspects):
            raise ValueError("answerable_without_support")
        return self


def validate_dataset(value):
    if value["dataset_id"] != DATASET_ID or value["holdout"]["status"] != "NOT_YET_SEALED":
        raise ValueError("dataset_identity_or_holdout_state")
    cases = [TelecomCase.model_validate(c) for c in value["cases"]]
    if Counter(c.split for c in cases) != {"dev": 32, "regression": 24, "safety": 16}:
        raise ValueError("visible_split_counts")
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("duplicate_case")
    for split, expected in {
        "dev": {"single_fact": 14, "multi_aspect": 9, "comparison": 6, "location": 3},
        "regression": {"single_fact": 10, "multi_aspect": 7, "comparison": 4, "location": 3},
    }.items():
        if Counter(c.question_type for c in cases if c.split == split) != expected:
            raise ValueError("core_category_stratification")
        if {c.primary_source for c in cases if c.split == split} != {
            s["source_id"] for s in value["sources"]
        }:
            raise ValueError("source_stratification")
    groups = {}
    for c in cases:
        if c.split == "safety":
            continue  # adversarial variants explicitly share their base support
        for g in c.clause_groups:
            if g in groups and groups[g] != c.split:
                raise ValueError("clause_group_leaks_across_splits")
            groups[g] = c.split
    if Counter(c.question_type for c in cases if c.split == "safety") != {
        "unanswerable": 8,
        "injection": 4,
        "boundary": 4,
    }:
        raise ValueError("safety_counts")
    return value
