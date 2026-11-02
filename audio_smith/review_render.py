"""Studio rendering: per-chunk takes and re-mastering from the selected takes (FR-022, US-017).

Why here and not in a front door: voice resolution (consent), planning, synthesis, and mastering
are pipeline concerns; Studio only calls these through audio_smith.api.
"""

import io
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import soundfile as sf

from audio_smith.cache import CacheStore
from audio_smith.config import Settings
from audio_smith.errors import AudioSmithError, UsageError
from audio_smith.master.assemble import resample
from audio_smith.master.tags import write_tags
from audio_smith.paths import atomic_write
from audio_smith.pipeline import (
    TrackJob,
    build_qa,
    chunk_records,
    master_units,
    project_lexicon,
)
from audio_smith.pipeline_types import RenderedUnit, SynthUnit
from audio_smith.profiles.schema import Profile
from audio_smith.publish.manifest import Manifest, Track, load_manifest, write_manifest
from audio_smith.review_state import (
    STATE_LOCK,
    STUDIO_DIR,
    TAKES_DIR,
    NotFoundError,
    StudioState,
    TakeRecord,
    TakeView,
    TrackView,
    load_state,
    media_url,
    require_script,
    save_state,
    text_hash,
    track_view,
)
from audio_smith.script.markdown import Script, parse_script
from audio_smith.tts.base import FloatArray, SynthParams, TTSBackend, VoiceRef
from audio_smith.tts.planner import PlanResult, plan_units
from audio_smith.tts.runner import SynthesisRunner

MS_PER_S = 1000
WAV_SUBTYPE = "PCM_16"
DEFAULT_STEM_LANG = "en"


class Context:
    """Everything a render or master call needs, resolved once."""

    def __init__(
        self, script: Script, profile: Profile, engine: TTSBackend, voice: VoiceRef, manifest: Manifest | None
    ) -> None:
        self.script, self.profile, self.engine, self.voice, self.manifest = (
            script,
            profile,
            engine,
            voice,
            manifest,
        )


def manifest_path(directory: Path, slug: str) -> Path:
    return directory / f"{slug}.manifest.json"


def read_manifest(directory: Path, slug: str) -> Manifest | None:
    path = manifest_path(directory, slug)
    return load_manifest(path) if path.is_file() else None


def build_context(
    out_dir: Path,
    slug: str,
    settings: Settings,
    *,
    tts: TTSBackend | None = None,
    voice: str | None = None,
) -> tuple[Path, Context]:
    """Resolve script, profile, backend, and voice. Consent is enforced by resolve_voice.

    Why manifest first: the backend and voice that narrated the track stay in force, so a
    re-rendered chunk sounds like its neighbours. The settings are the fallback.
    """
    from audio_smith import api  # noqa: PLC0415 - api re-exports this module

    directory, spath = require_script(out_dir, slug)
    script = parse_script(spath.read_text(encoding="utf-8"))
    manifest = read_manifest(directory, slug)
    profile = api.resolve_profile(script.meta.profile.split("@")[0], settings)
    backend_id = manifest.backend.id if manifest else settings.default_backend
    engine, _ = api._engine(backend_id, tts, settings)
    vref = api.resolve_voice(voice or (manifest.voice_id if manifest else None), engine, settings)
    return directory, Context(script, profile, engine, vref, manifest)


def plan_for(ctx: Context, *, seed_base: int = 0, chunks: set[str] | None = None) -> PlanResult:
    """Plan units exactly as produce_track does, optionally for a subset and a seed."""
    caps = ctx.engine.capabilities()
    return plan_units(
        ctx.script,
        max_chars=min(ctx.profile.speech.max_chunk_chars, caps.max_chars),
        lexicon=project_lexicon(ctx.profile),
        backend_id=ctx.engine.id,
        model=ctx.engine.model,
        voice=ctx.voice,
        rate=ctx.profile.speech.rate,
        seed_base=seed_base,
        chunks=chunks,
    )


def _runner(ctx: Context, settings: Settings, seed: int, *, single_take: bool) -> SynthesisRunner:
    qa, _ = build_qa(ctx.voice, settings, ctx.profile)
    if qa is not None and single_take:
        qa.takes_per_chunk = 1  # one seed is one take; Studio lets the author compare
    params = SynthParams(lang=ctx.script.meta.lang, rate=ctx.profile.speech.rate, seed=seed)
    return SynthesisRunner(ctx.engine, ctx.voice, params, CacheStore(settings.cache_dir), qa=qa)


def next_seed(takes: list[TakeRecord]) -> int:
    """Smallest non-negative seed no take of this chunk used (seed 0 is the pipeline's own render)."""
    used = {t.seed for t in takes}
    return next(n for n in range(len(used) + 1) if n not in used)


def join_units(units: list[RenderedUnit]) -> tuple[FloatArray, int]:
    """Concatenate a chunk's units with their internal pauses into one waveform."""
    rate = units[0].sample_rate
    parts: list[FloatArray] = []
    for i, ru in enumerate(units):
        parts.append(resample(np.asarray(ru.samples, dtype=np.float32), ru.sample_rate, rate))
        if i < len(units) - 1 and ru.unit.pause_after_ms > 0:
            parts.append(np.zeros(round(rate * ru.unit.pause_after_ms / MS_PER_S), dtype=np.float32))
    return np.concatenate(parts).astype(np.float32), rate


def _similarity(units: list[RenderedUnit]) -> float | None:
    scores = [u.similarity for u in units if u.similarity is not None]
    return round(min(scores), 4) if scores else None


def _record_failure(directory: Path, chunk_id: str, error: AudioSmithError) -> None:
    with STATE_LOCK:
        state = load_state(directory)
        state.failed[chunk_id] = error.message
        save_state(directory, state)


def _store_take(directory: Path, chunk: str, chash: str, seed: int, units: list[RenderedUnit]) -> TakeRecord:
    samples, rate = join_units(units)
    buf = io.BytesIO()
    sf.write(buf, samples, rate, format="WAV", subtype=WAV_SUBTYPE)
    with STATE_LOCK:
        state = load_state(directory)
        existing = state.takes.setdefault(chunk, [])
        number = max((t.take for t in existing), default=0) + 1
        relative = f"{STUDIO_DIR}/{TAKES_DIR}/{chunk}-{number}.wav"
        atomic_write(directory / relative, buf.getvalue())
        record = TakeRecord(
            take=number,
            seed=seed,
            similarity=_similarity(units),
            duration_ms=round(MS_PER_S * len(samples) / rate),
            file=relative,
            text_hash=chash,
        )
        existing.append(record)
        if chunk in state.stale:
            state.stale.remove(chunk)
        state.failed.pop(chunk, None)
        save_state(directory, state)
    return record


def render_take(
    out_dir: Path,
    slug: str,
    chunk_id: str,
    settings: Settings,
    *,
    seed: int | None = None,
    tts: TTSBackend | None = None,
    voice: str | None = None,
) -> TakeView:
    """Synthesize one chunk with a fresh seed and store it as a new take (US-004, US-017).

    Raises:
        NotFoundError: Unknown project or chunk.
        ConsentError: The voice is cloned and not registered (via resolve_voice).
        SynthesisError: The backend failed; the chunk is marked failed in state.json.
    """
    directory, ctx = build_context(out_dir, slug, settings, tts=tts, voice=voice)
    cid = chunk_id.zfill(3)
    if cid not in {c.id for c in ctx.script.chunks}:
        raise NotFoundError(f"Unknown chunk {cid!r}")
    chosen = seed if seed is not None else next_seed(load_state(directory).takes.get(cid, []))
    plan = plan_for(ctx, seed_base=chosen, chunks={cid})
    if not plan.units:
        raise UsageError(f"Chunk {cid} has no spoken text", hint="Add text to the chunk before rendering.")
    try:
        units = _runner(ctx, settings, chosen, single_take=True).run(plan.units)
    except AudioSmithError as e:
        _record_failure(directory, cid, e)
        raise
    rec = _store_take(directory, cid, text_hash(ctx.script.chunk(cid)), chosen, units)
    return TakeView(
        take=rec.take,
        seed=rec.seed,
        similarity=rec.similarity,
        duration_ms=rec.duration_ms,
        url=media_url(slug, rec.file),
    )


def _selected_unit(
    directory: Path, ctx: Context, state: StudioState, chunk_id: str, planned: list[SynthUnit]
) -> RenderedUnit | None:
    """The selected take as one unit, or None when it is missing or no longer matches the text."""
    take = state.selected.get(chunk_id)
    rec = next((t for t in state.takes.get(chunk_id, []) if t.take == take), None)
    if rec is None or rec.text_hash != text_hash(ctx.script.chunk(chunk_id)):
        return None
    path = directory / rec.file
    if not path.is_file():
        return None
    samples, rate = sf.read(path, dtype="float32")
    unit = SynthUnit(
        chunk_id=chunk_id,
        index=0,
        text=" ".join(u.text for u in planned),
        display_text=" ".join(u.display_text for u in planned),
        pause_after_ms=planned[-1].pause_after_ms,
        key=planned[0].key,
    )
    return RenderedUnit(
        unit=unit, samples=samples, sample_rate=int(rate), take=rec.take, seed=rec.seed,
        similarity=rec.similarity,
    )  # fmt: skip


def gather_units(directory: Path, ctx: Context, settings: Settings, state: StudioState) -> list[RenderedUnit]:
    """Selected takes where valid; otherwise a fresh (cache-first) render of the current text."""
    plan = plan_for(ctx)
    grouped: dict[str, list[SynthUnit]] = {}
    for u in plan.units:
        grouped.setdefault(u.chunk_id, []).append(u)
    chosen = {cid: _selected_unit(directory, ctx, state, cid, planned) for cid, planned in grouped.items()}
    missing = [u for cid, planned in grouped.items() if chosen[cid] is None for u in planned]
    fresh: dict[str, list[RenderedUnit]] = {}
    if missing:
        for ru in _runner(ctx, settings, 0, single_take=False).run(missing):
            fresh.setdefault(ru.unit.chunk_id, []).append(ru)
    out: list[RenderedUnit] = []
    for chunk in ctx.script.chunks:
        pick = chosen.get(chunk.id)
        out.extend([pick] if pick is not None else fresh.get(chunk.id, []))
    return out


def _update_manifest(
    directory: Path, slug: str, ctx: Context, track: Track, units: list[RenderedUnit]
) -> None:
    manifest = ctx.manifest
    if manifest is None:
        return
    same = [(t.kind, t.lang) == (track.kind, track.lang) for t in manifest.tracks]
    manifest.tracks = [track if hit else t for t, hit in zip(manifest.tracks, same, strict=True)]
    if not any(same):
        manifest.tracks.append(track)
    if manifest.tracks[0] is track:
        manifest.chunks = chunk_records(units)
    manifest.approved = False
    write_manifest(manifest_path(directory, slug), manifest)


def _stem(slug: str, ctx: Context) -> str:
    lang = ctx.script.meta.lang
    if ctx.manifest:
        main = next((t for t in ctx.manifest.tracks if t.kind == "main" and t.lang == lang), None)
        if main:
            return Path(main.file).stem
    return slug if lang == DEFAULT_STEM_LANG else f"{slug}.{lang}"


def master_selected(out_dir: Path, slug: str, settings: Settings) -> TrackView:
    """Re-master the project from the selected takes (US-017); writes MP3, VTT, and the manifest.

    Chunks without a valid selected take are rendered fresh (cache first), so the result always
    matches the script on disk. Re-mastering resets approval because the audio changed.
    """
    directory, ctx = build_context(out_dir, slug, settings)
    units = gather_units(directory, ctx, settings, load_state(directory))
    job = TrackJob(
        script=ctx.script,
        profile=ctx.profile,
        lang=ctx.script.meta.lang,
        kind="main",
        out_dir=directory,
        stem=_stem(slug, ctx),
    )
    result, mp3, vtt = master_units(units, job, Path.cwd())
    track = Track(
        lang=job.lang,
        kind="main",
        file=mp3.name,
        duration_s=round(result.duration_s, 3),
        loudness_lufs=round(result.loudness_lufs, 2),
        true_peak_dbtp=round(result.true_peak_dbtp, 2),
        peaks=result.peaks,
        captions=vtt.name,
    )
    _tag(mp3, ctx)
    _update_manifest(directory, slug, ctx, track, units)
    return track_view(slug, directory, track)


def _tag(mp3: Path, ctx: Context) -> None:
    """Mastering writes a bare MP3; restore the basic tags the pipeline wrote."""
    if ctx.manifest is None:
        return
    album = urlparse(ctx.manifest.source).netloc or "mr-audio-smith"
    write_tags(
        mp3,
        title=ctx.manifest.title,
        artist=album,
        album=album,
        date=datetime.now(UTC).date().isoformat(),
        cover=None,
    )
