"""Speech-to-text with mlx-whisper (Apple Silicon)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .transcript import Segment, Transcript, remove_loops

log = logging.getLogger(__name__)


def transcribe(audio_path: Path, whisper_cfg: dict[str, Any]) -> Transcript:
    # Imported lazily: loading MLX takes a moment and is not needed for .txt/.srt input.
    import mlx_whisper

    silence = float(whisper_cfg.get("hallucination_silence_threshold") or 0)
    kwargs: dict[str, Any] = dict(
        path_or_hf_repo=whisper_cfg["model"],
        language=whisper_cfg.get("language") or None,
        initial_prompt=whisper_cfg.get("initial_prompt") or None,
        condition_on_previous_text=bool(whisper_cfg.get("condition_on_previous_text", False)),
        compression_ratio_threshold=whisper_cfg.get("compression_ratio_threshold", 2.4),
        logprob_threshold=whisper_cfg.get("logprob_threshold", -1.0),
        no_speech_threshold=whisper_cfg.get("no_speech_threshold", 0.6),
        # temperature fallback: re-decode a window with higher temperature when
        # it fails the compression/logprob checks (typical loop symptom)
        temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        verbose=None,
    )
    if silence > 0:
        kwargs["word_timestamps"] = True
        kwargs["hallucination_silence_threshold"] = silence

    log.info("Transcribing %s with %s", audio_path.name, whisper_cfg["model"])
    result = mlx_whisper.transcribe(str(audio_path), **kwargs)

    raw = [
        Segment(str(s.get("text", "")).strip(), float(s["start"]), float(s["end"]))
        for s in result.get("segments", [])
    ]
    segments = remove_loops(raw)
    log.info("Whisper segments: %d raw, %d after loop removal", len(raw), len(segments))
    return Transcript(segments)
