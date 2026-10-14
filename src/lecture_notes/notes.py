"""Notes generation: prompting per mode, chunking long transcripts, merging."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .llm.base import LLMProvider, UsageRecord
from .modes import LECTURE, NoteMode
from .transcript import Block, format_blocks

log = logging.getLogger(__name__)


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


def _user_message(
    title: str,
    transcript_text: str,
    has_timestamps: bool,
    part: tuple[int, int] | None,
    language: str | None,
) -> str:
    header = [f"Nazwa pliku: {title}"]
    if language:
        header.append(f"Wykryty język nagrania: {language}")
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
    for value in notes.values():
        if not isinstance(value, list):
            continue
        for item in value:
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


def empty_notes(mode: NoteMode = LECTURE) -> dict[str, Any]:
    return {
        key: "" if spec.get("type") == "string" else []
        for key, spec in mode.schema["properties"].items()
    }


def generate_notes(
    provider: LLMProvider,
    title: str,
    blocks: list[Block],
    has_timestamps: bool,
    duration: float | None,
    max_chars: int,
    mode: NoteMode = LECTURE,
    language: str | None = None,
) -> NotesResult:
    parts = split_blocks(blocks, max_chars)
    usage: list[UsageRecord] = []

    if len(parts) == 1:
        resp = provider.generate_json(
            mode.system_prompt,
            _user_message(title, format_blocks(parts[0]), has_timestamps, None, language),
            mode.schema,
        )
        usage += resp.usage
        notes = resp.data
    else:
        log.info("Transcript split into %d parts", len(parts))
        partial = []
        for i, part in enumerate(parts, 1):
            resp = provider.generate_json(
                mode.system_prompt,
                _user_message(title, format_blocks(part), has_timestamps, (i, len(parts)), language),
                mode.schema,
            )
            usage += resp.usage
            partial.append(resp.data)
        merge_input = "\n\n".join(
            f"<czesc numer=\"{i}\">\n{json.dumps(p, ensure_ascii=False)}\n</czesc>"
            for i, p in enumerate(partial, 1)
        )
        resp = provider.generate_json(mode.merge_prompt, f"Plik: {title}\n\n{merge_input}", mode.schema)
        usage += resp.usage
        notes = resp.data

    notes = {**empty_notes(mode), **notes}
    notes = sanitize_timestamps(notes, has_timestamps, duration)
    return NotesResult(notes=notes, usage=usage, parts=len(parts))
