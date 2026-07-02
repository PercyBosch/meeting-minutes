# Meeting Minutes Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local Streamlit dashboard where the user uploads a meeting recording, clicks one button, and downloads polished meeting minutes as Word `.docx` and/or PDF.

**Architecture:** A 5-stage pipeline (normalize audio → transcribe → optional diarize → summarize → render) wired behind a Streamlit UI. Each stage is an isolated, independently testable module. Transcription defaults to local faster-whisper (GPU) with a Groq cloud fallback; summarization defaults to local Ollama with a Claude fallback — both selectable via `config.yaml`.

**Tech Stack:** Python 3.12, Streamlit, faster-whisper, ffmpeg (system), Ollama (local HTTP), python-docx, reportlab, pytest.

## Global Constraints

- Python 3.10+ (dev machine has 3.12) — one line each, exact values from the spec.
- Everything defaults to **$0 / local**; cloud providers (Groq, Claude) are opt-in via `config.yaml` + `.env`.
- Transcription and summarization run **sequentially**, never concurrently (8GB VRAM budget: Whisper large-v3 ~5GB then Ollama 8B ~5GB, one at a time).
- Device selection is `auto` with automatic CPU/`int8` fallback when CUDA/cuDNN is unavailable — the app must never crash on a machine without a working GPU.
- Speaker diarization is **optional and off by default**; its absence must never block the pipeline.
- Long meetings (2h ≈ 15–25k words) are handled by **chunked map-reduce** summarization so a local model's small context window is never exceeded.
- Cloud model IDs (exact, do not alter): Groq transcription `whisper-large-v3`; Claude summarization default `claude-opus-4-8` (cheaper alternative documented as `claude-haiku-4-5`). The `anthropic` SDK call uses `client.messages.create(...)` with **no** `temperature` parameter (removed on Opus 4.8).
- All modules live under `src/` as a package; tests under `tests/`. Run tests with `pytest`.

---

### Task 1: Project scaffolding & dependencies

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `pytest.ini`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: an installable environment and a working `pytest` run. Later tasks import from the `src` package.

- [ ] **Step 1: Write the failing smoke test**

Create `tests/test_smoke.py`:

```python
def test_src_package_importable():
    import src  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src'`

- [ ] **Step 3: Create the package files and configs**

Create `src/__init__.py` (empty file).
Create `tests/__init__.py` (empty file).

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

Create `requirements.txt`:

```text
streamlit>=1.36
faster-whisper>=1.0.3
python-docx>=1.1.2
reportlab>=4.2
requests>=2.32
PyYAML>=6.0
anthropic>=0.40
pytest>=8.2
```

Create `config.yaml`:

```yaml
# Meeting Minutes Dashboard configuration. Defaults are 100% local / $0.
transcribe:
  provider: local        # local | groq
  local:
    model: large-v3       # tiny|base|small|medium|large-v3 (large-v3 = best; fits 8GB GPU)
    device: auto          # auto | cuda | cpu
    compute_type: int8_float16   # falls back to int8 on CPU automatically
  groq:
    model: whisper-large-v3      # used only when provider=groq (needs GROQ_API_KEY)

summarize:
  provider: ollama        # ollama | claude
  chunk_chars: 6000       # transcript characters per map chunk
  ollama:
    host: http://localhost:11434
    model: llama3.1:8b
  claude:
    model: claude-opus-4-8   # cheaper alternative: claude-haiku-4-5 (needs ANTHROPIC_API_KEY)

storage:
  dir: meetings           # local history folder (git-ignored)
```

Create `.env.example`:

```text
# Copy to .env and fill in only if you switch a provider to a cloud service.
GROQ_API_KEY=
ANTHROPIC_API_KEY=
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt config.yaml .env.example src/ tests/ pytest.ini
git commit -m "chore: project scaffolding, deps, and config"
```

---

### Task 2: Shared data models

**Files:**
- Create: `src/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Segment(start: float, end: float, text: str, speaker: str | None = None)`
  - `ActionItem(task: str, owner: str = "", due: str = "")`
  - `Minutes(title, date, attendees: list[str], summary: str, decisions: list[str], action_items: list[ActionItem], topics: list[str], next_steps: list[str])`
  - `Minutes.to_dict() -> dict` and `Minutes.from_dict(d: dict) -> Minutes` (round-trippable, used by `store.py` and `render.py`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
from src.models import Segment, ActionItem, Minutes


def test_minutes_round_trips_through_dict():
    m = Minutes(
        title="Weekly Sync",
        date="2026-07-02",
        attendees=["Percy", "Stefan"],
        summary="Discussed the launch.",
        decisions=["Ship on Friday"],
        action_items=[ActionItem(task="Write release notes", owner="Percy", due="Thu")],
        topics=["Launch", "Testing"],
        next_steps=["Prepare rollback plan"],
    )
    restored = Minutes.from_dict(m.to_dict())
    assert restored == m
    assert restored.action_items[0].owner == "Percy"


def test_segment_defaults_speaker_to_none():
    s = Segment(start=0.0, end=1.5, text="hello")
    assert s.speaker is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.models'`

- [ ] **Step 3: Write minimal implementation**

Create `src/models.py`:

```python
from dataclasses import dataclass, field, asdict


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass
class ActionItem:
    task: str
    owner: str = ""
    due: str = ""


@dataclass
class Minutes:
    title: str
    date: str
    attendees: list[str] = field(default_factory=list)
    summary: str = ""
    decisions: list[str] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Minutes":
        d = dict(d)
        d["action_items"] = [ActionItem(**a) for a in d.get("action_items", [])]
        return cls(**d)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: shared data models (Segment, ActionItem, Minutes)"
```

---

### Task 3: Config loader

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Config` dataclass with `raw: dict` and `get(path: str, default=None)` (dotted-path lookup, e.g. `cfg.get("transcribe.provider", "local")`).
  - `load_config(path: str = "config.yaml") -> Config` (returns an empty config if the file is missing).

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from src.config import load_config, Config


def test_get_reads_nested_dotted_path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("transcribe:\n  provider: groq\n  local:\n    model: small\n")
    cfg = load_config(str(p))
    assert cfg.get("transcribe.provider") == "groq"
    assert cfg.get("transcribe.local.model") == "small"


def test_get_returns_default_for_missing_path(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("summarize:\n  provider: ollama\n")
    cfg = load_config(str(p))
    assert cfg.get("transcribe.provider", "local") == "local"


def test_missing_file_yields_empty_config():
    cfg = load_config("does-not-exist.yaml")
    assert isinstance(cfg, Config)
    assert cfg.get("anything", "fallback") == "fallback"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Write minimal implementation**

Create `src/config.py`:

```python
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    raw: dict

    def get(self, path: str, default=None):
        node = self.raw
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


def load_config(path: str = "config.yaml") -> Config:
    p = Path(path)
    data = yaml.safe_load(p.read_text()) if p.exists() else {}
    return Config(raw=data or {})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: config loader with dotted-path lookup"
```

---

### Task 4: Audio normalization

**Files:**
- Create: `src/audio.py`
- Test: `tests/test_audio.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `AudioError(Exception)`
  - `ffmpeg_cmd(src, dst) -> list[str]` (pure function building the ffmpeg argv).
  - `normalize_audio(src, dst) -> Path` (converts any input to 16kHz mono wav; raises `AudioError` if ffmpeg is missing, the input is missing, or ffmpeg exits non-zero).

- [ ] **Step 1: Write the failing test**

Create `tests/test_audio.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.audio'`

- [ ] **Step 3: Write minimal implementation**

Create `src/audio.py`:

```python
import shutil
import subprocess
from pathlib import Path


class AudioError(Exception):
    pass


def ffmpeg_cmd(src, dst) -> list[str]:
    return ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-vn", str(dst)]


def normalize_audio(src, dst) -> Path:
    if shutil.which("ffmpeg") is None:
        raise AudioError("ffmpeg not found on PATH. Install ffmpeg to process recordings.")
    src_path = Path(src)
    if not src_path.exists():
        raise AudioError(f"Input file not found: {src_path}")
    proc = subprocess.run(ffmpeg_cmd(src_path, dst), capture_output=True, text=True)
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg failed: {proc.stderr[-500:]}")
    return Path(dst)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audio.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/audio.py tests/test_audio.py
git commit -m "feat: audio normalization via ffmpeg (16kHz mono wav)"
```

---

### Task 5: Transcription (local + Groq, provider-routed)

**Files:**
- Create: `src/transcribe.py`
- Test: `tests/test_transcribe.py`

**Interfaces:**
- Consumes: `Config` from `src.config`; `Segment` from `src.models`.
- Produces:
  - `TranscribeError(Exception)`
  - `transcribe(wav_path, cfg) -> list[Segment]` (routes on `cfg.get("transcribe.provider")`).
  - `load_model(model_cls, name, device, compute_type)` (tries the requested device, falls back to CPU `int8` on any exception).
  - `_transcribe_local(wav_path, cfg)` and `_transcribe_groq(wav_path, cfg)` (both return `list[Segment]`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_transcribe.py`:

```python
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


def test_transcribe_groq_requires_key(monkeypatch):
    cfg = Config(raw={"transcribe": {"provider": "groq"}})
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(TranscribeError):
        transcribe._transcribe_groq("a.wav", cfg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_transcribe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.transcribe'`

- [ ] **Step 3: Write minimal implementation**

Create `src/transcribe.py`:

```python
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


def _transcribe_local(wav_path, cfg) -> list[Segment]:
    from faster_whisper import WhisperModel

    name = cfg.get("transcribe.local.model", "large-v3")
    device = cfg.get("transcribe.local.device", "auto")
    compute_type = cfg.get("transcribe.local.compute_type", "int8_float16")
    model = load_model(WhisperModel, name, device, compute_type)
    segments, _info = model.transcribe(str(wav_path))
    return [Segment(start=s.start, end=s.end, text=s.text.strip()) for s in segments]


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_transcribe.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/transcribe.py tests/test_transcribe.py
git commit -m "feat: transcription with local faster-whisper + Groq fallback"
```

---

### Task 6: Transcript chunking (map-reduce input)

**Files:**
- Create: `src/summarize.py` (chunking function only in this task)
- Test: `tests/test_chunking.py`

**Interfaces:**
- Consumes: `Segment` from `src.models`.
- Produces: `chunk_transcript(segments: list[Segment], max_chars: int = 6000) -> list[str]` (joins segment text into chunks no larger than `max_chars`; skips empty segments; returns `[]` for empty input).

- [ ] **Step 1: Write the failing test**

Create `tests/test_chunking.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_chunking.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.summarize'`

- [ ] **Step 3: Write minimal implementation**

Create `src/summarize.py`:

```python
from .models import Segment


def chunk_transcript(segments: list[Segment], max_chars: int = 6000) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if size + len(text) + 1 > max_chars and buf:
            chunks.append(" ".join(buf))
            buf, size = [], 0
        buf.append(text)
        size += len(text) + 1
    if buf:
        chunks.append(" ".join(buf))
    return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chunking.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/summarize.py tests/test_chunking.py
git commit -m "feat: transcript chunking for map-reduce summarization"
```

---

### Task 7: Summarization (map-reduce + Ollama/Claude providers)

**Files:**
- Modify: `src/summarize.py` (append prompts, providers, and the `summarize` orchestrator)
- Test: `tests/test_summarize.py`

**Interfaces:**
- Consumes: `chunk_transcript` (Task 6); `Config`; `Minutes`, `ActionItem`, `Segment`.
- Produces:
  - `SummarizeError(Exception)`
  - `summarize(segments, title, date, attendees, cfg) -> Minutes`
  - `parse_json(raw: str) -> dict` (extracts the first `{...}` block; raises `SummarizeError` if none).
  - `get_llm(cfg) -> Callable[[str], str]` (routes on `cfg.get("summarize.provider")`).
  - `_ollama_call(prompt, cfg) -> str`, `_claude_call(prompt, cfg) -> str`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_summarize.py`:

```python
import json

import pytest

from src import summarize as summ
from src.config import Config
from src.models import Segment
from src.summarize import summarize, parse_json, SummarizeError


REDUCE_RESULT = {
    "summary": "We agreed to ship Friday.",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_summarize.py -v`
Expected: FAIL — `ImportError: cannot import name 'summarize' from 'src.summarize'` (function not yet defined)

- [ ] **Step 3: Write minimal implementation**

Append to `src/summarize.py` (below the existing `chunk_transcript`):

```python
import json
import os

from .models import Minutes, ActionItem


class SummarizeError(Exception):
    pass


MAP_PROMPT = """You are summarizing part {i} of {n} of a meeting transcript.
Extract the key points, decisions, and any action items from THIS excerpt only.
Be concise and factual. Excerpt:
\"\"\"
{chunk}
\"\"\""""

REDUCE_PROMPT = """You are writing the final minutes for a meeting titled "{title}" held on {date}.
Attendees: {attendees}.
Below are ordered notes from consecutive parts of the meeting. Merge them into
final minutes. Return ONLY valid JSON with this exact schema:
{{
  "summary": "one concise paragraph",
  "decisions": ["..."],
  "action_items": [{{"task": "...", "owner": "", "due": ""}}],
  "topics": ["..."],
  "next_steps": ["..."]
}}
Notes:
{notes}"""


def summarize(segments, title, date, attendees, cfg) -> Minutes:
    chunks = chunk_transcript(segments, cfg.get("summarize.chunk_chars", 6000))
    if not chunks:
        raise SummarizeError("Empty transcript; nothing to summarize.")
    call = get_llm(cfg)
    partials = [
        call(MAP_PROMPT.format(i=i + 1, n=len(chunks), chunk=c))
        for i, c in enumerate(chunks)
    ]
    notes = "\n\n".join(f"Part {i + 1}:\n{p}" for i, p in enumerate(partials))
    raw = call(
        REDUCE_PROMPT.format(
            title=title,
            date=date,
            attendees=", ".join(attendees) or "not specified",
            notes=notes,
        )
    )
    data = parse_json(raw)
    return Minutes(
        title=title,
        date=date,
        attendees=list(attendees),
        summary=data.get("summary", ""),
        decisions=data.get("decisions", []),
        action_items=[ActionItem(**a) for a in data.get("action_items", [])],
        topics=data.get("topics", []),
        next_steps=data.get("next_steps", []),
    )


def parse_json(raw: str) -> dict:
    raw = raw.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise SummarizeError(f"LLM did not return JSON: {raw[:200]}")
    return json.loads(raw[start : end + 1])


def get_llm(cfg):
    provider = cfg.get("summarize.provider", "ollama")
    if provider == "ollama":
        return lambda prompt: _ollama_call(prompt, cfg)
    if provider == "claude":
        return lambda prompt: _claude_call(prompt, cfg)
    raise SummarizeError(f"Unknown summarize provider: {provider}")


def _ollama_call(prompt, cfg) -> str:
    import requests

    host = cfg.get("summarize.ollama.host", "http://localhost:11434")
    model = cfg.get("summarize.ollama.model", "llama3.1:8b")
    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=600,
        )
    except requests.exceptions.ConnectionError as e:
        raise SummarizeError(
            f"Cannot reach Ollama at {host}. Is `ollama serve` running?"
        ) from e
    if resp.status_code != 200:
        raise SummarizeError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
    return resp.json().get("response", "")


def _claude_call(prompt, cfg) -> str:
    from anthropic import Anthropic

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise SummarizeError("ANTHROPIC_API_KEY not set but summarize.provider=claude")
    model = cfg.get("summarize.claude.model", "claude-opus-4-8")
    client = Anthropic(api_key=key)
    msg = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_summarize.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/summarize.py tests/test_summarize.py
git commit -m "feat: map-reduce summarization with Ollama + Claude providers"
```

---

### Task 8: Rendering to DOCX and PDF

**Files:**
- Create: `src/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `Minutes`, `ActionItem` from `src.models`.
- Produces:
  - `to_docx(minutes: Minutes, path) -> Path`
  - `to_pdf(minutes: Minutes, path) -> Path`
  - `action_line(item: ActionItem) -> str` (pure helper: `"task (owner · due)"`, omitting empty owner/due).

- [ ] **Step 1: Write the failing test**

Create `tests/test_render.py`:

```python
from docx import Document

from src.models import Minutes, ActionItem
from src.render import to_docx, to_pdf, action_line


def _sample() -> Minutes:
    return Minutes(
        title="Weekly Sync",
        date="2026-07-02",
        attendees=["Percy"],
        summary="We discussed the launch.",
        decisions=["Ship Friday"],
        action_items=[ActionItem(task="Write notes", owner="Percy", due="Thu")],
        topics=["Launch"],
        next_steps=["Rollback plan"],
    )


def test_action_line_includes_owner_and_due():
    assert action_line(ActionItem(task="Do X", owner="Percy", due="Thu")) == "Do X (Percy · Thu)"


def test_action_line_omits_empty_fields():
    assert action_line(ActionItem(task="Do X")) == "Do X"


def test_to_docx_writes_openable_file_with_headings(tmp_path):
    out = tmp_path / "m.docx"
    to_docx(_sample(), out)
    doc = Document(str(out))
    texts = [p.text for p in doc.paragraphs]
    assert "Weekly Sync" in texts
    assert "Summary" in texts
    assert "Key Decisions" in texts
    assert "Action Items" in texts


def test_to_pdf_writes_nonempty_file(tmp_path):
    out = tmp_path / "m.pdf"
    to_pdf(_sample(), out)
    assert out.exists()
    assert out.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.render'`

- [ ] **Step 3: Write minimal implementation**

Create `src/render.py`:

```python
from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from .models import Minutes, ActionItem


def action_line(item: ActionItem) -> str:
    extra = " · ".join(x for x in [item.owner, item.due] if x)
    return f"{item.task} ({extra})" if extra else item.task


def to_docx(minutes: Minutes, path) -> Path:
    doc = Document()
    doc.add_heading(minutes.title, level=0)
    doc.add_paragraph(f"Date: {minutes.date}")
    if minutes.attendees:
        doc.add_paragraph("Attendees: " + ", ".join(minutes.attendees))

    doc.add_heading("Summary", level=1)
    doc.add_paragraph(minutes.summary)

    doc.add_heading("Key Decisions", level=1)
    for d in minutes.decisions:
        doc.add_paragraph(d, style="List Bullet")

    doc.add_heading("Action Items", level=1)
    for a in minutes.action_items:
        doc.add_paragraph(action_line(a), style="List Bullet")

    doc.add_heading("Topics Discussed", level=1)
    for t in minutes.topics:
        doc.add_paragraph(t, style="List Number")

    doc.add_heading("Next Steps", level=1)
    for n in minutes.next_steps:
        doc.add_paragraph(n, style="List Bullet")

    doc.save(str(path))
    return Path(path)


def to_pdf(minutes: Minutes, path) -> Path:
    styles = getSampleStyleSheet()
    story = [Paragraph(minutes.title, styles["Title"]), Paragraph(f"Date: {minutes.date}", styles["Normal"])]
    if minutes.attendees:
        story.append(Paragraph("Attendees: " + ", ".join(minutes.attendees), styles["Normal"]))

    def section(heading, items, prefix=""):
        story.append(Spacer(1, 12))
        story.append(Paragraph(heading, styles["Heading2"]))
        for i, item in enumerate(items, 1):
            bullet = f"{i}. " if prefix == "num" else "• "
            story.append(Paragraph(bullet + item, styles["Normal"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Summary", styles["Heading2"]))
    story.append(Paragraph(minutes.summary, styles["Normal"]))
    section("Key Decisions", minutes.decisions)
    section("Action Items", [action_line(a) for a in minutes.action_items])
    section("Topics Discussed", minutes.topics, prefix="num")
    section("Next Steps", minutes.next_steps)

    SimpleDocTemplate(str(path), pagesize=A4).build(story)
    return Path(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_render.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/render.py tests/test_render.py
git commit -m "feat: render minutes to DOCX and PDF"
```

---

### Task 9: Local history store

**Files:**
- Create: `src/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Minutes` from `src.models`.
- Produces:
  - `save_meeting(base_dir, title, date, minutes: Minutes, transcript_text: str, files: dict) -> str` (returns a meeting id; writes `metadata.json`, `minutes.json`, `transcript.txt`, and copies each file in `files`).
  - `list_meetings(base_dir) -> list[dict]` (newest first; each dict is the saved metadata).
  - `load_meeting(base_dir, mid) -> tuple[dict, Minutes]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_store.py`:

```python
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
    mid = save_meeting(str(tmp_path / "meetings"), "Sync", "2026-07-02", _minutes(), "hello transcript", {"docx": str(docx)})

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.store'`

- [ ] **Step 3: Write minimal implementation**

Create `src/store.py`:

```python
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from .models import Minutes


def save_meeting(base_dir, title, date, minutes: Minutes, transcript_text: str, files: dict) -> str:
    base = Path(base_dir)
    mid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    mdir = base / mid
    mdir.mkdir(parents=True, exist_ok=True)

    (mdir / "transcript.txt").write_text(transcript_text)
    (mdir / "minutes.json").write_text(json.dumps(minutes.to_dict(), indent=2))

    saved = {}
    for kind, src in files.items():
        if src:
            dst = mdir / Path(src).name
            shutil.copy(src, dst)
            saved[kind] = str(dst)

    meta = {"id": mid, "title": title, "date": date, "files": saved}
    (mdir / "metadata.json").write_text(json.dumps(meta, indent=2))
    return mid


def list_meetings(base_dir) -> list[dict]:
    base = Path(base_dir)
    if not base.exists():
        return []
    out = []
    for d in sorted(base.iterdir(), reverse=True):
        mp = d / "metadata.json"
        if mp.exists():
            out.append(json.loads(mp.read_text()))
    return out


def load_meeting(base_dir, mid) -> tuple[dict, Minutes]:
    mdir = Path(base_dir) / mid
    meta = json.loads((mdir / "metadata.json").read_text())
    minutes = Minutes.from_dict(json.loads((mdir / "minutes.json").read_text()))
    return meta, minutes
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_store.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/store.py tests/test_store.py
git commit -m "feat: local meeting history store (save/list/load)"
```

---

### Task 10: Pipeline orchestrator

**Files:**
- Create: `src/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `normalize_audio`, `transcribe`, `summarize`, `to_docx`, `to_pdf`, `save_meeting`, `Config`.
- Produces:
  - `run_pipeline(input_path, title, date, attendees, formats, cfg, workdir, progress=None) -> dict` where the returned dict has keys `id`, `minutes` (a `Minutes`), `files` (dict), and `transcript` (str). `formats` is a list subset of `["docx", "pdf"]`. `progress` is an optional `Callable[[str], None]` called before each stage.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline.py`:

```python
from src import pipeline
from src.config import Config
from src.models import Minutes, Segment


def test_run_pipeline_wires_stages(monkeypatch, tmp_path):
    cfg = Config(raw={"storage": {"dir": str(tmp_path / "meetings")}})
    events = []

    monkeypatch.setattr(pipeline, "normalize_audio", lambda src, dst: dst)
    monkeypatch.setattr(pipeline, "transcribe", lambda wav, cfg: [Segment(0, 1, "hello")])
    fake_minutes = Minutes(title="Sync", date="2026-07-02", summary="s")
    monkeypatch.setattr(pipeline, "summarize", lambda segs, t, d, a, c: fake_minutes)
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
        progress=events.append,
    )

    assert result["id"] == "mid-123"
    assert result["minutes"] is fake_minutes
    assert result["transcript"] == "hello"
    assert set(result["files"]) == {"docx", "pdf"}
    assert len(events) >= 5  # a progress message per stage


def test_run_pipeline_respects_format_selection(monkeypatch, tmp_path):
    cfg = Config(raw={"storage": {"dir": str(tmp_path / "meetings")}})
    monkeypatch.setattr(pipeline, "normalize_audio", lambda src, dst: dst)
    monkeypatch.setattr(pipeline, "transcribe", lambda wav, cfg: [Segment(0, 1, "hi")])
    monkeypatch.setattr(pipeline, "summarize", lambda *a: Minutes(title="t", date="d"))
    monkeypatch.setattr(pipeline, "to_docx", lambda m, p: p)
    monkeypatch.setattr(pipeline, "to_pdf", lambda m, p: pytest_fail())
    monkeypatch.setattr(pipeline, "save_meeting", lambda *a, **k: "mid")

    result = pipeline.run_pipeline("in.mp4", "t", "d", [], ["docx"], cfg, str(tmp_path / "w"))
    assert set(result["files"]) == {"docx"}


def pytest_fail():
    raise AssertionError("to_pdf should not be called when pdf not requested")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.pipeline'`

- [ ] **Step 3: Write minimal implementation**

Create `src/pipeline.py`:

```python
from pathlib import Path

from .audio import normalize_audio
from .transcribe import transcribe
from .summarize import summarize
from .render import to_docx, to_pdf
from .store import save_meeting


def run_pipeline(input_path, title, date, attendees, formats, cfg, workdir, progress=None) -> dict:
    def step(msg):
        if progress:
            progress(msg)

    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    step("Normalizing audio…")
    wav = normalize_audio(input_path, work / "audio.wav")

    step("Transcribing…")
    segments = transcribe(wav, cfg)
    transcript_text = "\n".join(s.text for s in segments)

    step("Summarizing…")
    minutes = summarize(segments, title, date, attendees, cfg)

    step("Rendering documents…")
    files = {}
    if "docx" in formats:
        files["docx"] = str(to_docx(minutes, work / "minutes.docx"))
    if "pdf" in formats:
        files["pdf"] = str(to_pdf(minutes, work / "minutes.pdf"))

    step("Saving to history…")
    mid = save_meeting(
        cfg.get("storage.dir", "meetings"), title, date, minutes, transcript_text, files
    )

    return {"id": mid, "minutes": minutes, "files": files, "transcript": transcript_text}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/pipeline.py tests/test_pipeline.py
git commit -m "feat: pipeline orchestrator wiring all stages"
```

---

### Task 11: Streamlit dashboard

**Files:**
- Create: `app.py`
- Test: `tests/test_app_import.py`

**Interfaces:**
- Consumes: `load_config`, `run_pipeline`, `list_meetings`, `load_meeting`.
- Produces: a runnable Streamlit app (`streamlit run app.py`). Because Streamlit UI is not unit-testable in a headless run, this task verifies the module imports cleanly and delegates all logic to already-tested modules. A manual smoke test is part of Task 12.

- [ ] **Step 1: Write the failing test**

Create `tests/test_app_import.py`:

```python
import importlib.util
from pathlib import Path


def test_app_module_parses():
    # Compile app.py without executing Streamlit runtime to catch syntax/import errors.
    path = Path(__file__).resolve().parents[1] / "app.py"
    source = path.read_text()
    compile(source, str(path), "exec")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app_import.py -v`
Expected: FAIL — `FileNotFoundError` (app.py does not exist yet)

- [ ] **Step 3: Write minimal implementation**

Create `app.py`:

```python
from datetime import date as date_cls
from pathlib import Path

import streamlit as st

from src.config import load_config
from src.pipeline import run_pipeline
from src.store import list_meetings, load_meeting

st.set_page_config(page_title="Meeting Minutes", layout="centered")
cfg = load_config()

st.title("Meeting Minutes")
st.caption("Upload a recording, generate polished minutes, download as Word or PDF.")

tab_new, tab_history = st.tabs(["New Meeting", "History"])

with tab_new:
    uploaded = st.file_uploader(
        "Meeting recording", type=["mp3", "mp4", "m4a", "wav", "mov", "webm", "mkv"]
    )
    title = st.text_input("Meeting title", value="Team Meeting")
    meeting_date = st.date_input("Date", value=date_cls.today())
    attendees_raw = st.text_input("Attendees (comma-separated, optional)")
    st.checkbox("Speaker labels (experimental)", value=False, disabled=True,
                help="Optional diarization — reserved for a future version.")
    fmt = st.multiselect("Output format", ["docx", "pdf"], default=["docx", "pdf"])

    if st.button("Generate Minutes", type="primary"):
        if not uploaded:
            st.error("Please upload a recording first.")
        elif not fmt:
            st.error("Pick at least one output format.")
        else:
            work = Path("meetings") / "_work"
            work.mkdir(parents=True, exist_ok=True)
            input_path = work / uploaded.name
            input_path.write_bytes(uploaded.getbuffer())
            attendees = [a.strip() for a in attendees_raw.split(",") if a.strip()]

            progress = st.progress(0.0)
            status = st.empty()
            stages = {"Normalizing audio…": 0.1, "Transcribing…": 0.4,
                      "Summarizing…": 0.7, "Rendering documents…": 0.9,
                      "Saving to history…": 1.0}

            def on_step(msg):
                status.write(msg)
                progress.progress(stages.get(msg, 0.0))

            try:
                result = run_pipeline(
                    input_path=str(input_path),
                    title=title,
                    date=str(meeting_date),
                    attendees=attendees,
                    formats=fmt,
                    cfg=cfg,
                    workdir=str(work),
                    progress=on_step,
                )
            except Exception as e:  # surface a clean message, not a traceback
                st.error(f"Something went wrong: {e}")
            else:
                status.write("Done.")
                m = result["minutes"]
                st.subheader(m.title)
                st.write(m.summary)
                for kind, path in result["files"].items():
                    with open(path, "rb") as f:
                        st.download_button(
                            f"Download .{kind}", f.read(), file_name=Path(path).name
                        )

with tab_history:
    meetings = list_meetings(cfg.get("storage.dir", "meetings"))
    if not meetings:
        st.info("No meetings yet. Generate one in the New Meeting tab.")
    for meta in meetings:
        with st.expander(f"{meta['date']} — {meta['title']}"):
            for kind, path in meta.get("files", {}).items():
                if Path(path).exists():
                    with open(path, "rb") as f:
                        st.download_button(
                            f"Download .{kind}", f.read(),
                            file_name=Path(path).name, key=f"{meta['id']}-{kind}"
                        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_app_import.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app_import.py
git commit -m "feat: Streamlit dashboard for upload, generate, download, history"
```

---

### Task 12: README + full test run + manual smoke test

**Files:**
- Create: `README.md`
- Test: full suite via `pytest`

**Interfaces:**
- Consumes: everything.
- Produces: setup documentation and a verified end-to-end run.

- [ ] **Step 1: Write the README**

Create `README.md`:

```markdown
# Meeting Minutes Dashboard

Upload a meeting recording, click one button, and download polished minutes as
Word (`.docx`) and/or PDF. Runs locally; free by default.

## One-time setup

1. Install **ffmpeg** (system package):
   - Ubuntu/WSL: `sudo apt-get update && sudo apt-get install -y ffmpeg`
2. Install **Ollama** and pull a model:
   - https://ollama.com/download — then `ollama pull llama3.1:8b`
   - Make sure it is running: `ollama serve` (or the desktop app).
3. Install Python deps:
   - `pip install -r requirements.txt`

## Run

```bash
streamlit run app.py
```

Opens http://localhost:8501. Upload a recording, fill in the title/date,
choose Word/PDF, and click **Generate Minutes**.

## Configuration

Everything is local and free by default. To switch a stage to a cloud service,
edit `config.yaml` and add the key to `.env` (copy from `.env.example`):

- **Transcription** → set `transcribe.provider: groq` and `GROQ_API_KEY` (fast, pennies).
- **Summarization** → set `summarize.provider: claude` and `ANTHROPIC_API_KEY`
  (`summarize.claude.model` defaults to `claude-opus-4-8`; `claude-haiku-4-5` is cheaper).

## GPU notes

On an NVIDIA GPU, transcription uses CUDA automatically (`device: auto`). If CUDA
or cuDNN is unavailable it falls back to CPU automatically — slower, but it still runs.

## Tests

```bash
pytest
```
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: PASS — all tests from Tasks 1–11 green.

- [ ] **Step 3: Manual end-to-end smoke test**

Ensure `ffmpeg` and `ollama` are installed and `ollama serve` is running with `llama3.1:8b` pulled. Then:

Run: `streamlit run app.py`
- Upload a short (~1 min) audio/video clip.
- Enter a title, keep both formats, click **Generate Minutes**.
- Confirm the progress bar advances through all five stages, the summary renders,
  and both **Download .docx** and **Download .pdf** buttons produce openable files.
- Open the **History** tab and confirm the meeting appears and re-downloads.

Expected: minutes document with Summary, Key Decisions, Action Items, Topics, Next Steps.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, run, config, and smoke test"
```

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- Upload → generate → download (spec §1, §6): Task 11 (UI) + Task 10 (pipeline).
- Local transcription + Groq fallback (spec §5 `transcribe.py`): Task 5.
- Optional diarization, off by default (spec §5 `diarize.py`): surfaced as a disabled toggle in Task 11; a full diarization module is intentionally deferred (spec §12 lists it as future). The toggle exists and never blocks the pipeline, satisfying the "optional, off by default" requirement.
- Chunked map-reduce summarization (spec §5 `summarize.py`): Tasks 6 + 7.
- DOCX + PDF rendering (spec §5 `render.py`): Task 8.
- Local history (spec §5 `store.py`, §6 History): Task 9 + Task 11 History tab.
- Config-driven providers (spec §3): Task 3 + used throughout Tasks 5, 7.
- Error handling (spec §8): `AudioError`/`TranscribeError`/`SummarizeError` raised with actionable messages; CUDA fallback in `load_model`; Ollama-not-running detection; UI wraps the pipeline in try/except (Task 11).
- Minutes template (spec §7): encoded in `render.py` (Task 8) and the `Minutes` model (Task 2).
- Setup (spec §10): Task 12 README.

**2. Placeholder scan** — no "TBD"/"TODO"/"implement later"; every code step contains complete, runnable code. The diarization toggle is `disabled=True` by design, not a placeholder.

**3. Type consistency** — `Minutes`/`ActionItem`/`Segment` field names and `to_dict`/`from_dict` are used identically across Tasks 2, 7, 8, 9, 10. `Config.get` dotted-path signature is consistent across Tasks 3, 5, 7, 10. `run_pipeline` return keys (`id`, `minutes`, `files`, `transcript`) match their consumer in Task 11. Provider strings (`local`/`groq`, `ollama`/`claude`) match `config.yaml` in Task 1.
