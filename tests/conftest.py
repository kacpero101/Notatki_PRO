from __future__ import annotations

import copy
from typing import Any

import pytest

from lecture_notes.llm.base import LLMProvider, LLMResponse, UsageRecord

SAMPLE_NOTES: dict[str, Any] = {
    "summary": "Wykład o pochodnych funkcji jednej zmiennej.",
    "topics": [
        {"title": "Pochodna", "timestamp": "00:00:03", "points": ["Definicja przez granicę ilorazu różnicowego."]},
    ],
    "definitions": [
        {"term": "Pochodna", "definition": "Granica ilorazu różnicowego.", "timestamp": "00:00:03"},
    ],
    "formulas": [
        {"description": "Pochodna funkcji kwadratowej", "formula": "f(x) = x^2 + 1  =>  f'(x) = 2x",
         "example": "f'(3) = 6", "timestamp": "00:00:03"},
    ],
    "exam_items": [
        {"content": "Liczenie pochodnej wielomianu", "reason": "Prowadzący zapowiedział wprost.",
         "kind": "explicit", "quote": "To będzie na kolokwium.", "timestamp": "00:00:03"},
        {"content": "Interpretacja geometryczna", "reason": "Powtórzone kilka razy.",
         "kind": "likely", "quote": "", "timestamp": ""},
    ],
    "review_questions": ["Jak definiujemy pochodną?"],
    "transcript_issues": [
        {"fragment": "pochodna z iksa", "problem": "Niejasne", "suggestion": "pochodna po x", "timestamp": "00:00:05"},
    ],
}

SAMPLE_GENERAL_NOTES: dict[str, Any] = {
    "summary": "Podcast o uczeniu ze wzmocnieniem.",
    "topics": [{"title": "Agent i środowisko", "timestamp": "00:00:00", "points": ["Agent maksymalizuje nagrodę."]}],
    "definitions": [{"term": "Polityka (policy)", "definition": "Reguła wyboru akcji.", "timestamp": "00:00:45"}],
    "takeaways": [{"text": "Nagroda definiuje cel agenta.", "timestamp": "00:00:45"}],
    "formulas": [],
    "review_questions": ["Czym jest polityka?"],
    "supplements": [{"title": "Kontekst", "content": "Termin pochodzi z psychologii behawioralnej."}],
    "transcript_issues": [],
}


class FakeProvider(LLMProvider):
    """LLM double: records calls and returns canned notes."""

    name = "fake"

    def __init__(self, responses: list[dict[str, Any]] | None = None, model: str = "claude-sonnet-5-5"):
        super().__init__(model, {})
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, system, user, schema):
        self.calls.append({"system": system, "user": user, "schema": schema})
        data = self.responses.pop(0) if self.responses else copy.deepcopy(SAMPLE_NOTES)
        return LLMResponse(data=data, usage=[UsageRecord(self.model, input_tokens=1000, output_tokens=500)])


@pytest.fixture
def fake_provider():
    return FakeProvider()


@pytest.fixture
def sample_notes():
    return copy.deepcopy(SAMPLE_NOTES)
