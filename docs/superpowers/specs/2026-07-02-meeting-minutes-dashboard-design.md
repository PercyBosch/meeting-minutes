# Meeting Minutes Dashboard — Design Spec

**Date:** 2026-07-02
**Owner:** Percy (Cloud Centrix)
**Status:** Approved design — ready for implementation planning

## 1. Purpose

A local dashboard where the user uploads a meeting recording (audio or video),
clicks one button, and receives polished, well-structured meeting minutes as a
Word `.docx` and/or `.pdf`. A 2-hour recording goes in; clean minutes come out.

The app is developed once, pushed to git, and run locally on any machine after a
one-time setup. It runs entirely on the user's machine with **$0 ongoing cost**
by default.

## 2. Goals & Non-Goals

**Goals**
- Upload a recording, click "Generate Minutes", download a formatted document.
- Handle long recordings (2h+) reliably.
- Produce structured minutes: summary, decisions, action items, topics, next steps.
- Run locally and free by default; degrade gracefully to cloud services via config.
- Keep a local history of past meetings that can be re-opened and re-downloaded.

**Non-Goals (v1)**
- Live/real-time transcription (files only).
- Multi-user accounts, auth, or hosting on a server.
- Calendar/email integrations.
- Automatic, always-on speaker diarization (it is an optional, off-by-default toggle).

## 3. Decisions (from brainstorming)

| Area | Decision |
|------|----------|
| App framework | **Python + Streamlit** single app (`streamlit run app.py`) |
| Transcription | **faster-whisper** locally by default; **Groq Whisper** as a config-switch fallback |
| Summarization | **Ollama** local model by default (e.g. `llama3.1:8b`); cloud (Claude Haiku) via config-switch |
| Speaker labels | Optional toggle, **off by default** |
| Output formats | Word `.docx` and PDF, user-selectable per run |
| Cost | $0 default; optional cloud usage is a few cents per meeting |

**Model/provider choices are config-driven**, so a weak machine can flip transcription
to Groq or summarization to Claude without any code change, while the default remains
fully local and free.

## 4. Target Environment

- Primary/test machine: WSL2 (Linux), Python 3.12, **NVIDIA RTX 3070 (8GB VRAM)**.
- Work machine: stronger GPU (per user).
- Because transcription and summarization run **sequentially** (not concurrently),
  Whisper large-v3 (~5GB) and an 8B Ollama model (~5GB Q4) each fit within 8GB VRAM
  one at a time. Whisper memory is released before summarization begins.
- `device=auto`: use CUDA when available, fall back to CPU automatically. On WSL,
  if CUDA/cuDNN libraries are unavailable, fall back to CPU `int8` rather than crash.

## 5. Architecture

Local Streamlit dashboard at `localhost:8501` driving a 5-stage pipeline:

```
Upload recording ─► [1] audio.py   normalize → 16kHz mono wav (ffmpeg)
                    [2] transcribe.py  faster-whisper → timestamped segments
                                       (provider: local | groq, from config)
                    [3] diarize.py  OPTIONAL speaker labels (off by default)
                    [4] summarize.py  chunked map-reduce → structured minutes
                                       (provider: ollama | claude, from config)
                    [5] render.py   minutes → .docx and/or .pdf
                 ─► preview + download buttons; saved to local meetings/ history
```

### Modules (each independently testable)

- **`audio.py`** — Convert any input (mp3/mp4/m4a/wav/mov/…) to normalized 16kHz mono
  wav via ffmpeg. Returns path to wav + duration. Validates the file is decodable.
- **`transcribe.py`** — Wrapper returning `[{start, end, text}]` segments.
  - `provider=local`: faster-whisper (model + device + compute_type from config).
  - `provider=groq`: POST audio to Groq's Whisper endpoint (needs `GROQ_API_KEY`).
  - Returns a uniform segment list regardless of provider.
- **`diarize.py`** — OPTIONAL. When enabled, produces speaker turns and the caller
  merges labels into segments. Off by default; absence must never block the pipeline.
- **`summarize.py`** — Turns the transcript into structured minutes.
  - **Chunked map-reduce**: split the transcript (a 2h meeting is ~15–25k words) into
    token-bounded chunks, summarize each chunk ("map"), then merge the chunk summaries
    into the final structured minutes ("reduce"). This keeps it within a local model's
    context window and stays reliable for long meetings.
  - `provider=ollama`: call local Ollama HTTP API (`model` from config).
  - `provider=claude`: call Claude Haiku (needs `ANTHROPIC_API_KEY`).
  - Output is a structured object (title, date, attendees, summary, decisions,
    action_items, topics, next_steps) so rendering is format-agnostic.
- **`render.py`** — Structured minutes → `.docx` (python-docx) and `.pdf` (reportlab,
  pure-Python, no heavy system deps). Applies a consistent minutes template/styling.
- **`store.py`** — Persist each meeting to `meetings/<id>/` (metadata.json + transcript.txt
  + minutes.docx/pdf). List/load for the history view.
- **`app.py`** — Streamlit dashboard wiring the pipeline with a progress indicator.
- **`config.yaml`** — Defaults for whisper model/device/compute_type, ollama model,
  provider selections, chunk sizes, output dir. `.env` holds optional API keys.

### Data flow

`app.py` collects form input → `audio.normalize()` → `transcribe.run()` →
(optional) `diarize.run()` + merge → `summarize.run()` → `render.to_docx()/to_pdf()` →
`store.save()` → dashboard shows preview + download buttons.

## 6. Dashboard UX

1. **New Meeting form**: file uploader; title; date; optional attendee names;
   "Speaker labels" toggle (off); output format (Word / PDF / both); **Generate Minutes** button.
2. **Progress**: a stepper/progress bar showing the 5 stages as they run.
3. **Result**: rendered minutes preview + **Download .docx / .pdf** buttons.
4. **History**: list of past meetings (title + date), each re-openable and re-downloadable.

## 7. Minutes Template (default, tweakable)

- **Title**
- **Date**
- **Attendees** (from the form; blank if not provided)
- **Summary** — one concise paragraph
- **Key Decisions** — bulleted
- **Action Items** — task · owner · due (owner/due blank if unknown)
- **Topics Discussed** — ordered by occurrence
- **Next Steps** — bulleted

## 8. Error Handling

- **Bad/undecodable upload**: ffmpeg validation fails → clear message, no pipeline run.
- **CUDA unavailable**: automatic fallback to CPU `int8`; surface a notice, keep going.
- **Ollama not running / model missing**: detect and show an actionable message
  ("start Ollama" / "ollama pull <model>") instead of a stack trace.
- **Transcript too long for one chunk**: handled by design via map-reduce chunking.
- **Cloud provider selected but key missing**: fail fast with a clear config message.
- Long-running stages run without blocking the UI from showing progress.

## 9. Testing Strategy

- **audio.py**: a short fixture clip normalizes to 16kHz mono wav; a corrupt file errors cleanly.
- **transcribe.py**: local provider on a tiny fixture returns non-empty segments; provider
  selection routes correctly (mock the Groq path).
- **summarize.py**: chunking splits a long synthetic transcript into the expected number of
  chunks; the reduce step returns the full structured schema; provider routing is mocked so
  tests need no network or GPU.
- **render.py**: a sample minutes object produces a valid, openable `.docx` and `.pdf`
  containing the expected section headings.
- **store.py**: save then load round-trips metadata and file paths.
- End-to-end smoke test on a short real clip, run manually, before first real meeting.

## 10. One-Time Setup (README)

Install once per machine:
- Python 3.10+ (3.12 present)
- `ffmpeg` (system package)
- Ollama + a model: install Ollama, then `ollama pull llama3.1:8b`
- `pip install -r requirements.txt`

Then run: `streamlit run app.py` → opens `localhost:8501`.

Optional cloud fallbacks: set `GROQ_API_KEY` and/or `ANTHROPIC_API_KEY` in `.env` and
flip the relevant provider in `config.yaml`.

## 11. Repository Layout

```
meeting-minutes/
├── app.py
├── config.yaml
├── requirements.txt
├── .env.example
├── README.md
├── src/
│   ├── audio.py
│   ├── transcribe.py
│   ├── diarize.py
│   ├── summarize.py
│   ├── render.py
│   └── store.py
├── tests/
├── meetings/            # local history (git-ignored)
└── docs/superpowers/specs/
```

## 12. Open Questions / Future

- Diarization implementation detail (pyannote vs Whisper-based) deferred until the
  optional toggle is actually built out; v1 ships the toggle wired to a stub if needed.
- Editable minutes (tweak in-app before download) — future enhancement.
- Batch upload of multiple recordings — future enhancement.
