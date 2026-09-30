"""Estimated CNY using the pinned rate card, never provider actual billing."""

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

RATE_CARD = "deepseek-flash-CNY-2026-09-13"
PEAK_CACHE_HIT = Decimal("0.04")
PEAK_INPUT = Decimal(2)
PEAK_OUTPUT = Decimal(8)


def maximum_cost(input_tokens, output_tokens, revision=RATE_CARD):
    """Exact Decimal reservation: peak time, cache miss, full output allowance."""
    if revision != RATE_CARD or any(type(v) is not int or v < 0 for v in (input_tokens, output_tokens)):
        raise ValueError("provider_rate_identity_invalid")
    return (Decimal(input_tokens) * PEAK_INPUT + Decimal(output_tokens) * PEAK_OUTPUT) / Decimal(1000000)


def breakdown(usage, when=None):
    if not usage or "prompt_tokens" not in usage or "completion_tokens" not in usage:
        return None
    local = (when or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Shanghai"))
    peak = local.weekday() < 5 and (9 <= local.hour < 12 or 14 <= local.hour < 18)
    hit = min(usage.get("prompt_cache_hit_tokens", 0), usage["prompt_tokens"])
    miss = usage["prompt_tokens"] - hit
    factor = Decimal(1 if peak else "0.5") / Decimal(1_000_000)
    input_cost = (Decimal(hit) * PEAK_CACHE_HIT + Decimal(miss) * PEAK_INPUT) * factor
    output_cost = Decimal(usage["completion_tokens"]) * PEAK_OUTPUT * factor
    return dict(
        input_yuan=float(input_cost),
        output_yuan=float(output_cost),
        estimated_yuan=float(input_cost + output_cost),
        rate_card=RATE_CARD,
        actual_charge="unavailable",
    )


def estimated_cost(usage, when=None):
    value = breakdown(usage, when)
    if not value or usage.get("uncertain_retry"):
        return None
    return Decimal(str(value["estimated_yuan"]))


def attempt_cost(calls):
    """Any unknown attempt keeps the aggregate unknown; known subtotals remain in calls."""
    if any(call.get("estimated_yuan") is None for call in calls):
        return None
    return sum((Decimal(str(call["estimated_yuan"])) for call in calls), Decimal(0))
