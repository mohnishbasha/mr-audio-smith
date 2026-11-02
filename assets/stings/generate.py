"""Procedurally generate the two bundled CC0 chimes (original, no samples used).

Run `python assets/stings/generate.py` to rewrite chime-soft.wav and chime-bright.wav.
Output is deterministic: 44.1 kHz mono PCM_16.
"""

from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 44_100
PEAK = 0.5
# (frequency Hz, onset s, decay time constant s) per note.
SOFT_NOTES = ((659.25, 0.0, 0.35), (880.0, 0.25, 0.4))
SOFT_SECONDS = 1.2
BRIGHT_NOTES = ((1046.5, 0.0, 0.18), (1318.5, 0.2, 0.18), (1568.0, 0.4, 0.22))
BRIGHT_SECONDS = 1.0
HARMONICS = ((1.0, 1.0), (2.76, 0.25), (5.4, 0.08))  # bell-like inharmonic partials
ATTACK_S = 0.004
TAIL_FADE_S = 0.02


def _note(freq: float, tau: float, length: int) -> np.ndarray:
    t = np.arange(length) / SAMPLE_RATE
    tone = sum(amp * np.sin(2 * np.pi * freq * mult * t) for mult, amp in HARMONICS)
    env = np.exp(-t / tau) * np.minimum(1.0, t / ATTACK_S)
    return np.asarray(tone * env)


def render(notes: tuple[tuple[float, float, float], ...], seconds: float) -> np.ndarray:
    """Mix the notes into one mono buffer, normalized to PEAK with a short tail fade."""
    total = round(SAMPLE_RATE * seconds)
    out = np.zeros(total)
    for freq, onset, tau in notes:
        start = round(SAMPLE_RATE * onset)
        out[start:] += _note(freq, tau, total - start)
    out *= PEAK / float(np.max(np.abs(out)))
    fade = round(SAMPLE_RATE * TAIL_FADE_S)
    out[-fade:] *= np.linspace(1.0, 0.0, fade)
    return out


def main(out_dir: Path | None = None) -> None:
    target = out_dir or Path(__file__).parent
    for name, notes, seconds in (
        ("chime-soft", SOFT_NOTES, SOFT_SECONDS),
        ("chime-bright", BRIGHT_NOTES, BRIGHT_SECONDS),
    ):
        sf.write(target / f"{name}.wav", render(notes, seconds), SAMPLE_RATE, subtype="PCM_16")


if __name__ == "__main__":
    main()
