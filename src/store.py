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
