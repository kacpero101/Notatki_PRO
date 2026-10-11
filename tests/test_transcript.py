from lecture_notes.transcript import (
    Segment,
    Transcript,
    collapse_repeats,
    format_blocks,
    format_hms,
    format_srt_time,
    merge_into_blocks,
    parse_srt,
    parse_txt,
    remove_loops,
    to_srt,
)

SRT = """﻿1
00:00:01,000 --> 00:00:04,500
Dzień dobry, zaczynamy wykład.

2
00:00:04,500 --> 00:00:09,250
Dziś omówimy <i>grafy</i>
i drzewa rozpinające.

3
01:02:03.400 --> 01:02:05.000
Koniec.
"""


def test_parse_srt_basic():
    t = parse_srt(SRT)
    assert len(t.segments) == 3
    assert t.segments[0].start == 1.0
    assert t.segments[0].end == 4.5
    assert t.segments[1].text == "Dziś omówimy grafy i drzewa rozpinające."
    assert t.segments[2].start == 3723.4
    assert t.has_timestamps


def test_parse_srt_crlf_and_garbage():
    content = "1\r\n00:00:00,000 --> 00:00:01,000\r\nRaz\r\n\r\nnot a block\r\n\r\n"
    t = parse_srt(content)
    assert [s.text for s in t.segments] == ["Raz"]


def test_srt_roundtrip():
    t = parse_srt(SRT)
    again = parse_srt(to_srt(t))
    assert [(s.text, s.start, s.end) for s in again.segments] == [
        (s.text, s.start, s.end) for s in t.segments
    ]


def test_time_formatting():
    assert format_hms(3725.9) == "01:02:05"
    assert format_srt_time(3725.25) == "01:02:05,250"
    assert format_srt_time(0) == "00:00:00,000"


def test_parse_txt_without_timestamps():
    t = parse_txt("Pierwszy akapit\nciąg dalszy.\n\nDrugi akapit.")
    assert not t.has_timestamps
    assert [s.text for s in t.segments] == ["Pierwszy akapit ciąg dalszy.", "Drugi akapit."]
    assert all(s.start is None for s in t.segments)


def test_parse_txt_with_timestamps_and_continuation():
    t = parse_txt("[00:00:05] Wstęp.\nciąg dalszy\n[00:01:10] Definicja grafu.\n12:30 Krótki stempel.")
    assert t.has_timestamps
    assert [s.start for s in t.segments] == [5.0, 70.0, 750.0]
    assert t.segments[0].text == "Wstęp. ciąg dalszy"
    assert t.segments[0].end == 70.0


def test_collapse_repeats_single_word_and_phrase():
    assert collapse_repeats("tak tak tak tak tak") == "tak"
    assert collapse_repeats("i to jest to i to jest to i to jest to koniec") == "i to jest to koniec"
    # two repetitions are normal speech and must stay
    assert collapse_repeats("bardzo bardzo ważne") == "bardzo bardzo ważne"


def test_remove_loops_consecutive_and_alternating():
    segs = [
        Segment("Zaczynamy.", 0, 2),
        Segment("Dziękuję.", 2, 4),
        Segment("Dziękuję.", 4, 6),
        Segment("Dziękuję!", 6, 8),
        Segment("A to drugie.", 8, 9),
        Segment("B to trzecie.", 9, 10),
        Segment("A to drugie.", 10, 11),
        Segment("B to trzecie.", 11, 12),
        Segment("Nowa myśl.", 12, 14),
    ]
    out = remove_loops(segs)
    assert [s.text for s in out] == [
        "Zaczynamy.", "Dziękuję.", "A to drugie.", "B to trzecie.", "Nowa myśl.",
    ]
    assert out[1].end == 8  # dropped duplicates extend the kept segment


def test_remove_loops_known_hallucinations_and_inner_repeats():
    segs = [
        Segment("Napisy stworzone przez społeczność Amara.org", 0, 3),
        Segment("Subskrybuj!", 3, 4),
        Segment("no no no no no no no no dobrze", 4, 8),
        Segment("", 8, 9),
    ]
    out = remove_loops(segs)
    assert [s.text for s in out] == ["no dobrze"]


def test_remove_loops_keeps_legit_repeat_far_apart():
    segs = [Segment(f"Zdanie {i}.", i, i + 1) for i in range(5)] + [Segment("Zdanie 0.", 5, 6)]
    assert len(remove_loops(segs)) == 6


def test_merge_into_blocks_respects_bounds():
    segs = [Segment(f"Zdanie {i}.", i * 10.0, i * 10.0 + 10) for i in range(12)]  # 120 s
    blocks = merge_into_blocks(Transcript(segs), 30, 60)
    assert blocks[0].start == 0.0
    for b, nxt in zip(blocks, blocks[1:]):
        assert nxt.start - b.start <= 60
    assert " ".join(b.text for b in blocks) == " ".join(s.text for s in segs)


def test_merge_into_blocks_waits_for_sentence_end_but_caps_at_max():
    segs = [Segment(f"słowo{i}", i * 10.0, i * 10.0 + 10) for i in range(9)]  # no punctuation
    blocks = merge_into_blocks(Transcript(segs), 30, 60)
    assert [b.start for b in blocks] == [0.0, 60.0]


def test_merge_without_timestamps_by_length():
    segs = [Segment("x" * 400) for _ in range(5)]
    blocks = merge_into_blocks(Transcript(segs), max_chars_without_timestamps=900)
    assert len(blocks) == 3
    assert all(b.start is None for b in blocks)
    assert not format_blocks(blocks).startswith("[")


def test_format_blocks():
    from lecture_notes.transcript import Block
    assert format_blocks([Block("Ala", 0.0), Block("ma kota", 75.0)]) == "[00:00:00] Ala\n[00:01:15] ma kota"
