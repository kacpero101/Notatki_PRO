"""File naming helpers: never overwrite existing files."""

from __future__ import annotations

from pathlib import Path

MEDIA_EXTENSIONS = {
    ".m4a", ".mp3", ".wav", ".aac", ".aif", ".aiff", ".flac", ".ogg", ".opus", ".oga",
    ".wma", ".amr", ".caf", ".webm", ".mp4", ".m4v", ".mkv", ".mov", ".avi", ".wmv",
    ".flv", ".mpg", ".mpeg", ".3gp", ".ts",
}
TRANSCRIPT_EXTENSIONS = {".txt", ".srt"}

NOTES_SUFFIX = " – notatki"


def unique_path(path: Path) -> Path:
    """``path`` if free, otherwise ``name (2).ext``, ``name (3).ext``, ..."""
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def notes_path_for(source: Path) -> Path:
    return unique_path(source.with_name(f"{source.stem}{NOTES_SUFFIX}.docx"))


def transcript_paths_for(source: Path) -> tuple[Path, Path]:
    return unique_path(source.with_suffix(".txt")), unique_path(source.with_suffix(".srt"))
