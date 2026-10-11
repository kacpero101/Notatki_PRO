"""Transcript model: parsing/writing .txt and .srt, loop removal, block merging."""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Segment:
    text: str
    start: float | None = None  # seconds; None when the source has no timestamps
    end: float | None = None


@dataclass
class Transcript:
    segments: list[Segment] = field(default_factory=list)

    @property
    def has_timestamps(self) -> bool:
        return bool(self.segments) and all(s.start is not None for s in self.segments)

    @property
    def duration(self) -> float | None:
        ends = [s.end for s in self.segments if s.end is not None]
        return max(ends) if ends else None

    def plain_text(self) -> str:
        return "\n".join(s.text for s in self.segments if s.text)


# ---------------------------------------------------------------- timestamps

def format_hms(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def format_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


_SRT_TIME = r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
_SRT_RANGE = re.compile(rf"{_SRT_TIME}\s*-->\s*{_SRT_TIME}")


def _srt_seconds(h: str, m: str, s: str, frac: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(frac.ljust(3, "0")) / 1000


# ------------------------------------------------------------------- parsing

def parse_srt(content: str) -> Transcript:
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        for i, line in enumerate(lines):
            match = _SRT_RANGE.search(line)
            if match:
                g = match.groups()
                text = " ".join(lines[i + 1:])
                text = re.sub(r"<[^>]+>", "", text).strip()  # drop <i> etc.
                if text:
                    segments.append(Segment(text, _srt_seconds(*g[:4]), _srt_seconds(*g[4:])))
                break
    return Transcript(segments)


# "[00:12:30] text" or "00:12:30 text" or "[12:30] text" at the start of a line
_TXT_STAMP = re.compile(r"^\[?(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\]?\s+(.*)$")


def parse_txt(content: str) -> Transcript:
    """Plain text transcript. Lines starting with a timestamp keep it; otherwise
    the transcript has no timestamps and is split into paragraphs."""
    content = content.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in content.split("\n")]
    non_empty = [ln for ln in lines if ln]
    matches = [_TXT_STAMP.match(ln) for ln in non_empty]
    if matches and sum(1 for m in matches if m) >= max(1, len(matches) // 2):
        segments: list[Segment] = []
        for line, m in zip(non_empty, matches):
            if m:
                h, mnt, s, text = m.groups()
                start = int(h or 0) * 3600 + int(mnt) * 60 + int(s)
                segments.append(Segment(text.strip(), float(start)))
            elif segments:  # continuation line belongs to the previous stamp
                segments[-1].text += " " + line
        for seg, nxt in zip(segments, segments[1:]):
            seg.end = nxt.start
        if segments:
            segments[-1].end = segments[-1].start
        return Transcript(segments)

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    if len(paragraphs) <= 1:
        # one big blob: split into sentences-ish lines so it can be chunked
        paragraphs = non_empty
    return Transcript([Segment(" ".join(p.split())) for p in paragraphs])


def load_transcript(path: Path) -> Transcript:
    content = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() == ".srt":
        return parse_srt(content)
    return parse_txt(content)


# ------------------------------------------------------------------- writing

def to_srt(transcript: Transcript) -> str:
    out = []
    for i, seg in enumerate(transcript.segments, 1):
        start = seg.start or 0.0
        end = seg.end if seg.end is not None else start
        out.append(f"{i}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{seg.text}\n")
    return "\n".join(out)


def to_plain_text(transcript: Transcript) -> str:
    return transcript.plain_text() + "\n"


# -------------------------------------------------------------- loop removal

# Phrases Whisper is known to hallucinate on Polish silence/noise (subtitle credits
# learned from training data). Matched against the whole normalised segment.
_HALLUCINATION_PATTERNS = [
    re.compile(p)
    for p in (
        r"^napisy (wykonane|stworzone|przygotowane|zrobione) .*$",
        r".*amara\.org.*",
        r"^(subskrybuj|zasubskrybuj)( kanał)?( i zostaw (łapkę|like))?\.?$",
        r"^(transkrypcja|tłumaczenie|korekta) .*(napisy|amara).*$",
    )
]


def _normalise(text: str) -> str:
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def collapse_repeats(text: str, max_repeats: int = 2) -> str:
    """Collapse a phrase (1–12 words) repeated more than ``max_repeats`` times in a
    row to a single occurrence ("tak tak tak tak" -> "tak")."""
    words = text.split()
    if len(words) < max_repeats + 1:
        return text
    changed = True
    while changed:
        changed = False
        for n in range(1, min(12, len(words) // (max_repeats + 1)) + 1):
            i = 0
            result: list[str] = []
            while i < len(words):
                unit = [_normalise(w) for w in words[i:i + n]]
                count = 1
                while [_normalise(w) for w in words[i + count * n:i + (count + 1) * n]] == unit:
                    count += 1
                if count > max_repeats and len(unit) == n:
                    result.extend(words[i:i + n])
                    i += count * n
                    changed = True
                else:
                    result.append(words[i])
                    i += 1
            words = result
    return " ".join(words)


def _compression_ratio(text: str) -> float:
    data = text.encode("utf-8")
    return len(data) / len(zlib.compress(data)) if data else 0.0


def remove_loops(
    segments: list[Segment],
    window: int = 3,
    compression_ratio_limit: float = 3.0,
) -> list[Segment]:
    """Remove typical Whisper hallucination loops.

    * collapses phrases repeated within a segment,
    * drops a segment whose text already appeared in the last ``window`` kept
      segments (catches "A A A" and "A B A B" loops),
    * drops known subtitle-credit hallucinations,
    * drops segments that are still extremely repetitive (high gzip ratio).
    """
    cleaned: list[Segment] = []
    for seg in segments:
        text = collapse_repeats(" ".join(seg.text.split()))
        norm = _normalise(text)
        if not norm:
            continue
        if any(p.match(norm) for p in _HALLUCINATION_PATTERNS):
            continue
        if len(text) > 40 and _compression_ratio(text) > compression_ratio_limit:
            continue
        if norm in (_normalise(s.text) for s in cleaned[-window:]):
            if seg.end is not None and cleaned[-1].end is not None:
                cleaned[-1].end = max(cleaned[-1].end, seg.end)
            continue
        cleaned.append(Segment(text, seg.start, seg.end))
    return cleaned


# ------------------------------------------------------------ block merging

@dataclass
class Block:
    text: str
    start: float | None


def merge_into_blocks(
    transcript: Transcript, min_seconds: float = 30, max_seconds: float = 60,
    max_chars_without_timestamps: int = 900,
) -> list[Block]:
    """Merge segments into ~30–60 s blocks. A block is closed once it is at least
    ``min_seconds`` long and the segment ends a sentence, or when adding the next
    segment would exceed ``max_seconds``. Without timestamps, blocks are built by
    length instead."""
    blocks: list[Block] = []
    current: list[Segment] = []

    def flush() -> None:
        if current:
            blocks.append(Block(" ".join(s.text for s in current), current[0].start))
            current.clear()

    if not transcript.has_timestamps:
        size = 0
        for seg in transcript.segments:
            if current and size + len(seg.text) > max_chars_without_timestamps:
                flush()
                size = 0
            current.append(seg)
            size += len(seg.text) + 1
        flush()
        return blocks

    for seg in transcript.segments:
        if current:
            block_start = current[0].start
            seg_end = seg.end if seg.end is not None else seg.start
            if seg_end - block_start > max_seconds:
                flush()
        current.append(seg)
        block_start = current[0].start
        end = seg.end if seg.end is not None else seg.start
        if end - block_start >= min_seconds and seg.text.rstrip().endswith((".", "?", "!", "…")):
            flush()
    flush()
    return blocks


def format_blocks(blocks: list[Block]) -> str:
    lines = []
    for b in blocks:
        prefix = f"[{format_hms(b.start)}] " if b.start is not None else ""
        lines.append(prefix + b.text)
    return "\n".join(lines)
