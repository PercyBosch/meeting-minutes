from src import pipeline
from src.config import Config
from src.models import Minutes, Segment


def test_run_pipeline_wires_stages(monkeypatch, tmp_path):
    cfg = Config(raw={"storage": {"dir": str(tmp_path / "meetings")}})
    events = []

    captured = {}
    monkeypatch.setattr(pipeline, "normalize_audio", lambda src, dst: dst)
    monkeypatch.setattr(pipeline, "transcribe", lambda wav, cfg: [Segment(0, 1, "hello")])
    fake_minutes = Minutes(title="Sync", date="2026-07-02", summary="s")

    def fake_summarize(segs, t, d, a, c, content_type="general"):
        captured["content_type"] = content_type
        return fake_minutes

    monkeypatch.setattr(pipeline, "summarize", fake_summarize)
    monkeypatch.setattr(pipeline, "to_docx", lambda m, p: p)
    monkeypatch.setattr(pipeline, "to_pdf", lambda m, p: p)
    monkeypatch.setattr(pipeline, "save_meeting", lambda *a, **k: "mid-123")

    result = pipeline.run_pipeline(
        input_path="in.mp4",
        title="Sync",
        date="2026-07-02",
        attendees=["Percy"],
        formats=["docx", "pdf"],
        cfg=cfg,
        workdir=str(tmp_path / "work"),
        content_type="podcast",
        progress=events.append,
    )

    assert result["id"] == "mid-123"
    assert result["minutes"] is fake_minutes
    assert result["transcript"] == "hello"
    assert set(result["files"]) == {"docx", "pdf"}
    assert captured["content_type"] == "podcast"  # content type flows through
    assert len(events) >= 5  # a progress message per stage


def test_run_pipeline_respects_format_selection(monkeypatch, tmp_path):
    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("to_pdf should not be called when pdf not requested")

    cfg = Config(raw={"storage": {"dir": str(tmp_path / "meetings")}})
    monkeypatch.setattr(pipeline, "normalize_audio", lambda src, dst: dst)
    monkeypatch.setattr(pipeline, "transcribe", lambda wav, cfg: [Segment(0, 1, "hi")])
    monkeypatch.setattr(pipeline, "summarize", lambda *a, **k: Minutes(title="t", date="d"))
    monkeypatch.setattr(pipeline, "to_docx", lambda m, p: p)
    monkeypatch.setattr(pipeline, "to_pdf", _should_not_be_called)
    monkeypatch.setattr(pipeline, "save_meeting", lambda *a, **k: "mid")

    result = pipeline.run_pipeline("in.mp4", "t", "d", [], ["docx"], cfg, str(tmp_path / "w"))
    assert set(result["files"]) == {"docx"}
