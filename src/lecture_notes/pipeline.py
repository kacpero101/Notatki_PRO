"""End-to-end processing of one input file."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from .cost import format_cost, total_cost
from .docx_builder import DocumentMeta, save_document
from .llm import LLMProvider, create_provider
from .notes import generate_notes
from .paths import MEDIA_EXTENSIONS, TRANSCRIPT_EXTENSIONS, notes_path_for, transcript_paths_for
from .transcript import Transcript, load_transcript, merge_into_blocks, to_plain_text, to_srt

log = logging.getLogger(__name__)


class UserError(RuntimeError):
    """Expected problem with a short message suitable for a notification."""


@dataclass
class ProcessResult:
    notes_path: Path
    cost: float | None
    cost_text: str
    transcript_paths: tuple[Path, Path] | None = None


def recording_date(path: Path, ffprobe: str | None) -> date:
    """Creation date from media metadata if available, else the file's birth time."""
    if ffprobe and path.suffix.lower() in MEDIA_EXTENSIONS:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "quiet", "-print_format", "json", "-show_entries", "format_tags", str(path)],
                capture_output=True, text=True, timeout=20, check=False,
            ).stdout
            tags = {k.lower(): v for k, v in json.loads(out or "{}").get("format", {}).get("tags", {}).items()}
            for key in ("com.apple.quicktime.creationdate", "creation_time", "date"):
                if key in tags:
                    value = tags[key].replace("Z", "+00:00")
                    try:
                        dt = datetime.fromisoformat(value)
                        return dt.astimezone().date() if dt.tzinfo else dt.date()
                    except ValueError:
                        continue
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
            log.debug("ffprobe failed: %s", e)
    st = path.stat()
    return datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_mtime)).date()


def _transcribe(path: Path, config: dict[str, Any]) -> Transcript:
    from .transcribe import transcribe  # lazy: MLX import is slow

    return transcribe(path, config["whisper"])


def process_file(
    path: Path,
    config: dict[str, Any],
    provider_factory: Callable[[dict[str, Any]], LLMProvider] | None = None,
    transcriber: Callable[[Path, dict[str, Any]], Transcript] | None = None,
) -> ProcessResult:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise UserError(f"Nie znaleziono pliku: {path.name}")
    ext = path.suffix.lower()
    if ext not in MEDIA_EXTENSIONS | TRANSCRIPT_EXTENSIONS:
        raise UserError(f"Nieobsługiwany format pliku: {path.name}")

    # fail fast (e.g. missing API key) before a long transcription
    provider = (provider_factory or create_provider)(config["llm"])

    transcript_paths = None
    if ext in MEDIA_EXTENSIONS:
        transcript = (transcriber or _transcribe)(path, config)
        if not transcript.segments:
            raise UserError(f"Nie rozpoznano mowy w nagraniu: {path.name}")
        txt_path, srt_path = transcript_paths_for(path)
        txt_path.write_text(to_plain_text(transcript), encoding="utf-8")
        srt_path.write_text(to_srt(transcript), encoding="utf-8")
        transcript_paths = (txt_path, srt_path)
        log.info("Transcript saved: %s, %s", txt_path.name, srt_path.name)
    else:
        transcript = load_transcript(path)
        if not transcript.segments:
            raise UserError(f"Pusta transkrypcja: {path.name}")

    tcfg = config.get("transcript", {})
    blocks = merge_into_blocks(
        transcript, tcfg.get("block_min_seconds", 30), tcfg.get("block_max_seconds", 60)
    )
    result = generate_notes(
        provider,
        title=path.name,
        blocks=blocks,
        has_timestamps=transcript.has_timestamps,
        duration=transcript.duration,
        max_chars=int(config["llm"].get("max_transcript_chars_per_request", 250_000)),
    )

    cost = total_cost(result.usage, config.get("pricing", {}))
    cost_text = format_cost(cost)
    models = sorted({u.model for u in result.usage}) or [provider.model]
    meta = DocumentMeta(
        title=path.name,
        recorded=recording_date(path, config.get("paths", {}).get("ffprobe")),
        model=", ".join(models),
        cost=cost_text,
        generated=datetime.now(),
        source_name=path.name,
    )
    notes_path = save_document(result.notes, meta, notes_path_for(path))
    tokens_in = sum(u.input_tokens for u in result.usage)
    tokens_out = sum(u.output_tokens for u in result.usage)
    log.info(
        "Notes saved: %s (parts=%d, input_tokens=%d, output_tokens=%d, cost=%s)",
        notes_path.name, result.parts, tokens_in, tokens_out, cost_text,
    )
    return ProcessResult(notes_path, cost, cost_text, transcript_paths)
