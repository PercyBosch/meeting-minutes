from src.models import Minutes, ActionItem
from src.store import save_meeting, list_meetings, load_meeting


def _minutes() -> Minutes:
    return Minutes(
        title="Sync",
        date="2026-07-02",
        attendees=["Percy"],
        summary="s",
        decisions=["d"],
        action_items=[ActionItem(task="t", owner="Percy")],
        topics=["x"],
        next_steps=["n"],
    )


def test_save_then_load_round_trips(tmp_path):
    docx = tmp_path / "src.docx"
    docx.write_bytes(b"docx-bytes")
    mid = save_meeting(
        str(tmp_path / "meetings"), "Sync", "2026-07-02", _minutes(), "hello transcript",
        {"docx": str(docx)},
    )

    meta, minutes = load_meeting(str(tmp_path / "meetings"), mid)
    assert meta["title"] == "Sync"
    assert minutes.action_items[0].owner == "Percy"
    assert "docx" in meta["files"]


def test_list_meetings_returns_saved_entries(tmp_path):
    base = str(tmp_path / "meetings")
    save_meeting(base, "A", "2026-07-01", _minutes(), "t", {})
    save_meeting(base, "B", "2026-07-02", _minutes(), "t", {})
    titles = [m["title"] for m in list_meetings(base)]
    assert set(titles) == {"A", "B"}


def test_list_meetings_empty_when_no_dir(tmp_path):
    assert list_meetings(str(tmp_path / "nope")) == []
