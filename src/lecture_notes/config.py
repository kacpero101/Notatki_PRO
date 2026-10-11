"""Configuration: bundled config.example.toml overlaid with the user's config.toml."""

from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "lecture-notes"
CONFIG_PATH = CONFIG_DIR / "config.toml"
LOG_DIR = Path.home() / "Library" / "Logs" / "lecture-notes"


def example_config_text() -> str:
    bundled = resources.files("lecture_notes").joinpath("config.example.toml")
    if bundled.is_file():
        return bundled.read_text(encoding="utf-8")
    # editable/development install: file lives in the repository root
    return (Path(__file__).resolve().parents[2] / "config.example.toml").read_text(encoding="utf-8")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    config = tomllib.loads(example_config_text())
    path = path or Path(os.environ.get("LECTURE_NOTES_CONFIG", CONFIG_PATH))
    if path.is_file():
        with path.open("rb") as f:
            config = _deep_merge(config, tomllib.load(f))
    return config


def write_default_config(path: Path = CONFIG_PATH) -> bool:
    """Create the user config from the example. Returns False if it already exists."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(example_config_text(), encoding="utf-8")
    return True
