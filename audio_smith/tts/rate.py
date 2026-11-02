"""Post-synthesis speaking rate via ffmpeg atempo (ADR-016).

Why: Maya 2 only accepts speed 1.0, and atempo keeps pitch stable, so every backend that
cannot change rate natively reuses this one function.
"""

import tempfile
from pathlib import Path

import soundfile as sf

from audio_smith import proc
from audio_smith.errors import SynthesisError
from audio_smith.tts.base import PcmAudio, to_float32

FFMPEG_TIMEOUT_S = 120.0
RATE_EPSILON = 1e-6
OUTPUT_CHANNELS = "1"


def apply_rate(pcm: PcmAudio, rate: float) -> PcmAudio:
    """Return pcm time-scaled by rate (>1 faster) using ffmpeg atempo, or pcm itself at 1.0."""
    if abs(rate - 1.0) < RATE_EPSILON:
        return pcm
    with tempfile.TemporaryDirectory(prefix="audio-smith-rate-") as tmp:
        src, dst = Path(tmp) / "in.wav", Path(tmp) / "out.wav"
        sf.write(str(src), pcm.samples, pcm.sample_rate, subtype="FLOAT")
        args = [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(src),
            "-filter:a", f"atempo={rate:g}", "-ar", str(pcm.sample_rate), "-ac", OUTPUT_CHANNELS, str(dst),
        ]  # fmt: skip
        try:
            proc.run(args, timeout=FFMPEG_TIMEOUT_S)
            data, sr = sf.read(str(dst), dtype="float32")
        except Exception as e:
            raise SynthesisError(
                f"ffmpeg atempo failed: {e}",
                hint="Install ffmpeg 6 or newer and re-run `mr-audio-smith doctor`.",
            ) from e
    return PcmAudio(samples=to_float32(data), sample_rate=int(sr))
