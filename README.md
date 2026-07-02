# Meeting Minutes Dashboard

Upload a meeting recording, click one button, and download polished minutes as
Word (`.docx`) and/or PDF. Runs locally; free by default.

## Quick start (one line)

```bash
./start.sh
```

`start.sh` is idempotent: the first run installs everything that's missing
(virtual env, Python deps, a bundled ffmpeg, and — in local mode — the Ollama
model), then launches the dashboard at http://localhost:8501. Every run after
that just launches it.

- **macOS / Windows note:** Python 3 is the only prerequisite you install yourself
  (https://www.python.org/downloads/). For *local* mode you also install Ollama once
  (https://ollama.com/download). Or skip Ollama entirely with **cloud mode** below.

## Easiest on any machine (incl. a MacBook): cloud mode

Local mode downloads a few GB of AI models and likes a GPU. To run on *any*
machine with almost no setup — no models, no GPU — use cloud mode:

1. Create a `.env` file (copy `.env.example`) and add at least one key:
   - `GROQ_API_KEY=...`  (fast, low-cost speech-to-text — has a free tier)
   - `ANTHROPIC_API_KEY=...`  (writes the minutes)
2. In `config.yaml` set `transcribe.provider: groq` and/or `summarize.provider: claude`.
3. `./start.sh`

`start.sh` detects the keys and skips all local model downloads. This is the
lightest "clone and run" path and works the same on macOS, Linux, and Windows.

## Manual setup (if you'd rather not use start.sh)

1. Install **ffmpeg**: macOS `brew install ffmpeg` · Ubuntu/WSL `sudo apt-get install -y ffmpeg`
2. Install **Ollama** and pull the model: https://ollama.com/download then
   `ollama pull llama3.1:8b` (or the lighter `ollama pull llama3.2:3b`)
3. `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`
4. `streamlit run app.py`

## Configuration (`config.yaml`)

Everything is local and free by default. Switch any stage to a cloud service:

- **Transcription** → `transcribe.provider: groq` + `GROQ_API_KEY` (fast, pennies).
- **Summarization** → `summarize.provider: claude` + `ANTHROPIC_API_KEY`
  (`summarize.claude.model` defaults to `claude-opus-4-8`; `claude-haiku-4-5` is cheaper).
- **Quality vs speed** → transcription `large-v3` and summarizer `llama3.1:8b` give the
  best minutes; `small` / `llama3.2:3b` are faster and lighter.

## GPU notes

On an NVIDIA GPU, transcription uses CUDA automatically (`device: auto`). If the CUDA
libraries aren't present it falls back to CPU automatically — slower, but it still runs.
Apple Silicon Macs run Ollama on the Metal GPU; Whisper runs on CPU there.

## Tests

```bash
pytest
```
