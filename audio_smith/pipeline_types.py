"""Data passed between the synthesis, mastering, and publish stages (Sprint 3).

Kept in one small module so stage modules depend on these models, not on each other.
"""

from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from audio_smith.tts.base import FloatArray

MASTER_SAMPLE_RATE = 44_100


class SynthUnit(BaseModel):
    """One TTS call: a piece of a chunk between pause markers, after lexicon substitution."""

    chunk_id: str
    index: int
    text: str
    display_text: str
    pause_after_ms: int = 0
    key: str = ""


class RenderedUnit(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    unit: SynthUnit
    samples: FloatArray
    sample_rate: int
    take: int = 0
    seed: int | None = None
    similarity: float | None = None
    cached: bool = False


class ChunkSpan(BaseModel):
    """Where a chunk landed in the assembled track; VTT cues are derived from these."""

    chunk_id: str
    start_ms: int
    end_ms: int
    text: str


class AssembledTrack(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    samples: FloatArray
    sample_rate: int = MASTER_SAMPLE_RATE
    spans: list[ChunkSpan] = Field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return round(1000 * len(self.samples) / self.sample_rate)


class MasterResult(BaseModel):
    """A mastered audio file plus its measured loudness."""

    path: Path
    duration_s: float
    loudness_lufs: float
    true_peak_dbtp: float
    peaks: list[float] = Field(default_factory=list)
    opus_path: Path | None = None


def silence(ms: int, sample_rate: int) -> FloatArray:
    return np.zeros(round(sample_rate * ms / 1000), dtype=np.float32)
