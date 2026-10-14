"""End-to-end: synthetic recording -> real mlx-whisper -> fake LLM -> .docx.

Run with:  pytest -m e2e
Needs macOS `say` with the voices "Zosia" (Polish lecture) and "Daniel" (English,
"any topic" mode with language detection), ffmpeg and the Whisper model
(downloaded on first use). No API calls are made.
"""

import shutil
import subprocess

import pytest
from conftest import SAMPLE_GENERAL_NOTES, FakeProvider
from docx import Document

from lecture_notes.cli import _prepare_environment
from lecture_notes.config import load_config
from lecture_notes.modes import GENERAL
from lecture_notes.pipeline import process_file

pytestmark = pytest.mark.e2e

LECTURE = (
    "Dzień dobry państwu. Dzisiaj omówimy pochodną funkcji. "
    "Pochodna funkcji f od x równa x do kwadratu plus jeden wynosi dwa x. "
    "Proszę to zapamiętać, to będzie na kolokwium."
)

PODCAST = (
    "Welcome to the show. Today we talk about reinforcement learning. "
    "An agent takes actions in an environment and receives a reward. "
    "The goal is to learn a policy that maximizes the total reward."
)


def _voice_available(name: str) -> bool:
    if not shutil.which("say"):
        return False
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return any(line.split()[0] == name for line in voices.splitlines() if line.strip())


def _say(voice: str, text: str, path) -> None:
    subprocess.run(
        ["say", "-v", voice, "-o", str(path), "--file-format=m4af", "--data-format=aac", text], check=True
    )


@pytest.mark.skipif(not _voice_available("Zosia"), reason="macOS voice Zosia not available")
def test_recording_to_docx(tmp_path, monkeypatch):
    monkeypatch.setenv("LECTURE_NOTES_CONFIG", str(tmp_path / "none.toml"))
    config = load_config()
    _prepare_environment(config)
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")

    recording = tmp_path / "Wykład testowy.m4a"
    _say("Zosia", LECTURE, recording)

    provider = FakeProvider()
    result = process_file(recording, config, provider_factory=lambda cfg: provider)

    txt, srt = result.transcript_paths
    text = txt.read_text(encoding="utf-8").lower()
    assert "pochodn" in text and "kolokwium" in text
    assert "-->" in srt.read_text(encoding="utf-8")
    sent = provider.calls[0]["user"]
    assert "[00:00:00]" in sent and "kolokwium" in sent.lower()
    assert Document(str(result.notes_path)).paragraphs[0].text == recording.name


@pytest.mark.skipif(not _voice_available("Daniel"), reason="macOS voice Daniel not available")
def test_general_mode_detects_english(tmp_path, monkeypatch):
    monkeypatch.setenv("LECTURE_NOTES_CONFIG", str(tmp_path / "none.toml"))
    config = load_config()
    _prepare_environment(config)
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")

    recording = tmp_path / "Podcast.m4a"
    _say("Daniel", PODCAST, recording)

    provider = FakeProvider(responses=[dict(SAMPLE_GENERAL_NOTES)])
    result = process_file(recording, config, provider_factory=lambda cfg: provider, mode=GENERAL)

    text = result.transcript_paths[0].read_text(encoding="utf-8").lower()
    assert "reinforcement learning" in text and "reward" in text
    assert "Wykryty język nagrania: en" in provider.calls[0]["user"]
    assert provider.calls[0]["system"] == GENERAL.system_prompt
