"""Generate deterministic synthetic voice clips for the voice tests.

No real person is recorded: each clip is a sum of harmonics with a syllable-rate amplitude
envelope. Run `uv run python tests/fixtures/voices/generate.py` to regenerate the WAVs.
"""

from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

RATE = 24_000
SEED = 7
F0_HZ = 120.0
HARMONICS = 12
SYLLABLE_HZ = 3.0
PEAK = 0.5
CLEAN_NOISE_RMS = 1e-4
NOISY_SNR_DB = 10.0
CLIP_GAIN = 6.0
FRAME = RATE // 50
OUT_DIR = Path(__file__).parent

F64 = npt.NDArray[np.float64]


def speech_like(seconds: float) -> F64:
    """Harmonic tone with vibrato and silent gaps between syllables, peak-normalized."""
    t = np.arange(int(seconds * RATE)) / RATE
    phase = 2 * np.pi * (F0_HZ * t + 2.0 * np.sin(2 * np.pi * 5.0 * t) / 5.0)
    tone = sum(np.sin(h * phase) / h for h in range(1, HARMONICS + 1))
    env = np.clip(np.sin(2 * np.pi * SYLLABLE_HZ * t), 0.0, None) ** 1.5
    sig = np.asarray(tone * env, dtype=np.float64)
    return sig * (PEAK / float(np.max(np.abs(sig))))


def _loud_rms(sig: F64) -> float:
    frames = sig[: len(sig) // FRAME * FRAME].reshape(-1, FRAME)
    return float(np.percentile(np.sqrt(np.mean(frames**2, axis=1)), 90))


def _noise(n: int, rms: float, rng: np.random.Generator) -> F64:
    return rng.normal(0.0, rms, n)


def _write(name: str, data: F64) -> None:
    sf.write(OUT_DIR / name, np.clip(data, -1.0, 1.0), RATE, subtype="PCM_16")


def main() -> None:
    rng = np.random.default_rng(SEED)
    clean = speech_like(8.0)
    _write("clean.wav", clean + _noise(len(clean), CLEAN_NOISE_RMS, rng))
    _write("clipped.wav", clean * CLIP_GAIN + _noise(len(clean), CLEAN_NOISE_RMS, rng))
    noise_rms = _loud_rms(clean) / 10 ** (NOISY_SNR_DB / 20)
    _write("noisy.wav", clean + _noise(len(clean), noise_rms, rng))
    short = speech_like(1.5)
    _write("too-short.wav", short + _noise(len(short), CLEAN_NOISE_RMS, rng))


if __name__ == "__main__":
    main()
