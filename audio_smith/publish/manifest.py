"""Manifest model for {slug}.manifest.json (ARCHITECTURE 5.4, FR-016).

Why a closed model: the manifest is safe by construction. It has no fields for
secrets, reference clip paths, or consent text, and extra fields are forbidden,
so none of them can be smuggled in.
"""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from audio_smith.paths import atomic_write

MANIFEST_SCHEMA = "audio-smith/manifest@1"
RFC3339_UTC = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"

Peak = Annotated[float, Field(ge=0.0, le=1.0)]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProfileRef(_Closed):
    id: str
    version: str


class BackendRef(_Closed):
    id: str
    model: str


class Track(_Closed):
    """One mastered audio track. `captions` is the relative WebVTT file name."""

    lang: str
    kind: Literal["main", "parent"]
    file: str
    duration_s: float
    loudness_lufs: float
    true_peak_dbtp: float
    peaks: list[Peak] = Field(default_factory=list)
    captions: str | None = None
    opus: str | None = None


class ChunkRecord(_Closed):
    id: str
    hash: str
    take: int
    seed: int
    similarity: float | None = None
    duration_ms: int


class Timings(_Closed):
    """Per-stage wall time in seconds (NFR-010)."""

    fetch: float = 0.0
    extract: float = 0.0
    script: float = 0.0
    synth: float = 0.0
    master: float = 0.0
    publish: float = 0.0


class Manifest(_Closed):
    schema_id: str = Field(default=MANIFEST_SCHEMA, alias="schema", pattern=r"^audio-smith/manifest@1$")
    tool_version: str
    source: str
    title: str
    profile: ProfileRef
    backend: BackendRef
    llm: str
    voice_id: str
    content_hash: str
    created_at: str = Field(pattern=RFC3339_UTC)
    approved: bool = False
    tracks: list[Track]
    chunks: list[ChunkRecord]
    timings: Timings = Field(default_factory=Timings)
    warnings: list[str] = Field(default_factory=list)


def write_manifest(path: Path, manifest: Manifest) -> Path:
    """Write the manifest as indented JSON using the `schema` alias, atomically."""
    return atomic_write(path, manifest.model_dump_json(by_alias=True, indent=2) + "\n")


def load_manifest(path: Path) -> Manifest:
    """Load and validate a manifest file."""
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
