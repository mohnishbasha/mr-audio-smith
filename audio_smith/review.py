"""Studio core (FR-022, US-003, US-004, US-017): list, load, edit, select, approve, and inject.

Why a core module: Studio is a front door and may call audio_smith.api only (Appendix I). These
functions hold the logic over `OUT/<slug>/` so the HTTP layer stays thin and testable without it.
Rendering and mastering live in review_render.py; both are re-exported by audio_smith.api.
"""

import re
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

from pydantic import BaseModel

from audio_smith.cache import CacheStore
from audio_smith.config import Settings
from audio_smith.errors import UsageError
from audio_smith.paths import atomic_write, ensure_inside
from audio_smith.profiles import get_profile
from audio_smith.publish.embed import PACKAGED_ASSET, REPO_DIST, EmbedOptions, render_embed
from audio_smith.publish.inject import inject, inject_file, unified_diff
from audio_smith.publish.manifest import Manifest, Track, write_manifest
from audio_smith.review_render import Context, manifest_path, plan_for, read_manifest
from audio_smith.review_state import (
    STATE_LOCK,
    ChunkEdit,
    ChunkView,
    NotFoundError,
    ProjectSummary,
    ProjectView,
    SaveResult,
    StudioState,
    TakeView,
    load_state,
    media_url,
    project_dir,
    require_script,
    save_state,
    script_path,
    text_hash,
    track_view,
)
from audio_smith.script.markdown import Chunk, Script, parse_script, serialize
from audio_smith.script.validate import validate
from audio_smith.tts.registry import get_backend
from audio_smith.voices import registry as voice_registry

MEDIA_SUFFIXES = frozenset({".mp3", ".vtt", ".wav", ".opus"})
DEFAULT_SELECTOR = "h1"
_BLANK_LINES = re.compile(r"\n{2,}")


class InjectOutcome(BaseModel):
    diff: str
    changed: bool


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def list_projects(out_dir: Path) -> list[ProjectSummary]:
    """Projects are directories holding a `<slug>.*.script.md`; newest first."""
    if not out_dir.is_dir():
        return []
    found: list[ProjectSummary] = []
    for directory in sorted(p for p in out_dir.iterdir() if p.is_dir()):
        spath = script_path(directory, directory.name)
        if spath is None:
            continue
        manifest = read_manifest(directory, directory.name)
        stamps = [spath.stat().st_mtime]
        if manifest is not None:
            stamps.append(manifest_path(directory, directory.name).stat().st_mtime)
        found.append(
            ProjectSummary(
                slug=directory.name,
                title=manifest.title if manifest else directory.name,
                updated_at=_iso(max(stamps)),
                has_manifest=manifest is not None,
                approved=bool(manifest and manifest.approved),
            )
        )
    return sorted(found, key=lambda p: p.updated_at, reverse=True)


def _cached_chunks(
    directory: Path, script: Script, manifest: Manifest | None, settings: Settings
) -> set[str]:
    """Chunk ids whose planned units are all in the synthesis cache for the narrated voice.

    Best effort and read-only (no backend preflight): when the backend or voice cannot be
    resolved, fall back to the manifest, which lists every chunk that was rendered.
    """
    fallback = {c.id for c in manifest.chunks} if manifest else set()
    if manifest is None:
        return fallback
    try:
        engine = get_backend(manifest.backend.id, settings)
        voice = voice_registry.resolve(manifest.voice_id, settings, engine.capabilities())
        profile = get_profile(script.meta.profile.split("@")[0], settings.profiles_dir)
        plan = plan_for(Context(script, profile, engine, voice, manifest))
    except Exception:
        return fallback
    cache = CacheStore(settings.cache_dir)
    keys: dict[str, list[str]] = {}
    for unit in plan.units:
        keys.setdefault(unit.chunk_id, []).append(unit.key)
    return {cid for cid, ks in keys.items() if all(cache.exists("chunks", k, "wav") for k in ks)}


def _status(chunk: Chunk, state: StudioState, cached: set[str]) -> str:
    """failed > a take matches the text > stale (edited or never rendered) > cached by the pipeline."""
    if chunk.id in state.failed:
        return "failed"
    takes = state.takes.get(chunk.id, [])
    if any(t.text_hash == text_hash(chunk) for t in takes):
        return "cached"
    if takes or chunk.id in state.stale:
        return "stale"
    return "cached" if chunk.id in cached else "stale"


def _chunk_view(slug: str, chunk: Chunk, state: StudioState, cached: set[str]) -> ChunkView:
    takes = [
        TakeView(
            take=t.take,
            seed=t.seed,
            similarity=t.similarity,
            duration_ms=t.duration_ms,
            url=media_url(slug, t.file),
        )
        for t in state.takes.get(chunk.id, [])
    ]
    return ChunkView(
        id=chunk.id,
        text=chunk.text,
        verbatim=chunk.verbatim,
        status=_status(chunk, state, cached),
        selected_take=state.selected.get(chunk.id),
        takes=takes,
    )


def main_track(manifest: Manifest | None, lang: str) -> Track | None:
    """The main track for the script's language (parent tracks are not edited in Studio)."""
    if manifest is None:
        return None
    mains = [t for t in manifest.tracks if t.kind == "main"]
    return next((t for t in mains if t.lang == lang), mains[0] if mains else None)


def load_project(out_dir: Path, slug: str, settings: Settings) -> ProjectView:
    """Everything the Studio needs to draw one project."""
    directory, spath = require_script(out_dir, slug)
    script = parse_script(spath.read_text(encoding="utf-8"))
    manifest = read_manifest(directory, slug)
    state = load_state(directory)
    cached = _cached_chunks(directory, script, manifest, settings)
    track = main_track(manifest, script.meta.lang)
    has_audio = track is not None and (directory / track.file).is_file()
    return ProjectView(
        slug=slug,
        title=manifest.title if manifest else slug,
        source=script.meta.source,
        profile=script.meta.profile,
        lang=script.meta.lang,
        chunks=[_chunk_view(slug, c, state, cached) for c in script.chunks],
        track=track_view(slug, directory, track) if track is not None and has_audio else None,
        approved=bool(manifest and manifest.approved),
        warnings=manifest.warnings if manifest else [],
    )


def _edited_script(old: Script, chunks: list[ChunkEdit]) -> tuple[Script | None, list[str]]:
    built: list[Chunk] = []
    errors: list[str] = []
    for c in chunks:
        if not c.id.isdigit():
            errors.append(f"chunk id {c.id!r} is not a number")
            continue
        text = _BLANK_LINES.sub("\n", c.text.strip())
        built.append(Chunk(number=int(c.id), text=text, verbatim=c.verbatim))
    return (None, errors) if errors else (old.model_copy(update={"chunks": built}), [])


def save_script(out_dir: Path, slug: str, chunks: list[ChunkEdit], settings: Settings) -> SaveResult:
    """Validate the edited chunks (FR-006) and, only when valid, rewrite the script atomically.

    Edited chunks become stale so the UI offers a re-render; errors leave the file untouched.
    """
    directory, spath = require_script(out_dir, slug)
    old = parse_script(spath.read_text(encoding="utf-8"))
    new, errors = _edited_script(old, chunks)
    if new is None:
        return SaveResult(ok=False, errors=errors)
    profile = get_profile(old.meta.profile.split("@")[0], settings.profiles_dir)
    report = validate(new, max_chunk_chars=profile.speech.max_chunk_chars)
    if not report.ok:
        return SaveResult(ok=False, errors=report.errors, warnings=report.warnings)
    before = {c.id: c.text for c in old.chunks}
    stale = [c.id for c in new.chunks if before.get(c.id) != c.text]
    with STATE_LOCK:
        atomic_write(spath, serialize(new))
        state = load_state(directory)
        state.stale = sorted(set(state.stale) | set(stale))
        save_state(directory, state)
    return SaveResult(ok=True, warnings=report.warnings, stale=stale)


def select_take(out_dir: Path, slug: str, chunk_id: str, take: int) -> None:
    """Mark a take as the one master_selected will use for this chunk."""
    directory = project_dir(out_dir, slug)
    cid = chunk_id.zfill(3)
    with STATE_LOCK:
        state = load_state(directory)
        if not any(t.take == take for t in state.takes.get(cid, [])):
            raise NotFoundError(f"Chunk {cid} has no take {take}")
        state.selected[cid] = take
        save_state(directory, state)


def approve(out_dir: Path, slug: str) -> None:
    """Persist `approved: true` in the manifest (US-003)."""
    directory = project_dir(out_dir, slug)
    manifest = read_manifest(directory, slug)
    if manifest is None:
        raise UsageError("Nothing to approve yet", hint="Render the project first.")
    manifest.approved = True
    write_manifest(manifest_path(directory, slug), manifest)


def inject_from_studio(
    project_root: Path,
    out_dir: Path,
    slug: str,
    path: str,
    selector: str | None,
    dry_run: bool,
) -> InjectOutcome:
    """Embed the player into a page of the project (FR-018); a dry run returns the diff only.

    The page must live inside `project_root`: Studio is a local tool, but the path still comes
    from the browser, so it is confined like every other write.
    """
    directory = project_dir(out_dir, slug)
    manifest = read_manifest(directory, slug)
    if manifest is None:
        raise UsageError("Nothing to embed yet", hint="Render the project first.")
    try:
        page = ensure_inside(project_root, project_root / path)
    except (ValueError, OSError) as e:
        raise UsageError(f"Invalid page path {path!r}") from e
    if not page.is_file():
        raise NotFoundError(f"No such page: {path}")
    snippet = render_embed(manifest, EmbedOptions())
    old = page.read_bytes().decode("utf-8")
    result = inject(old, snippet, selector=selector or DEFAULT_SELECTOR)
    label = page.relative_to(project_root.resolve()).as_posix()
    if result.changed and not dry_run:
        inject_file(page, snippet, selector=selector or DEFAULT_SELECTOR)
    return InjectOutcome(diff=unified_diff(old, result.html, label), changed=result.changed)


def media_path(out_dir: Path, slug: str, file: str) -> Path:
    """Resolve a /media request to a file inside the project, or refuse it."""
    directory = project_dir(out_dir, slug)
    try:
        target = ensure_inside(directory, directory / file)
    except (ValueError, OSError) as e:
        raise UsageError("Invalid media path") from e
    if target.suffix.lower() not in MEDIA_SUFFIXES or not target.is_file():
        raise NotFoundError("No such media file")
    return target


def player_bundle() -> Path | None:
    """The built `<audio-smith-player>` bundle (packaged asset, else the repo build), if present."""
    try:
        packaged = resources.files("audio_smith").joinpath(*PACKAGED_ASSET)
        if packaged.is_file():
            return Path(str(packaged))
    except (ModuleNotFoundError, FileNotFoundError):
        pass
    return REPO_DIST if REPO_DIST.is_file() else None
