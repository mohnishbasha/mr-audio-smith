"""Script validation (FR-006): sanitize stray formatting, then report violations by chunk number."""

import re

from pydantic import BaseModel, Field

from audio_smith.blocks import hash_text, strip_emoji
from audio_smith.script.markdown import Chunk, Script

PAUSE = re.compile(r"\[pause (\d+)\]")
EMPHASIS = re.compile(r"(?<![*\w])\*([^\s*]+)\*(?![*\w])")
PAUSE_MIN_MS = 100
PAUSE_MAX_MS = 3000
MIN_SENTENCES = 2
MAX_SENTENCES = 4
_BRACKETED = re.compile(r"\[[^\]]*\]")
_ANGLE = re.compile(r"<[^>]{0,80}>")
_SENTENCE = re.compile(r"[^.!?]+[.!?]+")
_TERMINAL_PUNCT = re.compile(r"[\s.!?,;:]+$")
_STRAY = [
    (re.compile(r"\*+\s*(\[pause \d+\])\s*\*+"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"__([^_]+)__"), r"\1"),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"!?\[([^\]]+)\]\([^)]*\)"), r"\1"),
    (re.compile(r"^\s{0,3}#{1,6}\s+", re.M), ""),
    (re.compile(r"^\s{0,3}(?:[-*+]|\d+[.)])\s+", re.M), ""),
    (re.compile(r"^\s{0,3}>\s?", re.M), ""),
]


class ValidationReport(BaseModel):
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def sanitize(text: str) -> str:
    """Remove formatting the LLM was told not to produce; markers are preserved."""
    out = strip_emoji(text)
    for pattern, repl in _STRAY:
        out = pattern.sub(repl, out)
    out = re.sub(r"[ \t]+", " ", out)
    return re.sub(r" +([,.;:!?])", r"\1", out).strip()


def plain_text(text: str) -> str:
    """Spoken text: markers removed, emphasis unwrapped, whitespace collapsed."""
    return re.sub(r"\s+", " ", EMPHASIS.sub(r"\1", PAUSE.sub(" ", text))).strip()


def _verbatim_key(text: str) -> str:
    return _TERMINAL_PUNCT.sub("", hash_text(plain_text(text))).lower()


def _check_markers(c: Chunk, report: ValidationReport) -> None:
    for m in PAUSE.finditer(c.text):
        ms = int(m.group(1))
        if not PAUSE_MIN_MS <= ms <= PAUSE_MAX_MS:
            report.errors.append(f"chunk {c.id}: pause {ms} ms outside {PAUSE_MIN_MS}..{PAUSE_MAX_MS}")
    leftover = PAUSE.sub("", c.text)
    for m in _BRACKETED.finditer(leftover):
        report.errors.append(f"chunk {c.id}: unknown marker {m.group(0)!r}; only [pause N] is allowed")
    for m in _ANGLE.finditer(leftover):
        report.errors.append(f"chunk {c.id}: markup {m.group(0)!r} is not allowed")
    if "*" in EMPHASIS.sub("", leftover):
        report.errors.append(f"chunk {c.id}: stray '*'; emphasis is *oneword* only")


def _check_chunk(c: Chunk, max_chars: int, report: ValidationReport) -> None:
    spoken = plain_text(c.text)
    if not spoken:
        report.errors.append(f"chunk {c.id}: empty")
        return
    _check_markers(c, report)
    if len(spoken) > max_chars:
        report.errors.append(f"chunk {c.id}: {len(spoken)} characters exceeds max_chunk_chars {max_chars}")
    sentences = len(_SENTENCE.findall(spoken)) or 1
    if not c.verbatim and not MIN_SENTENCES <= sentences <= MAX_SENTENCES:
        report.warnings.append(
            f"chunk {c.id}: {sentences} sentences (aim for {MIN_SENTENCES} to {MAX_SENTENCES})"
        )


def _check_numbering(script: Script, report: ValidationReport) -> None:
    for expected, c in enumerate(script.chunks, 1):
        if c.number != expected:
            report.errors.append(f"chunk {c.id}: expected chunk number {expected:03d}")
            return


def _check_verbatim(script: Script, verbatim_sources: list[str], report: ValidationReport) -> None:
    allowed = {_verbatim_key(t) for t in verbatim_sources}
    present = set()
    for c in script.chunks:
        if c.verbatim:
            key = _verbatim_key(c.text)
            present.add(key)
            if key not in allowed:
                report.errors.append(f"chunk {c.id}: verbatim chunk differs from the source text")
    for src in verbatim_sources:
        if _verbatim_key(src) not in present:
            report.errors.append(f"missing verbatim chunk for source text {src[:50]!r} (keep it exactly)")


def validate(
    script: Script, *, max_chunk_chars: int, verbatim_sources: list[str] | None = None
) -> ValidationReport:
    """Check a script against the grammar; sanitize first with sanitize_script()."""
    report = ValidationReport()
    if not script.chunks:
        report.errors.append("script has no chunks")
    _check_numbering(script, report)
    for c in script.chunks:
        _check_chunk(c, max_chunk_chars, report)
    if verbatim_sources is not None:
        _check_verbatim(script, verbatim_sources, report)
    return report


def sanitize_script(script: Script) -> Script:
    chunks = [
        c.model_copy(update={"text": c.text if c.verbatim else sanitize(c.text)}) for c in script.chunks
    ]
    return script.model_copy(update={"chunks": chunks})


def word_count(script: Script) -> int:
    return sum(len(plain_text(c.text).split()) for c in script.chunks)
