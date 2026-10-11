"""LLM providers. Add new implementations to PROVIDERS."""

from __future__ import annotations

from typing import Any, Callable

from ..keychain import get_api_key
from .base import LLMError, LLMProvider, LLMResponse, UsageRecord


def _anthropic(llm_cfg: dict[str, Any]) -> LLMProvider:
    from .anthropic_provider import AnthropicProvider

    key = get_api_key("anthropic")
    if not key:
        raise LLMError("Brak klucza API Anthropic — uruchom `lecture-notes setup`.")
    return AnthropicProvider(llm_cfg["model"], llm_cfg, api_key=key)


PROVIDERS: dict[str, Callable[[dict[str, Any]], LLMProvider]] = {
    "anthropic": _anthropic,
}


def create_provider(llm_cfg: dict[str, Any]) -> LLMProvider:
    name = llm_cfg.get("provider", "anthropic")
    try:
        factory = PROVIDERS[name]
    except KeyError:
        raise LLMError(f"Nieznany dostawca LLM: {name}") from None
    return factory(llm_cfg)


__all__ = ["LLMError", "LLMProvider", "LLMResponse", "UsageRecord", "create_provider"]
