from src.models import Segment
from src.summarize import chunk_transcript


def test_empty_input_returns_empty_list():
    assert chunk_transcript([]) == []


def test_splits_when_exceeding_max_chars():
    segs = [Segment(i, i + 1, "word " * 100) for i in range(10)]
    chunks = chunk_transcript(segs, max_chars=600)
    assert len(chunks) > 1
    assert all(len(c) <= 700 for c in chunks)  # allow one segment of slack


def test_single_short_transcript_is_one_chunk():
    segs = [Segment(0, 1, "hello"), Segment(1, 2, "world")]
    chunks = chunk_transcript(segs, max_chars=6000)
    assert chunks == ["hello world"]


def test_blank_segments_are_skipped():
    segs = [Segment(0, 1, "  "), Segment(1, 2, "real")]
    assert chunk_transcript(segs) == ["real"]
