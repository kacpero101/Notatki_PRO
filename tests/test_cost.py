import tomllib

import pytest

from lecture_notes.config import example_config_text
from lecture_notes.cost import format_cost, record_cost, total_cost
from lecture_notes.llm.base import UsageRecord

PRICING = {
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.2},
    "claude-haiku-5-5": {
        "input": 0.1, "output": 0.5,
        "long_context_threshold": 100_000, "input_long": 0.5, "output_long": 2.5,
    },
}


def test_basic_cost():
    r = UsageRecord("claude-sonnet-5-5", input_tokens=1_000_000, output_tokens=100_000)
    assert record_cost(r, PRICING) == pytest.approx(2.0 + 1.0)


def test_cache_read_price_and_default():
    r = UsageRecord("claude-sonnet-5-5", cache_read_input_tokens=1_000_000)
    assert record_cost(r, PRICING) == pytest.approx(0.2)
    # no cache_write price configured -> priced like input
    r = UsageRecord("claude-sonnet-5-5", cache_creation_input_tokens=1_000_000)
    assert record_cost(r, PRICING) == pytest.approx(2.0)


def test_long_context_tier():
    short = UsageRecord("claude-haiku-5-5", input_tokens=100_000, output_tokens=10_000)
    long = UsageRecord("claude-haiku-5-5", input_tokens=100_001, output_tokens=10_000)
    assert record_cost(short, PRICING) == pytest.approx(0.01 + 0.005)
    assert record_cost(long, PRICING) == pytest.approx(100_001 * 0.5 / 1e6 + 0.025)


def test_model_id_with_suffix_uses_prefix_price():
    r = UsageRecord("claude-sonnet-5-5-20261001", input_tokens=1_000_000)
    assert record_cost(r, PRICING) == pytest.approx(2.0)


def test_total_cost_and_unknown_model():
    records = [
        UsageRecord("claude-sonnet-5-5", input_tokens=500_000),
        UsageRecord("claude-haiku-5-5", output_tokens=1_000_000),
    ]
    assert total_cost(records, PRICING) == pytest.approx(1.0 + 0.5)
    assert total_cost(records + [UsageRecord("mystery", input_tokens=1)], PRICING) is None


def test_format_cost():
    assert format_cost(0.1234) == "≈ $0.12"
    assert format_cost(0.0042) == "≈ $0.0042"
    assert "nieznany" in format_cost(None)


def test_example_config_has_prices_for_configured_models():
    cfg = tomllib.loads(example_config_text())
    assert cfg["llm"]["model"] in cfg["pricing"]
    assert "claude-haiku-5-5" in cfg["pricing"]
