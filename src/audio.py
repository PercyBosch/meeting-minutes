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
