"""Cost estimate from token usage and the editable price list in the config."""

from __future__ import annotations

from typing import Any, Iterable

from .llm.base import UsageRecord


def _prices_for(model: str, pricing: dict[str, Any]) -> dict[str, Any] | None:
    if model in pricing:
        return pricing[model]
    # the API may report a more specific model id (e.g. with a suffix)
    matches = [k for k in pricing if model.startswith(k)]
    return pricing[max(matches, key=len)] if matches else None


def record_cost(record: UsageRecord, pricing: dict[str, Any]) -> float | None:
    prices = _prices_for(record.model, pricing)
    if not prices:
        return None
    total_input = (
        record.input_tokens + record.cache_read_input_tokens + record.cache_creation_input_tokens
    )
    threshold = prices.get("long_context_threshold")
    long = threshold is not None and total_input > threshold
    in_price = float(prices["input_long"] if long and "input_long" in prices else prices["input"])
    out_price = float(prices["output_long"] if long and "output_long" in prices else prices["output"])
    # cache prices are optional in the config; without them cached tokens are
    # priced like regular input (an over- rather than under-estimate)
    in_price_read = float(prices.get("cache_read", in_price))
    in_price_write = float(prices.get("cache_write", in_price))
    return (
        record.input_tokens * in_price
        + record.cache_read_input_tokens * in_price_read
        + record.cache_creation_input_tokens * in_price_write
        + record.output_tokens * out_price
    ) / 1_000_000


def total_cost(records: Iterable[UsageRecord], pricing: dict[str, Any]) -> float | None:
    """Sum of costs; None if any model is missing from the price list."""
    total = 0.0
    for r in records:
        c = record_cost(r, pricing)
        if c is None:
            return None
        total += c
    return total


def format_cost(cost: float | None) -> str:
    if cost is None:
        return "koszt nieznany (brak cennika modelu w config.toml)"
    if cost < 0.01:
        return f"≈ ${cost:.4f}"
    return f"≈ ${cost:.2f}"
