"""TTSBackend protocol and its data models (ARCHITECTURE 6.5).

The interface stays tiny (capabilities, preflight, synth). Model quirks such as marker
handling, voice registration, or rate application live in each backend's adapter.
"""

from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field

from audio_smith.preflight import PreflightIssue

FloatArray = npt.NDArray[np.float32]


class Capabilities(BaseModel):
    languages: list[str]
    cloning: bool
    builtin_voices: list[str]
    sample_rate: int
    max_chars: int
    streaming: bool
    license: str
    commercial_ok: bool


class VoiceRef(BaseModel):
    """A resolved voice. Cloned voices carry the consent record path so backends can re-check it."""

    id: str
    builtin: bool = False
    reference_wav: Path | None = None
    reference_text: str | None = None
    clip_hash: str | None = None
    record_path: Path | None = None
    lang: str = "en"


class SynthParams(BaseModel):
    lang: str = "en"
    rate: float = Field(default=1.0, ge=0.5, le=2.0)
    seed: int | None = None
    temperature: float | None = None
    top_k: int | None = None
    top_p: float | None = None
    repetition_penalty: float | None = None
    normalize: bool = True


class PcmAudio(BaseModel):
    """Mono float32 samples in -1.0..1.0."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    samples: FloatArray
    sample_rate: int

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.sample_rate if self.sample_rate else 0.0


class TTSBackend(Protocol):
    id: str
    model: str

    def capabilities(self) -> Capabilities: ...
    def preflight(self) -> list[PreflightIssue]: ...
    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio: ...


def to_float32(samples: npt.NDArray[np.generic]) -> FloatArray:
    """Convert int16/int32/float64 or multichannel arrays to mono float32 in -1..1."""
    arr = np.asarray(samples)
    if arr.ndim == 2:
        arr = arr.mean(axis=1)
    if np.issubdtype(arr.dtype, np.integer):
        full_scale = float(2 ** (arr.dtype.itemsize * 8 - 1) - 1)
        arr = arr.astype(np.float32) / full_scale
    return np.clip(arr.astype(np.float32), -1.0, 1.0)
