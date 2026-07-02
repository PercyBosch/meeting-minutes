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
