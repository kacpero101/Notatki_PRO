"""Provider-agnostic LLM interface.

To add a provider (e.g. Azure OpenAI or a local model) implement ``LLMProvider``
and register it in ``lecture_notes.llm.PROVIDERS``. The rest of the program only
calls ``generate_json`` and reads ``LLMResponse``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    """An error worth showing to the user in a notification (short, no secrets)."""


@dataclass
class UsageRecord:
    """Token usage of one billed model call."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class LLMResponse:
    data: dict[str, Any]
    usage: list[UsageRecord] = field(default_factory=list)


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, model: str, settings: dict[str, Any]):
        self.model = model
        self.settings = settings

    @abstractmethod
    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        """Return a JSON object that validates against ``schema``."""
