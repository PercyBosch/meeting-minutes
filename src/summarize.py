import json
import os

from .models import Segment, Minutes, ActionItem


class SummarizeError(Exception):
    pass


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


# "map" step: pull thorough notes out of each chunk so nothing important is lost.
MAP_PROMPT = """You are analyzing part {i} of {n} of a transcript.
Write thorough, specific notes on THIS excerpt: the main points and arguments made,
important details and examples, any names mentioned, and any decisions or action items
if present. Capture substance, not just headings. Excerpt:
\"\"\"
{chunk}
\"\"\""""

# Content-type guidance injected into the reduce step.
_MEETING_GUIDANCE = (
    "This is a MEETING. Fill 'decisions', 'action_items' (task/owner/due), and "
    "'next_steps' from what was agreed; leave a field empty only if truly none. "
    "Still write a full 'summary' and 'key_points'."
)
_NONMEETING_GUIDANCE = (
    "This is NOT a meeting. Leave 'decisions', 'action_items', and 'next_steps' as "
    "empty arrays []. Put ALL the substance into a detailed multi-sentence 'summary' "
    "and a rich 'key_points' list (the specific ideas, insights, facts and takeaways), "
    "and give 'topics' with a short description each."
)

_STYLE_LABEL = {
    "meeting": "set of meeting minutes",
    "podcast": "summary of a podcast / interview",
    "talk": "summary of a talk or lecture",
    "general": "detailed summary of a recording",
}

REDUCE_PROMPT = """You are writing a {style_label} titled "{title}" ({date}).
{attendees_line}Below are ordered notes covering the whole recording. Produce a
thorough, well-written result — be substantial and specific, not vague.

Return ONLY valid JSON with exactly this schema:
{{
  "summary": "a detailed overview in full prose, 4-8 sentences across one or two paragraphs",
  "key_points": ["the most important points, insights, facts and takeaways — 6 to 12 specific bullets"],
  "topics": ["each main topic as 'Topic: a one-line description'"],
  "decisions": ["decisions that were made"],
  "action_items": [{{"task": "...", "owner": "", "due": ""}}],
  "next_steps": ["concrete next steps"]
}}

{guidance}

Notes:
{notes}"""


def summarize(segments, title, date, attendees, cfg, content_type: str = "general") -> Minutes:
    chunks = chunk_transcript(segments, cfg.get("summarize.chunk_chars", 6000))
    if not chunks:
        raise SummarizeError("Empty transcript; nothing to summarize.")
    call = get_llm(cfg)
    partials = [
        call(MAP_PROMPT.format(i=i + 1, n=len(chunks), chunk=c))
        for i, c in enumerate(chunks)
    ]
    notes = "\n\n".join(f"Part {i + 1}:\n{p}" for i, p in enumerate(partials))
    guidance = _MEETING_GUIDANCE if content_type == "meeting" else _NONMEETING_GUIDANCE
    attendees_line = f"Attendees/speakers: {', '.join(attendees)}.\n" if attendees else ""
    raw = call(
        REDUCE_PROMPT.format(
            style_label=_STYLE_LABEL.get(content_type, _STYLE_LABEL["general"]),
            title=title,
            date=date,
            attendees_line=attendees_line,
            guidance=guidance,
            notes=notes,
        )
    )
    data = parse_json(raw)
    return Minutes(
        title=title,
        date=date,
        attendees=list(attendees),
        summary=data.get("summary", ""),
        key_points=data.get("key_points", []),
        topics=data.get("topics", []),
        decisions=data.get("decisions", []),
        action_items=[ActionItem(**a) for a in data.get("action_items", [])],
        next_steps=data.get("next_steps", []),
    )


def parse_json(raw: str) -> dict:
    raw = raw.strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise SummarizeError(f"LLM did not return JSON: {raw[:200]}")
    return json.loads(raw[start : end + 1])


def get_llm(cfg):
    provider = cfg.get("summarize.provider", "ollama")
    if provider == "ollama":
        return lambda prompt: _ollama_call(prompt, cfg)
    if provider == "claude":
        return lambda prompt: _claude_call(prompt, cfg)
    raise SummarizeError(f"Unknown summarize provider: {provider}")


def _ollama_call(prompt, cfg) -> str:
    import requests

    host = cfg.get("summarize.ollama.host", "http://localhost:11434")
    model = cfg.get("summarize.ollama.model", "llama3.1:8b")
    try:
        resp = requests.post(
            f"{host}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                # Keep the default context so the model stays fully on the GPU
                # (a larger num_ctx can overflow 8GB VRAM and fall back to slow CPU).
                "options": {"temperature": 0.3},
            },
            timeout=600,
        )
    except requests.exceptions.ConnectionError as e:
        raise SummarizeError(
            f"Cannot reach Ollama at {host}. Is `ollama serve` running?"
        ) from e
    if resp.status_code != 200:
        raise SummarizeError(f"Ollama error {resp.status_code}: {resp.text[:300]}")
    return resp.json().get("response", "")


def _claude_call(prompt, cfg) -> str:
    from anthropic import Anthropic

    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise SummarizeError("ANTHROPIC_API_KEY not set but summarize.provider=claude")
    model = cfg.get("summarize.claude.model", "claude-opus-4-8")
    client = Anthropic(api_key=key)
    msg = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text
