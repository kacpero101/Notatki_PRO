"""Claude API implementation of LLMProvider (official ``anthropic`` SDK)."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from .base import LLMError, LLMProvider, LLMResponse, UsageRecord

log = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str, settings: dict[str, Any], api_key: str, client: Any = None):
        super().__init__(model, settings)
        self.client = client or anthropic.Anthropic(api_key=api_key, max_retries=4)

    def _use_fallback(self) -> bool:
        # server-side fallback is not offered for Haiku models
        return bool(self.settings.get("refusal_fallback", True)) and "haiku" not in self.model

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResponse:
        params: dict[str, Any] = dict(
            model=self.model,
            max_tokens=int(self.settings.get("max_output_tokens", 32000)),
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self.settings.get("effort", "medium"),
                "format": {"type": "json_schema", "schema": schema},
            },
        )
        try:
            if self._use_fallback():
                stream = self.client.beta.messages.stream(
                    betas=[FALLBACK_BETA], fallbacks="default", **params
                )
            else:
                stream = self.client.messages.stream(**params)
            with stream as s:
                message = s.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError("Nieprawidłowy klucz API Anthropic — uruchom `lecture-notes setup`.") from e
        except anthropic.PermissionDeniedError as e:
            raise LLMError("Klucz API nie ma uprawnień do tego modelu.") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Nieznany model: {self.model} (sprawdź config.toml).") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Przekroczony limit zapytań API — spróbuj za chwilę.") from e
        except anthropic.BadRequestError as e:
            raise LLMError(f"Błędne zapytanie do API: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Błąd serwera API ({e.status_code}) — spróbuj później.") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Brak połączenia z API Anthropic — sprawdź internet.") from e

        log.info(
            "Claude response: model=%s stop_reason=%s request_id=%s",
            message.model, message.stop_reason, getattr(message, "_request_id", None),
        )
        usage = _usage_records(message, self.model)

        if message.stop_reason == "refusal":
            raise LLMError("Model odmówił przetworzenia tej transkrypcji.")
        if message.stop_reason == "max_tokens":
            raise LLMError("Odpowiedź modelu ucięta — zwiększ llm.max_output_tokens w config.toml.")

        text = next((b.text for b in message.content if b.type == "text"), None)
        if text is None:
            raise LLMError("Model nie zwrócił treści notatek.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError("Model zwrócił niepoprawny JSON.") from e
        return LLMResponse(data=data, usage=usage)


def _usage_records(message: Any, requested_model: str) -> list[UsageRecord]:
    """One record per billed model. With server-side fallback the API reports
    per-model iterations; otherwise the top-level usage is used."""
    usage = message.usage
    iterations = getattr(usage, "iterations", None) or []
    records = []
    for it in iterations:
        model = getattr(it, "model", None)
        if model:
            records.append(UsageRecord(
                model=model,
                input_tokens=it.input_tokens or 0,
                output_tokens=it.output_tokens or 0,
                cache_read_input_tokens=it.cache_read_input_tokens or 0,
                cache_creation_input_tokens=it.cache_creation_input_tokens or 0,
            ))
    if records:
        return records
    return [UsageRecord(
        model=getattr(message, "model", None) or requested_model,
        input_tokens=usage.input_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )]
