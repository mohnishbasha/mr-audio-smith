"""Join rendered units into one 44.1 kHz track with pauses, crossfades, and chunk spans (FR-014)."""

import math
from dataclasses import dataclass

import numpy as np

from audio_smith.pipeline_types import MASTER_SAMPLE_RATE, AssembledTrack, ChunkSpan, RenderedUnit, silence
from audio_smith.tts.base import FloatArray

DEFAULT_CROSSFADE_MS = 10
MS_PER_S = 1000


@dataclass
class _Op:
    """One step of the layout: audio (with the chunk it belongs to) or silence."""

    audio: FloatArray | None
    silence_ms: int = 0
    chunk_id: str = ""
    text: str = ""


def resample(samples: FloatArray, src_rate: int, dst_rate: int) -> FloatArray:
    """Linear-interpolation resampler; deterministic and dependency-free.

    Why: narration is band-limited well below 22 kHz, so linear interpolation is inaudible for
    the 24 kHz to 44.1 kHz case and keeps the golden duration tests exact.
    """
    if src_rate == dst_rate or len(samples) == 0:
        return samples.astype(np.float32, copy=False)
    n_out = round(len(samples) * dst_rate / src_rate)
    src_pos = np.arange(n_out) * (src_rate / dst_rate)
    out = np.interp(src_pos, np.arange(len(samples)), samples)
    return out.astype(np.float32)


def _ramp(n: int) -> FloatArray:
    """Equal-power fade-in curve of length n (sin quarter wave)."""
    return np.sin(np.linspace(0.0, math.pi / 2, n, dtype=np.float32)).astype(np.float32)


def _layout(units: list[RenderedUnit], pause_between_chunks_ms: int, sample_rate: int) -> list[_Op]:
    """Turn units into audio and silence ops; the last unit gets no trailing pause."""
    ops: list[_Op] = []
    for i, ru in enumerate(units):
        audio = resample(np.asarray(ru.samples, dtype=np.float32), ru.sample_rate, sample_rate)
        ops.append(_Op(audio, chunk_id=ru.unit.chunk_id, text=ru.unit.display_text))
        if i == len(units) - 1:
            break
        gap = ru.unit.pause_after_ms
        if units[i + 1].unit.chunk_id != ru.unit.chunk_id:
            gap += pause_between_chunks_ms
        if gap > 0:
            ops.append(_Op(None, silence_ms=gap))
    return ops


def _edge_fades(audio: FloatArray, fade_in: bool, fade_out: bool, n: int) -> FloatArray:
    """Fade the edges that touch silence or the track ends so they cannot click."""
    out = audio.copy()
    n = min(n, len(out) // 2)
    if n < 2:
        return out
    ramp = _ramp(n)
    if fade_in:
        out[:n] *= ramp
    if fade_out:
        out[-n:] *= ramp[::-1]
    return out


def _crossfade(prev: FloatArray, cur: FloatArray, n: int) -> tuple[FloatArray, FloatArray, int]:
    """Return (prev without tail, overlapped region + cur remainder, overlap used)."""
    n = min(n, len(prev) // 2, len(cur) // 2)
    if n < 1:
        return prev, cur, 0
    fade_in = _ramp(n)
    mixed = prev[-n:] * fade_in[::-1] + cur[:n] * fade_in
    return prev[:-n], np.concatenate([mixed, cur[n:]]).astype(np.float32), n


def assemble(
    units: list[RenderedUnit],
    *,
    pause_between_chunks_ms: int,
    crossfade_ms: int = DEFAULT_CROSSFADE_MS,
    sample_rate: int = MASTER_SAMPLE_RATE,
) -> AssembledTrack:
    """Concatenate rendered units at the master rate.

    Why: chunk spans feed the captions and manifest, so they are recorded while laying out
    the audio. Crossfades apply only where two audio pieces touch (overlap shortens the track
    by at most crossfade_ms per join); edges next to silence get a fade so there are no clicks.

    Args:
        units: Rendered units in narration order.
        pause_between_chunks_ms: Extra silence inserted between different chunks.
        crossfade_ms: Equal-power crossfade length at audio-to-audio joins.
        sample_rate: Output rate.

    Returns:
        The assembled mono track with one ChunkSpan per chunk.
    """
    if not units:
        return AssembledTrack(samples=silence(0, sample_rate), sample_rate=sample_rate)
    ops = _layout(units, pause_between_chunks_ms, sample_rate)
    fade_n = round(sample_rate * crossfade_ms / MS_PER_S)
    pieces: list[FloatArray] = []
    cursor = 0
    prev_audio = False
    spans: dict[str, ChunkSpan] = {}
    order: list[str] = []
    to_ms = MS_PER_S / sample_rate
    for i, op in enumerate(ops):
        if op.audio is None:
            pieces.append(silence(op.silence_ms, sample_rate))
            cursor += len(pieces[-1])
            prev_audio = False
            continue
        next_audio = i + 1 < len(ops) and ops[i + 1].audio is not None
        audio = _edge_fades(op.audio, not prev_audio, not next_audio, fade_n)
        if prev_audio:
            pieces[-1], audio, overlap = _crossfade(pieces[-1], audio, fade_n)
            cursor -= overlap
        start = cursor
        cursor += len(audio)
        pieces.append(audio)
        prev_audio = True
        _record(spans, order, op, round(start * to_ms), round(cursor * to_ms))
    samples = np.concatenate(pieces).astype(np.float32)
    return AssembledTrack(samples=samples, sample_rate=sample_rate, spans=[spans[c] for c in order])


def _record(spans: dict[str, ChunkSpan], order: list[str], op: _Op, start_ms: int, end_ms: int) -> None:
    existing = spans.get(op.chunk_id)
    if existing is None:
        spans[op.chunk_id] = ChunkSpan(chunk_id=op.chunk_id, start_ms=start_ms, end_ms=end_ms, text=op.text)
        order.append(op.chunk_id)
        return
    existing.end_ms = end_ms
    existing.text = f"{existing.text} {op.text}".strip()
