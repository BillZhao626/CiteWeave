"""Offline boundary validation, no credentials, network or provider execution."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from citeweave.conversation_provider import CallAuthorization, Observation
from citeweave.costs import RATE_CARD


def grant():
    return dict(
        id=uuid4(),
        run_id=uuid4(),
        purpose="generation",
        provider="deepseek",
        model="deepseek-flash",
        price_revision=RATE_CARD,
        prompt_revision="synthetic-v1",
        request_hash="a" * 64,
        input_tokens=100,
        output_tokens=100,
        max_yuan=Decimal("0.001"),
        expires_at=datetime.now(timezone.utc),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_yuan", 0),
        ("max_yuan", "NaN"),
        ("max_yuan", "0.000000001"),
        ("input_tokens", 0),
        ("input_tokens", True),
        ("output_tokens", -1),
        ("price_revision", "unverified"),
        ("model", "other-model"),
        ("purpose", "judge"),
        ("request_hash", "not-a-hash"),
        ("expires_at", datetime(2026, 1, 1)),
    ],
)
def test_no_implicit_or_invalid_call_authorization(field, value):
    values = grant()
    values[field] = value
    with pytest.raises(ValidationError):
        CallAuthorization(**values)


def test_all_authorization_fields_are_explicit():
    values = grant()
    for field in values:
        with pytest.raises(ValidationError):
            CallAuthorization(**{k: v for k, v in values.items() if k != field})


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": -1},
        {"completion_tokens": True},
        {"total_tokens": "10"},
        {"raw_provider_body": "never persist"},
    ],
)
def test_usage_only_accepts_allowlisted_reported_integer_counts(usage):
    with pytest.raises(ValidationError):
        Observation(result_hash="b" * 64, usage=usage)


def test_partial_usage_stays_partial():
    value = Observation(result_hash="b" * 64, usage={"completion_tokens": 4})
    assert value.usage.model_dump(exclude_none=True) == {"completion_tokens": 4}
