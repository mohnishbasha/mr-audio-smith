"""Chunk planner (FR-012): script chunks to SynthUnits sized for the backend.

Why: backends have a max_chars limit and pauses must be real silence, not spoken markers,
so each chunk is cut at [pause N] markers and then at sentence boundaries.
"""

import re

from pydantic import BaseModel, Field

from audio_smith.cache.keys import chunk_key
from audio_smith.pipeline_types import SynthUnit
from audio_smith.script import lexicon as lexicon_mod
from audio_smith.script.markdown import Script
from audio_smith.script.validate import PAUSE, plain_text
from audio_smith.tts.base import VoiceRef

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_SOFT_BREAKS = (",", " ")


class PlanResult(BaseModel):
    units: list[SynthUnit]
    warnings: list[str] = Field(default_factory=list)


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text) if s]


def _hard_split(sentence: str, max_chars: int) -> list[str]:
    """Last resort for one over-long sentence: cut after the last comma, else last space."""
    pieces: list[str] = []
    rest = sentence
    while len(rest) > max_chars:
        window = rest[: max_chars + 1]
        cut = max((window.rfind(b) + (1 if b == "," else 0) for b in _SOFT_BREAKS), default=-1)
        if cut <= 0:
            cut = max_chars
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        pieces.append(rest)
    return pieces


def pack_sentences(text: str, max_chars: int) -> tuple[list[str], bool]:
    """Greedily pack whole sentences into pieces of at most max_chars.

    Returns (pieces, hard_split_used).
    """
    pieces: list[str] = []
    current = ""
    hard = False
    for sentence in split_sentences(text):
        if len(sentence) > max_chars:
            hard = True
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_hard_split(sentence, max_chars))
        elif current and len(current) + 1 + len(sentence) > max_chars:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces, hard


def _segments(text: str) -> list[tuple[str, int]]:
    """Split on [pause N]: (segment text, pause after in ms). The last segment has pause 0."""
    parts = PAUSE.split(text)
    return [(parts[i], int(parts[i + 1]) if i + 1 < len(parts) else 0) for i in range(0, len(parts), 2)]


def plan_units(
    script: Script,
    *,
    max_chars: int,
    lexicon: dict[str, str],
    backend_id: str,
    model: str,
    voice: VoiceRef,
    rate: float,
    seed_base: int = 0,
    chunks: set[str] | None = None,
) -> PlanResult:
    """Plan SynthUnits for every chunk (or the subset named in `chunks`).

    The lexicon applies to `text` only (display_text stays as written) and `key` is computed
    from the post-lexicon text so a lexicon edit invalidates exactly the affected units.
    """
    units: list[SynthUnit] = []
    warnings: list[str] = []
    for chunk in script.chunks:
        if chunks is not None and chunk.id not in chunks:
            continue
        index = 0
        for raw, pause in _segments(chunk.text):
            spoken = plain_text(raw)
            if not spoken:
                if units and pause:
                    units[-1].pause_after_ms += pause
                continue
            pieces, hard = pack_sentences(spoken, max_chars)
            if hard:
                warnings.append(
                    f"chunk {chunk.id}: sentence over {max_chars} chars split at a comma or space"
                )
            for n, piece in enumerate(pieces):
                text = lexicon_mod.apply(piece, lexicon)
                key = chunk_key(text, backend_id, model, voice.id, voice.clip_hash, rate, seed_base)
                last = n == len(pieces) - 1
                units.append(
                    SynthUnit(
                        chunk_id=chunk.id,
                        index=index,
                        text=text,
                        display_text=piece,
                        pause_after_ms=pause if last else 0,
                        key=key,
                    )
                )
                index += 1
    return PlanResult(units=units, warnings=warnings)
