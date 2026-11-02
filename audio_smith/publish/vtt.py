"""WebVTT captions derived from chunk timings (FR-015).

Forced alignment against the audio is deferred (OOS-04). Cue times are instead
distributed inside each chunk span by character-length proportion, which keeps
every cue boundary close to the real audio because chunks are only 2 to 4 sentences.
"""

import re
from pathlib import Path

from pydantic import BaseModel

from audio_smith.paths import atomic_write
from audio_smith.pipeline_types import ChunkSpan

LONG_SENTENCE_CHARS = 120
ABBREVIATIONS = frozenset(
    {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e", "no", "inc"}
)
_PAUSE_MARKER = re.compile(r"\s*\[pause \d+\]\s*")
_EMPHASIS = re.compile(r"\*(\w+)\*")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_SPACES = re.compile(r"\s+")
_MS_PER_SECOND = 1000
_MS_PER_MINUTE = 60_000
_MS_PER_HOUR = 3_600_000
_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))


class Cue(BaseModel):
    """One caption cue in milliseconds from the start of the track."""

    start_ms: int
    end_ms: int
    text: str


def clean_text(text: str) -> str:
    """Strip script markers so cues show only what is spoken.

    Why: pause markers and emphasis asterisks are instructions to the synthesizer,
    and showing them in captions would confuse readers.
    """
    no_pause = _PAUSE_MARKER.sub(" ", text)
    return _SPACES.sub(" ", _EMPHASIS.sub(r"\1", no_pause)).strip()


def _ends_with_abbreviation(piece: str) -> bool:
    last = piece.rsplit(None, 1)[-1].lower().rstrip(".")
    return piece.endswith(".") and last in ABBREVIATIONS


def split_sentences(text: str) -> list[str]:
    """Split on . ! ? followed by a space, keeping abbreviations like "Mr." intact."""
    sentences: list[str] = []
    for piece in _SENTENCE_BREAK.split(text):
        if sentences and _ends_with_abbreviation(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {piece}"
        else:
            sentences.append(piece)
    return [s for s in sentences if s]


def _split_long(sentence: str) -> list[str]:
    """Split an over-long sentence at the comma closest to its middle."""
    if len(sentence) <= LONG_SENTENCE_CHARS:
        return [sentence]
    commas = [i for i, ch in enumerate(sentence) if ch == ","]
    commas = [i for i in commas if sentence[i + 1 : i + 2] == " "]
    if not commas:
        return [sentence]
    cut = min(commas, key=lambda i: abs(i - len(sentence) / 2))
    return [sentence[: cut + 1].strip(), sentence[cut + 1 :].strip()]


def _cues_for_span(span: ChunkSpan) -> list[Cue]:
    pieces = [p for s in split_sentences(clean_text(span.text)) for p in _split_long(s)]
    total = sum(len(p) for p in pieces)
    if total == 0:
        return []
    length = span.end_ms - span.start_ms
    cues: list[Cue] = []
    consumed = 0
    start = span.start_ms
    for piece in pieces:
        consumed += len(piece)
        end = span.end_ms if consumed == total else span.start_ms + round(length * consumed / total)
        cues.append(Cue(start_ms=start, end_ms=max(start, end), text=piece))
        start = max(start, end)
    return cues


def build_cues(spans: list[ChunkSpan]) -> list[Cue]:
    """Build one cue per sentence, timed inside each chunk span.

    Why: cues derive from the narrated script text, never the source page, and each
    cue stays inside its chunk so consecutive cues cannot overlap.
    """
    return [cue for span in spans for cue in _cues_for_span(span)]


def format_timestamp(ms: int) -> str:
    """Format milliseconds as HH:MM:SS.mmm."""
    hours, rest = divmod(ms, _MS_PER_HOUR)
    minutes, rest = divmod(rest, _MS_PER_MINUTE)
    seconds, millis = divmod(rest, _MS_PER_SECOND)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _escape(text: str) -> str:
    for raw, safe in _ESCAPES:
        text = text.replace(raw, safe)
    return text


def render_vtt(cues: list[Cue]) -> str:
    """Render cues as a WebVTT document with <, > and & escaped."""
    blocks = ["WEBVTT\n"]
    for cue in cues:
        stamp = f"{format_timestamp(cue.start_ms)} --> {format_timestamp(cue.end_ms)}"
        blocks.append(f"{stamp}\n{_escape(cue.text)}\n")
    return "\n".join(blocks)


def write_vtt(path: Path, spans: list[ChunkSpan]) -> Path:
    """Build cues from spans and write the VTT file atomically."""
    return atomic_write(path, render_vtt(build_cues(spans)))
