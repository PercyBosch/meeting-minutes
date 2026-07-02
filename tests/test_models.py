from src.models import Segment, ActionItem, Minutes


def test_minutes_round_trips_through_dict():
    m = Minutes(
        title="Weekly Sync",
        date="2026-07-02",
        attendees=["Percy", "Stefan"],
        summary="Discussed the launch.",
        key_points=["Launch on track", "Costs discussed"],
        decisions=["Ship on Friday"],
        action_items=[ActionItem(task="Write release notes", owner="Percy", due="Thu")],
        topics=["Launch", "Testing"],
        next_steps=["Prepare rollback plan"],
    )
    restored = Minutes.from_dict(m.to_dict())
    assert restored == m
    assert restored.action_items[0].owner == "Percy"
    assert restored.key_points == ["Launch on track", "Costs discussed"]


def test_segment_defaults_speaker_to_none():
    s = Segment(start=0.0, end=1.5, text="hello")
    assert s.speaker is None
