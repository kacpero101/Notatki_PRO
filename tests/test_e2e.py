"""End-to-end: synthetic Polish recording -> real mlx-whisper -> fake LLM -> .docx.

Run with:  pytest -m e2e
Needs macOS `say` with the Polish voice "Zosia", ffmpeg and the Whisper model
(downloaded on first use). No API calls are made.
"""

import shutil
import subprocess

import pytest
from conftest import FakeProvider
from docx import Document

from lecture_notes.cli import _prepare_environment
from lecture_notes.config import load_config
from lecture_notes.pipeline import process_file

pytestmark = pytest.mark.e2e

LECTURE = (
    "Dzień dobry państwu. Dzisiaj omówimy pochodną funkcji. "
    "Pochodna funkcji f od x równa x do kwadratu plus jeden wynosi dwa x. "
    "Proszę to zapamiętać, to będzie na kolokwium."
)


def _zosia_available() -> bool:
    if not shutil.which("say"):
        return False
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return "Zosia" in voices


@pytest.mark.skipif(not _zosia_available(), reason="macOS voice Zosia not available")
def test_recording_to_docx(tmp_path, monkeypatch):
    monkeypatch.setenv("LECTURE_NOTES_CONFIG", str(tmp_path / "none.toml"))
    config = load_config()
    _prepare_environment(config)
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")

    recording = tmp_path / "Wykład testowy.m4a"
    subprocess.run(
        ["say", "-v", "Zosia", "-o", str(recording), "--file-format=m4af", "--data-format=aac", LECTURE],
        check=True,
    )

    provider = FakeProvider()
    result = process_file(recording, config, provider_factory=lambda cfg: provider)

    txt, srt = result.transcript_paths
    text = txt.read_text(encoding="utf-8").lower()
    assert "pochodn" in text and "kolokwium" in text
    assert "-->" in srt.read_text(encoding="utf-8")
    sent = provider.calls[0]["user"]
    assert "[00:00:00]" in sent and "kolokwium" in sent.lower()
    assert Document(str(result.notes_path)).paragraphs[0].text == recording.name
