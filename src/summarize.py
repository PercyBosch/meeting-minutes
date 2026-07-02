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


MAP_PROMPT = """You are summarizing part {i} of {n} of a meeting transcript.
Extract the key points, decisions, and any action items from THIS excerpt only.
Be concise and factual. Excerpt:
\"\"\"
{chunk}
\"\"\""""

REDUCE_PROMPT = """You are writing the final minutes for a meeting titled "{title}" held on {date}.
Attendees: {attendees}.
Below are ordered notes from consecutive parts of the meeting. Merge them into
final minutes. Return ONLY valid JSON with this exact schema:
{{
  "summary": "one concise paragraph",
  "decisions": ["..."],
  "action_items": [{{"task": "...", "owner": "", "due": ""}}],
  "topics": ["..."],
  "next_steps": ["..."]
}}
Notes:
{notes}"""


def summarize(segments, title, date, attendees, cfg) -> Minutes:
    chunks = chunk_transcript(segments, cfg.get("summarize.chunk_chars", 6000))
    if not chunks:
        raise SummarizeError("Empty transcript; nothing to summarize.")
    call = get_llm(cfg)
    partials = [
        call(MAP_PROMPT.format(i=i + 1, n=len(chunks), chunk=c))
        for i, c in enumerate(chunks)
    ]
    notes = "\n\n".join(f"Part {i + 1}:\n{p}" for i, p in enumerate(partials))
    raw = call(
        REDUCE_PROMPT.format(
            title=title,
            date=date,
            attendees=", ".join(attendees) or "not specified",
            notes=notes,
        )
    )
    data = parse_json(raw)
    return Minutes(
        title=title,
        date=date,
        attendees=list(attendees),
        summary=data.get("summary", ""),
        decisions=data.get("decisions", []),
        action_items=[ActionItem(**a) for a in data.get("action_items", [])],
        topics=data.get("topics", []),
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
            json={"model": model, "prompt": prompt, "stream": False},
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
