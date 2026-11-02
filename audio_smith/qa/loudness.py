"""Cheap loudness probe for QA. Mastering measures LUFS with ffmpeg in a separate module."""

import numpy as np

from audio_smith.tts.base import FloatArray

SILENCE_DBFS = -120.0


def measure_rms_dbfs(samples: FloatArray) -> float:
    """RMS level in dBFS (full scale = 1.0); silence and empty input return SILENCE_DBFS.

    Why: a fast sanity check for clipped or near-silent takes without spawning ffmpeg.
    """
    if samples.size == 0:
        return SILENCE_DBFS
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
    if rms <= 0.0:
        return SILENCE_DBFS
    return max(SILENCE_DBFS, 20.0 * float(np.log10(rms)))
