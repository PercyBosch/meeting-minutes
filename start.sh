#!/usr/bin/env bash
#
# One-command install + run for the Meeting Minutes dashboard (macOS / Linux).
#   ./start.sh
#
# First run downloads EVERYTHING it needs — Python packages, a bundled ffmpeg,
# the Ollama AI engine, and the AI model — then opens the dashboard. Later runs
# just launch it. The only thing you install yourself is Python 3.
#
# Windows users: run this in WSL or Git Bash, or use start.bat.

set -euo pipefail
cd "$(dirname "$0")"

OS="$(uname -s)"
OLLAMA_VERSION="v0.31.1"
export OLLAMA_MODELS="$(pwd)/.local/ollama-models"

# Load API keys from .env if present (enables cloud mode → no local models).
if [ -f .env ]; then set -a; . ./.env; set +a; fi

# --- 1. Python -------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required (the only thing you install yourself)."
  echo "  macOS: run 'xcode-select --install', or get it from https://www.python.org/downloads/"
  echo "  Then re-run ./start.sh"
  exit 1
fi

# --- 2. Virtual env + dependencies (idempotent) ----------------------------
[ -d .venv ] || { echo "Creating virtual environment…"; python3 -m venv .venv; }
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
  ln -sf "$(python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')" .venv/bin/ffmpeg
fi

# --- 4. Summarizer: cloud mode (keys present) or local Ollama ---------------
if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${GROQ_API_KEY:-}" ]; then
  echo "Cloud API key detected — cloud mode (no local models to download)."
  echo "  (Set config.yaml providers to 'groq' / 'claude' to use them.)"
else
  # Resolve an ollama binary: PATH → previously-downloaded local copy → auto-download.
  OLLAMA=""
  if command -v ollama >/dev/null 2>&1; then
    OLLAMA="ollama"
  else
    OLLAMA="$(find .local/ollama -type f -name ollama 2>/dev/null | head -1 || true)"
  fi
  if [ -z "$OLLAMA" ]; then
    mkdir -p .local/ollama
    if [ "$OS" = "Darwin" ]; then
      echo "Downloading the Ollama AI engine for macOS (~120MB, one-time)…"
      curl -L --fail -o .local/ollama.tgz \
        "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-darwin.tgz"
      tar -xzf .local/ollama.tgz -C .local/ollama
      xattr -dr com.apple.quarantine .local/ollama 2>/dev/null || true
      OLLAMA="$(find .local/ollama -type f -name ollama | head -1)"
      chmod +x "$OLLAMA" 2>/dev/null || true
    else
      echo "Please install Ollama once (Linux): curl -fsSL https://ollama.com/install.sh | sh"
      echo "  …or run cloud mode instead by putting GROQ_API_KEY / ANTHROPIC_API_KEY in a .env file."
      exit 1
    fi
  fi
  # Make bundled libraries (Linux CUDA, etc.) discoverable if we're using a local copy.
  OLLAMA_DIR="$(cd "$(dirname "$OLLAMA")/.." && pwd)"
  export DYLD_LIBRARY_PATH="$OLLAMA_DIR/lib:${DYLD_LIBRARY_PATH:-}"
  export LD_LIBRARY_PATH="$OLLAMA_DIR/lib/ollama:$OLLAMA_DIR/lib:${LD_LIBRARY_PATH:-}"

  # Start the server if it isn't already answering.
  if ! curl -s http://localhost:11434/api/version >/dev/null 2>&1; then
    echo "Starting the Ollama server…"
    "$OLLAMA" serve >/tmp/ollama-serve.log 2>&1 &
    for _ in 1 2 3 4 5 6 7 8; do
      curl -s http://localhost:11434/api/version >/dev/null 2>&1 && break
      sleep 1
    done
  fi

  MODEL="$(python -c "import yaml; print(yaml.safe_load(open('config.yaml'))['summarize']['ollama']['model'])")"
  if ! "$OLLAMA" list 2>/dev/null | grep -q "$MODEL"; then
    echo "Downloading the AI model '$MODEL' (one-time; this is the big one)…"
    "$OLLAMA" pull "$MODEL"
  fi
fi

# --- 5. Launch -------------------------------------------------------------
echo ""
echo "Starting the dashboard → open http://localhost:8501 in your browser"
exec streamlit run app.py
