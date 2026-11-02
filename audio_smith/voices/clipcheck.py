"""Reference clip quality gate and 24 kHz normalization (FR-011).

Bad clips make bad clones, so they are rejected at registration time with every problem
listed at once instead of failing mid-render.
"""

from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf
from pydantic import BaseModel

from audio_smith.errors import UsageError
from audio_smith.tts.base import to_float32

MIN_DURATION_S = 3.0
MAX_DURATION_S = 30.0
MIN_SAMPLE_RATE = 16_000
MAX_CLIPPING_PCT = 0.1
MIN_SNR_DB = 25.0
CLIP_LEVEL = 0.999
FRAME_S = 0.02
NOISE_PERCENTILE = 10
SIGNAL_PERCENTILE = 90
SNR_CAP_DB = 100.0
EPS = 1e-10
TARGET_RATE = 24_000
PEAK_DBFS = -1.0

F32 = npt.NDArray[np.float32]


class ClipReport(BaseModel):
    duration_s: float
    sample_rate: int
    channels: int
    snr_db: float
    clipping_pct: float
    problems: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def _read(path: Path) -> tuple[npt.NDArray[np.float32], int, int]:
    try:
        data, rate = sf.read(path, dtype="float32", always_2d=True)
    except (OSError, RuntimeError) as e:
        raise UsageError(f"Cannot read audio file {path.name}", hint="Use a PCM WAV or FLAC file.") from e
    return data, int(rate), int(data.shape[1])


def estimate_snr_db(mono: F32, rate: int) -> float:
    """Estimate SNR from frame RMS: quiet frames approximate noise, loud frames the speech."""
    frame = max(1, int(rate * FRAME_S))
    n = len(mono) // frame
    if n == 0:
        return 0.0
    rms = np.sqrt(np.mean(mono[: n * frame].reshape(n, frame).astype(np.float64) ** 2, axis=1))
    noise = max(float(np.percentile(rms, NOISE_PERCENTILE)), EPS)
    signal = max(float(np.percentile(rms, SIGNAL_PERCENTILE)), EPS)
    return min(SNR_CAP_DB, 20.0 * float(np.log10(signal / noise)))


def check_clip(path: Path) -> ClipReport:
    """Measure a clip and list every way it falls short of the voice-cloning requirements."""
    data, rate, channels = _read(path)
    mono = to_float32(data)
    duration = len(mono) / rate if rate else 0.0
    clipping = float(np.mean(np.abs(mono) >= CLIP_LEVEL) * 100.0) if len(mono) else 0.0
    snr = estimate_snr_db(mono, rate)
    problems: list[str] = []
    if duration < MIN_DURATION_S:
        problems.append(f"too short: {duration:.1f} s (minimum {MIN_DURATION_S:.0f} s)")
    if duration > MAX_DURATION_S:
        problems.append(f"too long: {duration:.1f} s (maximum {MAX_DURATION_S:.0f} s)")
    if rate < MIN_SAMPLE_RATE:
        problems.append(f"sample rate {rate} Hz is below {MIN_SAMPLE_RATE} Hz")
    if clipping >= MAX_CLIPPING_PCT:
        problems.append(f"clipping {clipping:.2f}% of samples (maximum {MAX_CLIPPING_PCT}%)")
    if snr < MIN_SNR_DB:
        problems.append(f"SNR about {snr:.1f} dB is below {MIN_SNR_DB:.0f} dB")
    return ClipReport(
        duration_s=round(duration, 3),
        sample_rate=rate,
        channels=channels,
        snr_db=round(snr, 1),
        clipping_pct=round(clipping, 4),
        problems=problems,
    )


def _resample(mono: F32, rate: int, target: int) -> F32:
    if rate == target:
        return mono
    if rate > target:
        spectrum = np.fft.rfft(mono)
        cutoff = int(len(spectrum) * target / rate)
        spectrum[cutoff:] = 0
        mono = np.fft.irfft(spectrum, n=len(mono)).astype(np.float32)
    n_out = round(len(mono) * target / rate)
    x_new = np.arange(n_out) * (rate / target)
    return np.interp(x_new, np.arange(len(mono)), mono).astype(np.float32)


def normalize_to_24k(src: Path, dst: Path) -> None:
    """Write a mono 24 kHz, peak -1 dBFS, PCM_16 copy used for synthesis and QA."""
    data, rate, _ = _read(src)
    out = _resample(to_float32(data), rate, TARGET_RATE)
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 0:
        out = out * np.float32(10 ** (PEAK_DBFS / 20) / peak)
    sf.write(dst, out, TARGET_RATE, subtype="PCM_16", format="WAV")
