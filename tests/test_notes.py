import json

import pytest
from conftest import SAMPLE_GENERAL_NOTES, SAMPLE_NOTES, FakeProvider

from lecture_notes.modes import GENERAL, LECTURE, MODES
from lecture_notes.notes import empty_notes, generate_notes, sanitize_timestamps, split_blocks
from lecture_notes.transcript import Block


def _blocks(n, with_ts=True, size=100):
    return [Block("x" * size, i * 45.0 if with_ts else None) for i in range(n)]


@pytest.mark.parametrize("mode", MODES.values(), ids=list(MODES))
def test_schema_is_strict_and_matches_sections(mode):
    def check(node):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for child in node["properties"].values():
                check(child)
        if node.get("type") == "array":
            check(node["items"])
    check(mode.schema)
    assert [s.key for s in mode.sections] == list(mode.schema["properties"])


def test_modes_differ_where_expected():
    assert "exam_items" in LECTURE.schema["properties"]
    assert "exam_items" not in GENERAL.schema["properties"]
    assert {"takeaways", "supplements"} <= set(GENERAL.schema["properties"])
    assert "WYŁĄCZNIE" in GENERAL.system_prompt and "supplements" in GENERAL.system_prompt
    assert "po polsku" in GENERAL.system_prompt
    assert LECTURE.quick_action == "Zrób notatki"
    assert GENERAL.quick_action == "Zrób notatki (dowolny temat)"


def test_empty_notes_per_mode():
    assert empty_notes(GENERAL) == {
        "summary": "", "topics": [], "definitions": [], "takeaways": [], "formulas": [],
        "review_questions": [], "supplements": [], "transcript_issues": [],
    }
    assert "exam_items" in empty_notes(LECTURE)


def test_general_mode_uses_its_prompt_schema_and_language():
    provider = FakeProvider(responses=[json.loads(json.dumps(SAMPLE_GENERAL_NOTES))])
    result = generate_notes(provider, "podcast.mp3", _blocks(2), True, 200.0, 10_000,
                            mode=GENERAL, language="en")
    call = provider.calls[0]
    assert call["system"] == GENERAL.system_prompt
    assert call["schema"] is GENERAL.schema
    assert "Wykryty język nagrania: en" in call["user"]
    assert result.notes["supplements"][0]["title"] == "Kontekst"
    assert result.notes["takeaways"][0]["timestamp"] == "00:00:45"


def test_general_mode_merge_uses_general_merge_prompt():
    provider = FakeProvider(responses=[json.loads(json.dumps(SAMPLE_GENERAL_NOTES)) for _ in range(10)])
    generate_notes(provider, "film.mp4", _blocks(10), True, 1000.0, 350, mode=GENERAL)
    assert provider.calls[-1]["system"] == GENERAL.merge_prompt


def test_split_blocks_respects_limit_and_order():
    blocks = _blocks(10, size=100)
    parts = split_blocks(blocks, max_chars=350)
    assert [b for p in parts for b in p] == blocks
    assert all(sum(len(b.text) + 12 for b in p) <= 350 for p in parts)
    assert len(split_blocks(blocks, max_chars=10_000)) == 1


def test_single_request_when_short(fake_provider):
    result = generate_notes(fake_provider, "wyklad.m4a", _blocks(3), True, 200.0, 10_000)
    assert len(fake_provider.calls) == 1
    assert result.parts == 1
    assert "[00:00:45]" in fake_provider.calls[0]["user"]
    assert result.notes["summary"] == SAMPLE_NOTES["summary"]
    assert len(result.usage) == 1


def test_long_transcript_is_split_and_merged():
    provider = FakeProvider()
    result = generate_notes(provider, "wyklad.m4a", _blocks(10, size=100), True, 1000.0, 350)
    n_parts = result.parts
    assert n_parts > 1
    assert len(provider.calls) == n_parts + 1  # parts + merge
    assert "część 1 z" in provider.calls[0]["user"]
    merge_call = provider.calls[-1]
    assert "Połącz" in merge_call["system"]
    # merge input carries the partial JSON results
    assert json.dumps(SAMPLE_NOTES["summary"], ensure_ascii=False) in merge_call["user"]
    assert len(result.usage) == n_parts + 1


def test_without_timestamps_prompt_says_so_and_stamps_are_dropped(fake_provider):
    result = generate_notes(fake_provider, "notatki.txt", _blocks(2, with_ts=False), False, None, 10_000)
    user = fake_provider.calls[0]["user"]
    assert "NIE ma znaczników czasu" in user
    assert "[" not in user.split("<transkrypcja>")[1]
    for value in result.notes.values():
        for item in value if isinstance(value, list) else []:
            if isinstance(item, dict):
                assert item["timestamp"] == ""


def test_sanitize_timestamps():
    notes = {
        "topics": [
            {"title": "a", "timestamp": "[0:01:05]", "points": []},
            {"title": "b", "timestamp": "02:00:00", "points": []},  # beyond duration
            {"title": "c", "timestamp": "około minuty", "points": []},
            {"title": "d", "timestamp": "00:61:00", "points": []},
        ],
        "review_questions": ["Pytanie?"],
    }
    out = sanitize_timestamps(notes, True, duration=600.0)
    assert [t["timestamp"] for t in out["topics"]] == ["00:01:05", "", "", ""]
    assert out["review_questions"] == ["Pytanie?"]


def test_missing_sections_are_filled():
    provider = FakeProvider(responses=[{"summary": "Tylko streszczenie."}])
    result = generate_notes(provider, "w.srt", _blocks(1), True, 100.0, 10_000)
    assert result.notes["definitions"] == []
    assert result.notes["summary"] == "Tylko streszczenie."
