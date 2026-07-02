import subprocess

import pytest

from src import audio
from src.audio import AudioError, ffmpeg_cmd, normalize_audio


def test_ffmpeg_cmd_targets_16khz_mono():
    cmd = ffmpeg_cmd("in.mp4", "out.wav")
    assert cmd[0] == "ffmpeg"
    assert "16000" in cmd
    assert "-ac" in cmd and cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[-1] == "out.wav"


def test_normalize_audio_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x")
    monkeypatch.setattr(audio.shutil, "which", lambda name: None)
    with pytest.raises(AudioError):
        normalize_audio(str(src), str(tmp_path / "out.wav"))


def test_normalize_audio_raises_on_nonzero_exit(monkeypatch, tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x")
    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    def fake_run(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    with pytest.raises(AudioError):
        normalize_audio(str(src), str(tmp_path / "out.wav"))


def test_normalize_audio_returns_dst_on_success(monkeypatch, tmp_path):
    src = tmp_path / "a.mp3"
    src.write_bytes(b"x")
    dst = tmp_path / "out.wav"
    monkeypatch.setattr(audio.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    def fake_run(cmd, capture_output, text):
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    result = normalize_audio(str(src), str(dst))
    assert str(result) == str(dst)
