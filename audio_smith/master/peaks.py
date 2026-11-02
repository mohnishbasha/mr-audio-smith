"""Waveform peaks for the player (DESIGN: 28 bars)."""

import itertools

import numpy as np

from audio_smith.tts.base import FloatArray

DEFAULT_BARS = 28
PEAK_DECIMALS = 3
ATTR_SCALE = 100


def compute_peaks(samples: FloatArray, bars: int = DEFAULT_BARS) -> list[float]:
    """Max absolute amplitude per bar, normalized so the loudest bar is 1.0.

    Why: the player draws a fixed number of bars; normalizing keeps quiet narration readable.
    Silent or empty input yields all zeros rather than dividing by zero.
    """
    if bars < 1:
        raise ValueError("bars must be >= 1")
    if len(samples) == 0:
        return [0.0] * bars
    edges = np.linspace(0, len(samples), bars + 1).astype(int)
    raw = np.array(
        [float(np.max(np.abs(samples[a:b]))) if b > a else 0.0 for a, b in itertools.pairwise(edges)]
    )
    top = float(raw.max())
    if top <= 0.0:
        return [0.0] * bars
    return [round(float(v) / top, PEAK_DECIMALS) for v in raw]


def peaks_attr(peaks: list[float]) -> str:
    """Comma-separated integers 0..100 for the player's data attribute."""
    return ",".join(str(min(ATTR_SCALE, max(0, round(p * ATTR_SCALE)))) for p in peaks)
