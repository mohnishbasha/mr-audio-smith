"""Studio review state: on-disk project layout, take bookkeeping, and the view models (FR-022).

Why a separate module: review.py and review_render.py both read and write `studio/state.json`;
keeping the layout and models here avoids a cycle and keeps each module small.
"""

import hashlib
import json
import re
import threading
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from audio_smith.errors import UsageError
from audio_smith.paths import atomic_write, ensure_inside
from audio_smith.publish.manifest import Track
from audio_smith.script.markdown import Chunk

STUDIO_DIR = "studio"
TAKES_DIR = "takes"
STATE_FILE = "state.json"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
HASH_LEN = 16
MEDIA_PREFIX = "/media"
STATE_LOCK = threading.RLock()
NS_PER_MS = 1_000_000
PEAK_SCALE = 100


class NotFoundError(UsageError):
    """A project, chunk, or take does not exist (HTTP 404)."""

    code = "not_found"
    http_status = 404


class TakeRecord(BaseModel):
    """One rendered alternative for a chunk, stored as `studio/takes/<chunk>-<take>.wav`."""

    take: int
    seed: int
    similarity: float | None = None
    duration_ms: int
    file: str
    text_hash: str = ""


class StudioState(BaseModel):
    """`studio/state.json`: selections, takes, and the chunks the author has edited since rendering."""

    selected: dict[str, int] = Field(default_factory=dict)
    takes: dict[str, list[TakeRecord]] = Field(default_factory=dict)
    stale: list[str] = Field(default_factory=list)
    failed: dict[str, str] = Field(default_factory=dict)


class ChunkEdit(BaseModel):
    """A chunk as sent by the editor."""

    id: str
    text: str
    verbatim: bool = False


class TakeView(BaseModel):
    take: int
    seed: int
    similarity: float | None
    duration_ms: int
    url: str


class ChunkView(BaseModel):
    id: str
    text: str
    verbatim: bool
    status: str
    selected_take: int | None
    takes: list[TakeView]


class TrackView(BaseModel):
    url: str
    captions_url: str | None
    duration_s: float
    loudness_lufs: float
    peaks: list[int]


class ProjectView(BaseModel):
    slug: str
    title: str
    source: str
    profile: str
    lang: str
    chunks: list[ChunkView]
    track: TrackView | None
    approved: bool
    warnings: list[str]


class ProjectSummary(BaseModel):
    slug: str
    title: str
    updated_at: str
    has_manifest: bool
    approved: bool


class SaveResult(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)


def text_hash(chunk: Chunk | str) -> str:
    """Short hash of a chunk's script text, used to tell whether a take is still current."""
    text = chunk if isinstance(chunk, str) else chunk.text
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:HASH_LEN]


def project_dir(out_dir: Path, slug: str) -> Path:
    """Directory of one project; the slug is validated so it cannot escape `out_dir`."""
    if not SLUG_RE.match(slug):
        raise NotFoundError(f"Unknown project {slug!r}")
    path = ensure_inside(out_dir, out_dir / slug)
    if not path.is_dir():
        raise NotFoundError(f"Unknown project {slug!r}", hint="Run `mr-audio-smith run` first.")
    return path


def script_path(directory: Path, slug: str) -> Path | None:
    """The main script: `<slug>.en.script.md` when present, else any non-parent `<slug>.*.script.md`."""
    preferred = directory / f"{slug}.en.script.md"
    if preferred.is_file():
        return preferred
    found = sorted(p for p in directory.glob(f"{slug}.*.script.md") if ".parent." not in p.name)
    return found[0] if found else None


def require_script(out_dir: Path, slug: str) -> tuple[Path, Path]:
    """Return (project dir, script path) or raise NotFoundError."""
    directory = project_dir(out_dir, slug)
    path = script_path(directory, slug)
    if path is None:
        raise NotFoundError(f"Project {slug!r} has no script", hint="Run `mr-audio-smith script` first.")
    return directory, path


def media_url(slug: str, relative: str, version: int = 0) -> str:
    """URL under /media; `version` busts the browser cache after a re-master."""
    suffix = f"?v={version}" if version else ""
    return f"{MEDIA_PREFIX}/{slug}/{relative}{suffix}"


def _state_path(directory: Path) -> Path:
    return directory / STUDIO_DIR / STATE_FILE


def load_state(directory: Path) -> StudioState:
    """Read state.json; a missing or corrupt file means no takes yet rather than a crash."""
    path = _state_path(directory)
    if not path.is_file():
        return StudioState()
    try:
        return StudioState.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ValidationError):
        return StudioState()


def save_state(directory: Path, state: StudioState) -> None:
    """Write state.json atomically."""
    atomic_write(_state_path(directory), state.model_dump_json(indent=2) + "\n")


def track_view(slug: str, directory: Path, track: Track) -> TrackView:
    """Project a manifest track into the Studio's JSON shape (peaks as integers 0..100)."""
    mp3 = directory / track.file
    version = mp3.stat().st_mtime_ns // NS_PER_MS if mp3.is_file() else 0
    return TrackView(
        url=media_url(slug, track.file, version),
        captions_url=media_url(slug, track.captions, version) if track.captions else None,
        duration_s=track.duration_s,
        loudness_lufs=track.loudness_lufs,
        peaks=[min(PEAK_SCALE, max(0, round(p * PEAK_SCALE))) for p in track.peaks],
    )
