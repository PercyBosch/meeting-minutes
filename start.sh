#!/usr/bin/env bash
#
# One-line install + run for the Meeting Minutes dashboard.
#   ./start.sh
#
# First run: sets up everything that's missing. Later runs: just launches.
# Works on Linux and macOS. No admin/sudo needed except (optionally) installing
# Ollama for local mode. If a cloud API key is present, it skips local models
# entirely — the lightest "just works anywhere" path (great for a MacBook).

set -euo pipefail
cd "$(dirname "$0")"

# Load API keys from .env if present (so cloud mode is auto-detected).
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# --- 1. Python -------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it from https://www.python.org/downloads/ then re-run ./start.sh"
  exit 1
fi

# --- 2. Virtual env + dependencies (idempotent) ----------------------------
if [ ! -d .venv ]; then
  echo "Creating virtual environment…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate

if [ ! -f .venv/.deps-installed ]; then
  echo "Installing Python dependencies (one-time)…"
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt
  touch .venv/.deps-installed
fi

# --- 3. ffmpeg (bundled, no admin needed) ----------------------------------
if ! command -v ffmpeg >/dev/null 2>&1 && [ ! -e .venv/bin/ffmpeg ]; then
  echo "Setting up a bundled ffmpeg…"
  python -m pip install --quiet imageio-ffmpeg
  FF="$(python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
  ln -sf "$FF" .venv/bin/ffmpeg
fi

# --- 4. Summarizer: cloud mode (keys present) or local Ollama ---------------
if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${GROQ_API_KEY:-}" ]; then
  echo "Cloud API key detected — running in cloud mode (no local models to download)."
  echo "  (Make sure config.yaml providers are set to 'groq' / 'claude' to use them.)"
else
  if ! command -v ollama >/dev/null 2>&1; then
    echo ""
    echo "Local mode needs Ollama (one-time install):"
    echo "  macOS:  download the app from https://ollama.com/download   (or: brew install ollama)"
    echo "  Linux:  curl -fsSL https://ollama.com/install.sh | sh"
    echo ""
    echo "…or run in cloud mode instead: put GROQ_API_KEY / ANTHROPIC_API_KEY in a .env file."
    echo "Then re-run ./start.sh"
    exit 1
  fi
  # Start the Ollama server if it isn't already answering.
  if ! curl -s http://localhost:11434/api/version >/dev/null 2>&1; then
    echo "Starting Ollama server…"
    ollama serve >/tmp/ollama-serve.log 2>&1 &
    sleep 3
  fi
  MODEL="$(python -c "import yaml; print(yaml.safe_load(open('config.yaml'))['summarize']['ollama']['model'])")"
  if ! ollama list | grep -q "$MODEL"; then
    echo "Pulling the summarizer model '$MODEL' (one-time download)…"
    ollama pull "$MODEL"
  fi
fi

# --- 5. Launch -------------------------------------------------------------
echo ""
echo "Starting the dashboard → http://localhost:8501"
exec streamlit run app.py
