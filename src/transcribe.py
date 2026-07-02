import os

from .models import Segment


class TranscribeError(Exception):
    pass


def transcribe(wav_path, cfg) -> list[Segment]:
    provider = cfg.get("transcribe.provider", "local")
    if provider == "local":
        return _transcribe_local(wav_path, cfg)
    if provider == "groq":
        return _transcribe_groq(wav_path, cfg)
    raise TranscribeError(f"Unknown transcribe provider: {provider}")


def load_model(model_cls, name, device, compute_type):
    try:
        return model_cls(name, device=device, compute_type=compute_type)
    except Exception:
        # CUDA/cuDNN unavailable — fall back to CPU int8 rather than crash.
        return model_cls(name, device="cpu", compute_type="int8")


def _whisper_model_cls():
    from faster_whisper import WhisperModel

    return WhisperModel


def _run_whisper(model_cls, name, device, compute_type, wav_path) -> list[Segment]:
    model = load_model(model_cls, name, device, compute_type)
    segments, _info = model.transcribe(str(wav_path))
    return [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in segments]


def _transcribe_local(wav_path, cfg) -> list[Segment]:
    name = cfg.get("transcribe.local.model", "large-v3")
    device = cfg.get("transcribe.local.device", "auto")
    compute_type = cfg.get("transcribe.local.compute_type", "int8_float16")
    model_cls = _whisper_model_cls()
    try:
        return _run_whisper(model_cls, name, device, compute_type, wav_path)
    except Exception:
        # CUDA runtime libraries (libcublas/libcudnn) may be missing even when a
        # GPU is detected — the failure can surface at transcribe time, not just
        # construction. Retry the whole transcription on CPU rather than crash.
        if device == "cpu":
            raise
        return _run_whisper(model_cls, name, "cpu", "int8", wav_path)


def _transcribe_groq(wav_path, cfg) -> list[Segment]:
    import requests

    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise TranscribeError("GROQ_API_KEY not set but transcribe.provider=groq")
    model = cfg.get("transcribe.groq.model", "whisper-large-v3")
    with open(wav_path, "rb") as f:
        resp = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {key}"},
            files={"file": f},
            data={"model": model, "response_format": "verbose_json"},
            timeout=600,
        )
    if resp.status_code != 200:
        raise TranscribeError(f"Groq error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    return [
        Segment(start=s["start"], end=s["end"], text=s["text"].strip())
        for s in data.get("segments", [])
    ]
