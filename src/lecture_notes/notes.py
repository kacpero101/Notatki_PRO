"""Notes generation: JSON schema, prompts, chunking long transcripts, merging."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .llm.base import LLMProvider, UsageRecord
from .transcript import Block, format_blocks

log = logging.getLogger(__name__)


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_TS = {"type": "string", "description": "Znacznik [hh:mm:ss] bloku transkrypcji, bez nawiasów, lub pusty."}

NOTES_SCHEMA: dict[str, Any] = _obj({
    "summary": {"type": "string", "description": "Kilka zdań streszczenia całego wykładu."},
    "topics": {"type": "array", "items": _obj({
        "title": _STR,
        "timestamp": _TS,
        "points": {"type": "array", "items": _STR},
    })},
    "definitions": {"type": "array", "items": _obj({
        "term": _STR, "definition": _STR, "timestamp": _TS,
    })},
    "formulas": {"type": "array", "items": _obj({
        "description": _STR,
        "formula": {"type": "string", "description": "Wzór jako zwykły tekst, np. f(x) = x^2 + 1."},
        "example": {"type": "string", "description": "Przykład z wykładu albo pusty."},
        "timestamp": _TS,
    })},
    "exam_items": {"type": "array", "items": _obj({
        "content": _STR,
        "reason": {"type": "string", "description": "Krótko: dlaczego to ważne."},
        "kind": {"type": "string", "enum": ["explicit", "likely"]},
        "quote": {"type": "string", "description": "Słowa prowadzącego dla 'explicit', inaczej pusty."},
        "timestamp": _TS,
    })},
    "review_questions": {"type": "array", "items": _STR},
    "transcript_issues": {"type": "array", "items": _obj({
        "fragment": _STR,
        "problem": _STR,
        "suggestion": {"type": "string", "description": "Prawdopodobna poprawna wersja albo pusty."},
        "timestamp": _TS,
    })},
})

NOTES_LIST_KEYS = ("topics", "definitions", "formulas", "exam_items", "review_questions", "transcript_issues")

SYSTEM_PROMPT = """\
Jesteś asystentem studenta informatyki stosowanej. Dostajesz automatyczną transkrypcję \
wykładu (polski, rozpoznawanie mowy — możliwe błędy) i przygotowujesz z niej notatki do nauki.

Zasady:
1. Opieraj się WYŁĄCZNIE na treści transkrypcji. Nie dopisuj wiedzy spoza wykładu jako \
faktów z wykładu. Jeśli wykład coś pomija lub urywa — nie uzupełniaj tego z własnej wiedzy.
2. Pisz po polsku, zwięźle i rzeczowo. Pomijaj dygresje, sprawy organizacyjne niezwiązane \
z materiałem, powtórzenia i wtrącenia.
3. Znaczniki czasu: transkrypcja jest podzielona na bloki zaczynające się od [hh:mm:ss]. \
W polu "timestamp" podawaj znacznik bloku, z którego pochodzi informacja, w formacie \
hh:mm:ss (bez nawiasów). Nigdy nie wymyślaj znaczników. Jeśli transkrypcja nie ma \
znaczników, zostaw pole puste.
4. Wzory zapisuj jako zwykły tekst jednej linii (np. "f(x) = x^2 + 1", "sum_{i=1}^{n} a_i", \
"O(n log n)"), bez LaTeX-a i bez Markdowna. Słowne opisy wzorów z mowy zamień na zapis \
symboliczny tylko wtedy, gdy jest jednoznaczny.
5. "Notatki tematyczne" (topics): uporządkowany podział materiału na tematy w kolejności \
wykładu; w punktach konkretne treści (fakty, kroki algorytmów, własności, zależności).
6. "Na egzamin" (exam_items): kind="explicit" tylko wtedy, gdy prowadzący wprost powiedział, \
że coś będzie na egzaminie/kolokwium/zaliczeniu albo że trzeba to umieć — wtedy w "quote" \
przytocz jego słowa z transkrypcji. kind="likely" dla treści mocno akcentowanych, \
powtarzanych lub przedstawionych jako kluczowe; "quote" zostaw puste. W "reason" krótko \
uzasadnij (np. "powtórzone trzy razy", "prowadzący: to trzeba umieć").
7. "Pytania do powtórki": 5–15 pytań kontrolnych, na które da się odpowiedzieć z materiału.
8. "Fragmenty do sprawdzenia" (transcript_issues): miejsca, gdzie transkrypcja jest \
prawdopodobnie błędna — przekręcone terminy, nazwiska, wzory, liczby, zdania bez sensu. \
Podaj fragment, na czym polega problem i (jeśli się da) prawdopodobną poprawną wersję. \
W notatkach używaj poprawionej wersji tylko wtedy, gdy jest oczywista z kontekstu.
9. Jeśli jakaś sekcja nie ma treści, zwróć pustą listę. Teksty pól bez formatowania \
Markdown (bez **, #, list z myślnikami)."""

MERGE_PROMPT = """\
Dostajesz częściowe notatki (JSON) z kolejnych części jednego wykładu. Połącz je w jedne \
notatki o tym samym schemacie:
- "summary": jedno spójne streszczenie całego wykładu (kilka zdań),
- scal tematy o tej samej treści, zachowując kolejność wykładu; usuń powtórzenia definicji, \
wzorów, punktów egzaminacyjnych i pytań,
- zachowaj znaczniki czasu z części (nie zmieniaj ich i nie wymyślaj nowych),
- nie dodawaj żadnych nowych informacji — tylko scalaj i porządkuj,
- pytania do powtórki: wybierz najlepsze 8–20."""


@dataclass
class NotesResult:
    notes: dict[str, Any]
    usage: list[UsageRecord] = field(default_factory=list)
    parts: int = 1


def split_blocks(blocks: list[Block], max_chars: int) -> list[list[Block]]:
    """Split blocks into parts whose formatted text stays under ``max_chars``."""
    parts: list[list[Block]] = [[]]
    size = 0
    for b in blocks:
        length = len(b.text) + 12
        if parts[-1] and size + length > max_chars:
            parts.append([])
            size = 0
        parts[-1].append(b)
        size += length
    return [p for p in parts if p]


def _user_message(title: str, transcript_text: str, has_timestamps: bool, part: tuple[int, int] | None) -> str:
    header = [f"Nazwa pliku wykładu: {title}"]
    if part:
        header.append(
            f"To jest część {part[0]} z {part[1]} transkrypcji. Zrób notatki tylko z tej części; "
            "zostaną później scalone z pozostałymi."
        )
    if not has_timestamps:
        header.append("Ta transkrypcja NIE ma znaczników czasu — wszystkie pola timestamp zostaw puste.")
    return "\n".join(header) + "\n\n<transkrypcja>\n" + transcript_text + "\n</transkrypcja>"


_TS_RE = re.compile(r"^\[?(\d{1,2}):(\d{2}):(\d{2})\]?$")


def sanitize_timestamps(notes: dict[str, Any], has_timestamps: bool, duration: float | None) -> dict[str, Any]:
    """Blank timestamps that are malformed, out of range, or when the source had none."""
    for key in NOTES_LIST_KEYS:
        for item in notes.get(key, []):
            if not isinstance(item, dict) or "timestamp" not in item:
                continue
            ts = str(item.get("timestamp") or "").strip()
            m = _TS_RE.match(ts)
            if not has_timestamps or not m:
                item["timestamp"] = ""
                continue
            h, mi, s = map(int, m.groups())
            seconds = h * 3600 + mi * 60 + s
            if mi > 59 or s > 59 or (duration is not None and seconds > duration + 5):
                item["timestamp"] = ""
            else:
                item["timestamp"] = f"{h:02d}:{mi:02d}:{s:02d}"
    return notes


def empty_notes() -> dict[str, Any]:
    return {"summary": "", **{k: [] for k in NOTES_LIST_KEYS}}


def generate_notes(
    provider: LLMProvider,
    title: str,
    blocks: list[Block],
    has_timestamps: bool,
    duration: float | None,
    max_chars: int,
) -> NotesResult:
    parts = split_blocks(blocks, max_chars)
    usage: list[UsageRecord] = []

    if len(parts) == 1:
        resp = provider.generate_json(
            SYSTEM_PROMPT, _user_message(title, format_blocks(parts[0]), has_timestamps, None), NOTES_SCHEMA
        )
        usage += resp.usage
        notes = resp.data
    else:
        log.info("Transcript split into %d parts", len(parts))
        partial = []
        for i, part in enumerate(parts, 1):
            resp = provider.generate_json(
                SYSTEM_PROMPT,
                _user_message(title, format_blocks(part), has_timestamps, (i, len(parts))),
                NOTES_SCHEMA,
            )
            usage += resp.usage
            partial.append(resp.data)
        merge_input = "\n\n".join(
            f"<czesc numer=\"{i}\">\n{json.dumps(p, ensure_ascii=False)}\n</czesc>"
            for i, p in enumerate(partial, 1)
        )
        resp = provider.generate_json(MERGE_PROMPT, f"Wykład: {title}\n\n{merge_input}", NOTES_SCHEMA)
        usage += resp.usage
        notes = resp.data

    notes = {**empty_notes(), **notes}
    notes = sanitize_timestamps(notes, has_timestamps, duration)
    return NotesResult(notes=notes, usage=usage, parts=len(parts))
