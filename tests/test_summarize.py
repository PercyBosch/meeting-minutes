import json

import pytest

from src import summarize as summ
from src.config import Config
from src.models import Segment
from src.summarize import summarize, parse_json, SummarizeError


REDUCE_RESULT = {
    "summary": "We agreed to ship Friday.",
    "key_points": ["Launch is on track", "Costs were raised"],
    "decisions": ["Ship Friday"],
    "action_items": [{"task": "Write notes", "owner": "Percy", "due": "Thu"}],
    "topics": ["Launch"],
    "next_steps": ["Prepare rollback"],
}


def test_parse_json_extracts_object_from_noisy_text():
    raw = "Sure! Here is the JSON:\n{\"summary\": \"hi\"}\nHope that helps."
    assert parse_json(raw) == {"summary": "hi"}


def test_parse_json_raises_without_object():
    with pytest.raises(SummarizeError):
        parse_json("no json here")


def test_summarize_builds_minutes_from_llm(monkeypatch):
    cfg = Config(raw={"summarize": {"provider": "ollama", "chunk_chars": 50}})
    # Map calls return plain notes; the final (reduce) call returns JSON.
    call_count = {"n": 0}

    def fake_llm(prompt):
        call_count["n"] += 1
        if "Return ONLY valid JSON" in prompt:
            return json.dumps(REDUCE_RESULT)
        return "note about the meeting"

    monkeypatch.setattr(summ, "get_llm", lambda cfg: fake_llm)
    segs = [Segment(i, i + 1, "word " * 20) for i in range(6)]
    minutes = summarize(segs, "Sync", "2026-07-02", ["Percy"], cfg)

    assert minutes.title == "Sync"
    assert minutes.summary == "We agreed to ship Friday."
    assert minutes.key_points == ["Launch is on track", "Costs were raised"]
    assert minutes.action_items[0].owner == "Percy"
    assert call_count["n"] >= 2  # at least one map + one reduce


def test_summarize_empty_transcript_raises():
    cfg = Config(raw={"summarize": {"provider": "ollama"}})
    with pytest.raises(SummarizeError):
        summarize([], "Sync", "2026-07-02", [], cfg)


def test_get_llm_unknown_provider_raises():
    cfg = Config(raw={"summarize": {"provider": "nope"}})
    with pytest.raises(SummarizeError):
        summ.get_llm(cfg)
