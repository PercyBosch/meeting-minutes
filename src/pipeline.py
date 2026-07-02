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
