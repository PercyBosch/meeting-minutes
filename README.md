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
   - `python3 -m venv .venv && . .venv/bin/activate`
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
