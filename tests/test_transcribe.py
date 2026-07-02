import pytest

from src import transcribe
from src.config import Config
from src.models import Segment
from src.transcribe import transcribe as run_transcribe, TranscribeError, load_model


def test_transcribe_routes_to_local(monkeypatch):
    cfg = Config(raw={"transcribe": {"provider": "local"}})
    monkeypatch.setattr(transcribe, "_transcribe_local", lambda p, c: [Segment(0, 1, "hi")])
    monkeypatch.setattr(transcribe, "_transcribe_groq", lambda p, c: pytest.fail("wrong route"))
    out = run_transcribe("a.wav", cfg)
    assert out[0].text == "hi"


def test_transcribe_routes_to_groq(monkeypatch):
    cfg = Config(raw={"transcribe": {"provider": "groq"}})
    monkeypatch.setattr(transcribe, "_transcribe_groq", lambda p, c: [Segment(0, 1, "g")])
    out = run_transcribe("a.wav", cfg)
    assert out[0].text == "g"


def test_transcribe_unknown_provider_raises():
    cfg = Config(raw={"transcribe": {"provider": "nope"}})
    with pytest.raises(TranscribeError):
        run_transcribe("a.wav", cfg)


def test_load_model_falls_back_to_cpu_on_gpu_error():
    calls = []

    class FakeModel:
        def __init__(self, name, device, compute_type):
            calls.append((device, compute_type))
            if device != "cpu":
                raise RuntimeError("no CUDA")

    model = load_model(FakeModel, "large-v3", "cuda", "int8_float16")
    assert isinstance(model, FakeModel)
    assert calls[-1] == ("cpu", "int8")


def test_transcribe_local_falls_back_to_cpu_on_runtime_error(monkeypatch):
    # GPU construction succeeds but transcribe() raises a missing-CUDA-lib error;
    # the whole transcription must retry on CPU rather than crash.
    cfg = Config(raw={"transcribe": {"provider": "local", "local": {"device": "cuda"}}})
    attempts = []

    class FakeModel:
        def __init__(self, name, device, compute_type):
            self.device = device
            attempts.append(device)

        def transcribe(self, path):
            if self.device != "cpu":
                raise RuntimeError("Library libcublas.so.12 is not found")
            seg = type("Seg", (), {"start": 0.0, "end": 1.0, "text": " hi "})()
            return [seg], None

    monkeypatch.setattr(transcribe, "_whisper_model_cls", lambda: FakeModel)
    out = transcribe._transcribe_local("a.wav", cfg)
    assert attempts == ["cuda", "cpu"]
    assert out == [Segment(0.0, 1.0, "hi")]


def test_transcribe_groq_requires_key(monkeypatch):
    cfg = Config(raw={"transcribe": {"provider": "groq"}})
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(TranscribeError):
        transcribe._transcribe_groq("a.wav", cfg)
