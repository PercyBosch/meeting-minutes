from datetime import date as date_cls
from pathlib import Path

import streamlit as st

from src.config import load_config
from src.pipeline import run_pipeline
from src.store import list_meetings

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
    st.checkbox(
        "Speaker labels (experimental)",
        value=False,
        disabled=True,
        help="Optional diarization — reserved for a future version.",
    )
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
            stages = {
                "Normalizing audio…": 0.1,
                "Transcribing…": 0.4,
                "Summarizing…": 0.7,
                "Rendering documents…": 0.9,
                "Saving to history…": 1.0,
            }

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
                            f"Download .{kind}",
                            f.read(),
                            file_name=Path(path).name,
                            key=f"{meta['id']}-{kind}",
                        )
