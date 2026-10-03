"""Conversation policy rules; all external observations are synthetic."""

import pytest

from citeweave.runtime_reliability import classify, retry_delay


@pytest.mark.parametrize(
    "code,dispatched,expected",
    [
        ("llm_timeout", False, "BEFORE_DISPATCH"),
        ("llm_timeout", True, "UNKNOWN"),
        ("llm_connection_failed", True, "RETRYABLE_KNOWN"),
        ("llm_http_429", True, "RETRYABLE_KNOWN"),
        ("llm_http_503", True, "UNKNOWN"),
        ("llm_http_401", True, "PERMANENT"),
        ("llm_key_missing", False, "PERMANENT"),
        ("circuit_open", False, "RETRYABLE_KNOWN"),
        ("unrecognized", True, "UNKNOWN"),
        ("llm_stream_incomplete", True, "UNKNOWN"),
    ],
)
def test_retry_classification(code, dispatched, expected):
    assert classify(code, dispatched) == expected


def test_backoff_is_bounded_exponential_full_jitter():
    assert retry_delay(1, 0.25) == 0.125
    assert retry_delay(2, 0.25) == 0.25
    assert retry_delay(100, 1) == 4
    assert retry_delay(1, 0) == 0
