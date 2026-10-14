"""Note modes: what the notes contain (JSON schema, prompts, document sections).

* ``lecture`` — university lecture, Polish, with an exam section (default).
* ``general`` — a recording on any topic, any language; notes in Polish, with a
  clearly separated section for knowledge added by the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Section:
    key: str          # notes field and renderer name in docx_builder
    heading: str
    optional: bool = False  # left out of the document when empty


@dataclass(frozen=True)
class NoteMode:
    name: str
    label: str          # notification title / document subject
    quick_action: str   # Finder menu item
    schema: dict[str, Any]
    system_prompt: str
    merge_prompt: str
    sections: tuple[Section, ...]


# ------------------------------------------------------------- schema parts

def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _list(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


_STR = {"type": "string"}
_TS = {"type": "string", "description": "Znacznik [hh:mm:ss] bloku transkrypcji, bez nawiasów, lub pusty."}

SUMMARY = {"type": "string", "description": "Kilka zdań streszczenia całości."}
TOPICS = _list(_obj({"title": _STR, "timestamp": _TS, "points": _list(_STR)}))
DEFINITIONS = _list(_obj({"term": _STR, "definition": _STR, "timestamp": _TS}))
FORMULAS = _list(_obj({
    "description": _STR,
    "formula": {"type": "string", "description": "Wzór jako zwykły tekst, np. f(x) = x^2 + 1."},
    "example": {"type": "string", "description": "Przykład z nagrania albo pusty."},
    "timestamp": _TS,
}))
EXAM_ITEMS = _list(_obj({
    "content": _STR,
    "reason": {"type": "string", "description": "Krótko: dlaczego to ważne."},
    "kind": {"type": "string", "enum": ["explicit", "likely"]},
    "quote": {"type": "string", "description": "Słowa prowadzącego dla 'explicit', inaczej pusty."},
    "timestamp": _TS,
}))
TAKEAWAYS = _list(_obj({"text": _STR, "timestamp": _TS}))
SUPPLEMENTS = _list(_obj({
    "title": _STR,
    "content": {"type": "string", "description": "Wyjaśnienie, kontekst lub sprostowanie spoza nagrania."},
}))
REVIEW_QUESTIONS = _list(_STR)
TRANSCRIPT_ISSUES = _list(_obj({
    "fragment": _STR,
    "problem": _STR,
    "suggestion": {"type": "string", "description": "Prawdopodobna poprawna wersja albo pusty."},
    "timestamp": _TS,
}))


# ------------------------------------------------------------ shared rules

_RULE_TIMESTAMPS = """\
Znaczniki czasu: transkrypcja jest podzielona na bloki zaczynające się od [hh:mm:ss]. \
W polu "timestamp" podawaj znacznik bloku, z którego pochodzi informacja, w formacie \
hh:mm:ss (bez nawiasów). Nigdy nie wymyślaj znaczników. Jeśli transkrypcja nie ma \
znaczników, zostaw pole puste."""

_RULE_FORMULAS = """\
Wzory zapisuj jako zwykły tekst jednej linii (np. "f(x) = x^2 + 1", "sum_{i=1}^{n} a_i", \
"O(n log n)"), bez LaTeX-a i bez Markdowna. Słowne opisy wzorów z mowy zamień na zapis \
symboliczny tylko wtedy, gdy jest jednoznaczny."""

_RULE_ISSUES = """\
"Fragmenty do sprawdzenia" (transcript_issues): miejsca, gdzie transkrypcja jest \
prawdopodobnie błędna — przekręcone terminy, nazwiska, wzory, liczby, zdania bez sensu. \
Podaj fragment, na czym polega problem i (jeśli się da) prawdopodobną poprawną wersję. \
W notatkach używaj poprawionej wersji tylko wtedy, gdy jest oczywista z kontekstu."""

_RULE_FORMAT = """\
Jeśli jakaś sekcja nie ma treści, zwróć pustą listę. Teksty pól bez formatowania \
Markdown (bez **, #, list z myślnikami)."""


# ------------------------------------------------------------------ lecture

LECTURE_PROMPT = f"""\
Jesteś asystentem studenta informatyki stosowanej. Dostajesz automatyczną transkrypcję \
wykładu (polski, rozpoznawanie mowy — możliwe błędy) i przygotowujesz z niej notatki do nauki.

Zasady:
1. Opieraj się WYŁĄCZNIE na treści transkrypcji. Nie dopisuj wiedzy spoza wykładu jako \
faktów z wykładu. Jeśli wykład coś pomija lub urywa — nie uzupełniaj tego z własnej wiedzy.
2. Pisz po polsku, zwięźle i rzeczowo. Pomijaj dygresje, sprawy organizacyjne niezwiązane \
z materiałem, powtórzenia i wtrącenia.
3. {_RULE_TIMESTAMPS}
4. {_RULE_FORMULAS}
5. "Notatki tematyczne" (topics): uporządkowany podział materiału na tematy w kolejności \
wykładu; w punktach konkretne treści (fakty, kroki algorytmów, własności, zależności).
6. "Na egzamin" (exam_items): kind="explicit" tylko wtedy, gdy prowadzący wprost powiedział, \
że coś będzie na egzaminie/kolokwium/zaliczeniu albo że trzeba to umieć — wtedy w "quote" \
przytocz jego słowa z transkrypcji. kind="likely" dla treści mocno akcentowanych, \
powtarzanych lub przedstawionych jako kluczowe; "quote" zostaw puste. W "reason" krótko \
uzasadnij (np. "powtórzone trzy razy", "prowadzący: to trzeba umieć").
7. "Pytania do powtórki": 5–15 pytań kontrolnych, na które da się odpowiedzieć z materiału.
8. {_RULE_ISSUES}
9. {_RULE_FORMAT}"""

LECTURE_MERGE_PROMPT = """\
Dostajesz częściowe notatki (JSON) z kolejnych części jednego wykładu. Połącz je w jedne \
notatki o tym samym schemacie:
- "summary": jedno spójne streszczenie całego wykładu (kilka zdań),
- scal tematy o tej samej treści, zachowując kolejność wykładu; usuń powtórzenia definicji, \
wzorów, punktów egzaminacyjnych i pytań,
- zachowaj znaczniki czasu z części (nie zmieniaj ich i nie wymyślaj nowych),
- nie dodawaj żadnych nowych informacji — tylko scalaj i porządkuj,
- pytania do powtórki: wybierz najlepsze 8–20."""

LECTURE = NoteMode(
    name="lecture",
    label="Notatki z wykładu",
    quick_action="Zrób notatki",
    schema=_obj({
        "summary": SUMMARY,
        "topics": TOPICS,
        "definitions": DEFINITIONS,
        "formulas": FORMULAS,
        "exam_items": EXAM_ITEMS,
        "review_questions": REVIEW_QUESTIONS,
        "transcript_issues": TRANSCRIPT_ISSUES,
    }),
    system_prompt=LECTURE_PROMPT,
    merge_prompt=LECTURE_MERGE_PROMPT,
    sections=(
        Section("summary", "Streszczenie"),
        Section("topics", "Notatki tematyczne"),
        Section("definitions", "Definicje"),
        Section("formulas", "Wzory i przykłady"),
        Section("exam_items", "Na egzamin / zaliczenie"),
        Section("review_questions", "Pytania do powtórki"),
        Section("transcript_issues", "Fragmenty do sprawdzenia"),
    ),
)


# ------------------------------------------------------------------ general

GENERAL_PROMPT = f"""\
Przygotowujesz notatki z automatycznej transkrypcji nagrania (rozpoznawanie mowy — możliwe \
błędy). Nagranie może dotyczyć dowolnego tematu (np. podcast, film, prezentacja, rozmowa, \
wykład) i być w dowolnym języku. Notatki zawsze piszesz po polsku.

Zasady:
1. Sekcje summary, topics, definitions, takeaways, formulas, review_questions \
i transcript_issues opierają się WYŁĄCZNIE na treści nagrania. Nie mieszaj w nich \
własnej wiedzy i nie uzupełniaj z niej tego, co nagranie pomija.
2. Własną wiedzę możesz dodać tylko w sekcji "supplements" (Uzupełnienia spoza nagrania): \
krótkie wyjaśnienia pojęć, których nagranie nie tłumaczy, a są potrzebne do zrozumienia, \
niezbędny kontekst, oraz sprostowania, gdy w nagraniu padło twierdzenie wyraźnie błędne \
lub nieaktualne (napisz wtedy, co padło w nagraniu i jak jest naprawdę). Każde \
uzupełnienie ma krótki tytuł. Dodawaj tylko to, co realnie pomaga; nie powtarzaj treści \
nagrania. Jeśli nic nie trzeba dodać, zwróć pustą listę.
3. Pisz po polsku, zwięźle i rzeczowo. Pomijaj dygresje, reklamy i sponsorów, powitania, \
sprawy organizacyjne i powtórzenia. Jeśli nagranie nie jest po polsku, przy kluczowych \
terminach podaj w nawiasie oryginalne brzmienie, np. "uczenie ze wzmocnieniem \
(reinforcement learning)".
4. {_RULE_TIMESTAMPS}
5. "Notatki tematyczne" (topics): uporządkowany podział treści na tematy w kolejności \
nagrania; w punktach konkretne informacje, argumenty, kroki, przykłady.
6. "Kluczowe pojęcia" (definitions): pojęcia i ich znaczenie tak, jak wyjaśniono je \
w nagraniu.
7. "Najważniejsze wnioski" (takeaways): 3–10 najważniejszych tez, wniosków lub \
rekomendacji z nagrania — to, co warto zapamiętać, czytając tylko tę sekcję.
8. "Wzory i przykłady" (formulas): {_RULE_FORMULAS} Jeśli w nagraniu nie ma wzorów, \
obliczeń ani fragmentów kodu, zwróć pustą listę.
9. "Pytania do powtórki": 5–15 pytań kontrolnych, na które da się odpowiedzieć z treści \
nagrania.
10. {_RULE_ISSUES} Fragment cytuj w języku transkrypcji.
11. {_RULE_FORMAT}"""

GENERAL_MERGE_PROMPT = """\
Dostajesz częściowe notatki (JSON) z kolejnych części jednego nagrania. Połącz je w jedne \
notatki o tym samym schemacie:
- "summary": jedno spójne streszczenie całego nagrania (kilka zdań),
- scal tematy o tej samej treści, zachowując kolejność nagrania; usuń powtórzenia pojęć, \
wzorów, wniosków, uzupełnień i pytań,
- "takeaways": wybierz 3–10 najważniejszych dla całego nagrania,
- zachowaj znaczniki czasu z części (nie zmieniaj ich i nie wymyślaj nowych),
- nie dodawaj żadnych nowych informacji — tylko scalaj i porządkuj; "supplements" \
pozostają osobną sekcją i nie przenoś ich treści do innych sekcji,
- pytania do powtórki: wybierz najlepsze 8–20."""

GENERAL = NoteMode(
    name="general",
    label="Notatki",
    quick_action="Zrób notatki (dowolny temat)",
    schema=_obj({
        "summary": SUMMARY,
        "topics": TOPICS,
        "definitions": DEFINITIONS,
        "takeaways": TAKEAWAYS,
        "formulas": FORMULAS,
        "review_questions": REVIEW_QUESTIONS,
        "supplements": SUPPLEMENTS,
        "transcript_issues": TRANSCRIPT_ISSUES,
    }),
    system_prompt=GENERAL_PROMPT,
    merge_prompt=GENERAL_MERGE_PROMPT,
    sections=(
        Section("summary", "Streszczenie"),
        Section("topics", "Notatki tematyczne"),
        Section("definitions", "Kluczowe pojęcia"),
        Section("takeaways", "Najważniejsze wnioski"),
        Section("formulas", "Wzory i przykłady", optional=True),
        Section("review_questions", "Pytania do powtórki"),
        Section("supplements", "Uzupełnienia (spoza nagrania)", optional=True),
        Section("transcript_issues", "Fragmenty do sprawdzenia"),
    ),
)


MODES: dict[str, NoteMode] = {m.name: m for m in (LECTURE, GENERAL)}


def get_mode(name: str) -> NoteMode:
    try:
        return MODES[name]
    except KeyError:
        raise ValueError(f"Nieznany tryb notatek: {name} (dostępne: {', '.join(MODES)})") from None
