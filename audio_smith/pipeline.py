"""Stages 3 to 5 for one script: synthesize, master, caption, tag. Called by audio_smith.api.

A finished track is cached under a key derived from every planned synthesis unit plus the
mastering settings, so an unchanged page skips synthesis, QA, and ffmpeg entirely (NFR-004).
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import soundfile as sf
from pydantic import BaseModel, Field

from audio_smith.cache import CacheStore
from audio_smith.cache.keys import track_key
from audio_smith.config import Settings
from audio_smith.master.assemble import assemble
from audio_smith.master.ffmpeg import master
from audio_smith.master.ffmpeg_graph import STING_GAP_S
from audio_smith.master.stings import resolve_sting
from audio_smith.paths import atomic_write
from audio_smith.pipeline_types import ChunkSpan, MasterResult, RenderedUnit
from audio_smith.profiles.schema import Profile
from audio_smith.publish.manifest import ChunkRecord, Track
from audio_smith.publish.vtt import write_vtt
from audio_smith.qa.similarity import RESEMBLYZER_MISSING_WARNING, SimilarityQA, load_embedder
from audio_smith.script import lexicon
from audio_smith.script.markdown import Script
from audio_smith.tts.base import SynthParams, TTSBackend, VoiceRef
from audio_smith.tts.planner import plan_units
from audio_smith.tts.runner import ProgressEvent, SynthesisRunner

HTTP_BACKENDS = {"maya2", "openai", "openai_compat"}
MASTERING_VERSION = "m1"
Progress = Callable[[ProgressEvent], None]


class TrackOutput(BaseModel):
    """A published track: files on disk plus the manifest entries that describe it."""

    track: Track
    chunks: list[ChunkRecord] = Field(default_factory=list)
    mp3: Path
    vtt: Path
    cached: bool = False
    warnings: list[str] = Field(default_factory=list)
    synth_s: float = 0.0
    master_s: float = 0.0


def project_lexicon(profile: Profile) -> dict[str, str]:
    return lexicon.merge(profile.lexicon, lexicon.load_project_lexicon(Path(lexicon.PROJECT_LEXICON)))


def build_qa(voice: VoiceRef, settings: Settings, profile: Profile) -> tuple[SimilarityQA | None, list[str]]:
    """Speaker similarity QA when the qa extra is installed; otherwise a manifest warning (ADR-015)."""
    embedder = load_embedder()
    if embedder is None:
        return None, [RESEMBLYZER_MISSING_WARNING]
    threshold = settings.qa_threshold if "qa_threshold" in settings.model_fields_set else profile.qa.threshold
    takes = profile.qa.takes_per_chunk
    if voice.builtin or voice.reference_wav is None:
        return SimilarityQA.reference_from_first(embedder, threshold, takes), []
    samples, rate = sf.read(voice.reference_wav, dtype="float32")
    return SimilarityQA.from_reference_clip(embedder, samples, int(rate), threshold, takes), []


def chunk_records(units: list[RenderedUnit]) -> list[ChunkRecord]:
    """One manifest record per chunk; the weakest unit's QA score represents the chunk."""
    records: dict[str, ChunkRecord] = {}
    for u in units:
        ms = round(1000 * len(u.samples) / u.sample_rate)
        rec = records.get(u.unit.chunk_id)
        if rec is None:
            records[u.unit.chunk_id] = ChunkRecord(
                id=u.unit.chunk_id,
                hash=u.unit.key,
                take=u.take,
                seed=u.seed or 0,
                similarity=u.similarity,
                duration_ms=ms,
            )
            continue
        rec.duration_ms += ms
        if u.similarity is not None and (rec.similarity is None or u.similarity < rec.similarity):
            rec.similarity, rec.take, rec.seed = u.similarity, u.take, u.seed or 0
    return list(records.values())


def _shift(spans: list[ChunkSpan], offset_ms: int) -> list[ChunkSpan]:
    return [
        s.model_copy(update={"start_ms": s.start_ms + offset_ms, "end_ms": s.end_ms + offset_ms})
        for s in spans
    ]


def _intro_offset_ms(intro: Path | None) -> int:
    if intro is None:
        return 0
    duration = float(sf.info(str(intro)).duration)
    return round(1000 * (duration + STING_GAP_S))


class TrackJob(BaseModel):
    """Everything needed to produce one track."""

    script: Script
    profile: Profile
    lang: str
    kind: str
    out_dir: Path
    stem: str
    opus: bool = False


def _cached_track(cache: CacheStore, key: str, job: TrackJob) -> TrackOutput | None:
    meta = cache.get_text("tracks", key, "json")
    mp3 = cache.path("tracks", key, "mp3")
    vtt = cache.path("tracks", key, "vtt")
    if meta is None or not mp3.is_file() or not vtt.is_file():
        return None
    out = TrackOutput.model_validate_json(meta)
    shutil.copyfile(mp3, job.out_dir / out.track.file)
    shutil.copyfile(vtt, job.out_dir / (out.track.captions or f"{job.stem}.vtt"))
    opus_src = cache.path("tracks", key, "opus")
    if out.track.opus and opus_src.is_file():
        shutil.copyfile(opus_src, job.out_dir / out.track.opus)
    return out.model_copy(
        update={
            "mp3": job.out_dir / out.track.file,
            "vtt": job.out_dir / f"{job.stem}.vtt",
            "cached": True,
            "synth_s": 0.0,
            "master_s": 0.0,
        }
    )


def _store_track(cache: CacheStore, key: str, out: TrackOutput, opus: Path | None) -> None:
    cache.put_bytes("tracks", key, "mp3", out.mp3.read_bytes())
    cache.put_bytes("tracks", key, "vtt", out.vtt.read_bytes())
    if opus is not None:
        cache.put_bytes("tracks", key, "opus", opus.read_bytes())
    cache.put_text("tracks", key, "json", out.model_dump_json())


def _mastering_signature(job: TrackJob) -> str:
    m = job.profile.mastering
    return json.dumps(
        [
            MASTERING_VERSION,
            m.intro_sting,
            m.outro_sting,
            m.music_bed,
            job.opus,
            job.profile.speech.pause_between_chunks_ms,
        ]
    )


def _master_units(
    units: list[RenderedUnit], job: TrackJob, project_root: Path
) -> tuple[MasterResult, Path, Path]:
    m = job.profile.mastering
    assembled = assemble(units, pause_between_chunks_ms=job.profile.speech.pause_between_chunks_ms)
    intro = resolve_sting(m.intro_sting, project_root)
    mp3 = job.out_dir / f"{job.stem}.mp3"
    result = master(
        assembled,
        mp3,
        intro=intro,
        outro=resolve_sting(m.outro_sting, project_root),
        music_bed=resolve_sting(m.music_bed, project_root),
        opus=job.opus,
    )
    vtt = write_vtt(job.out_dir / f"{job.stem}.vtt", _shift(assembled.spans, _intro_offset_ms(intro)))
    return result, mp3, vtt


def produce_track(
    job: TrackJob,
    engine: TTSBackend,
    voice: VoiceRef,
    settings: Settings,
    *,
    force: bool = False,
    progress: Progress | None = None,
    clock: Callable[[], float],
) -> TrackOutput:
    """Plan, synthesize (cached per unit), QA, assemble, master, and caption one track."""
    caps = engine.capabilities()
    plan = plan_units(
        job.script,
        max_chars=min(job.profile.speech.max_chunk_chars, caps.max_chars),
        lexicon=project_lexicon(job.profile),
        backend_id=engine.id,
        model=engine.model,
        voice=voice,
        rate=job.profile.speech.rate,
    )
    cache = CacheStore(settings.cache_dir)
    key = track_key([u.key for u in plan.units], _mastering_signature(job))
    job.out_dir.mkdir(parents=True, exist_ok=True)
    if not force and (hit := _cached_track(cache, key, job)) is not None:
        return hit
    t0 = clock()
    qa, warnings = build_qa(voice, settings, job.profile)
    concurrency = settings.synth_concurrency if engine.id in HTTP_BACKENDS else 1
    runner = SynthesisRunner(
        engine,
        voice,
        SynthParams(lang=job.lang, rate=job.profile.speech.rate),
        cache,
        concurrency=concurrency,
        progress=progress,
        qa=qa,
    )
    units = runner.run(plan.units)
    t1 = clock()
    result, mp3, vtt = _master_units(units, job, Path.cwd())
    track = Track(
        lang=job.lang,
        kind="parent" if job.kind == "parent" else "main",
        file=mp3.name,
        duration_s=round(result.duration_s, 3),
        loudness_lufs=round(result.loudness_lufs, 2),
        true_peak_dbtp=round(result.true_peak_dbtp, 2),
        peaks=result.peaks,
        captions=vtt.name,
        opus=result.opus_path.name if result.opus_path else None,
    )
    out = TrackOutput(
        track=track,
        chunks=chunk_records(units),
        mp3=mp3,
        vtt=vtt,
        warnings=plan.warnings + warnings + _qa_warnings(units, qa),
        synth_s=round(t1 - t0, 3),
        master_s=round(clock() - t1, 3),
    )
    _store_track(cache, key, out, result.opus_path)
    return out


def _qa_warnings(units: list[RenderedUnit], qa: SimilarityQA | None) -> list[str]:
    if qa is None:
        return []
    low = sorted(
        {u.unit.chunk_id for u in units if u.similarity is not None and not qa.acceptable(u.similarity)}
    )
    return [f"chunk {c}: speaker similarity below {qa.threshold} after all takes" for c in low]


def write_chunk_previews(units: list[RenderedUnit], out_dir: Path) -> dict[str, Path]:
    """Per-chunk WAV previews for `render --chunks` (no mastering)."""
    files: dict[str, Path] = {}
    for u in units:
        path = out_dir / "chunks" / f"{u.unit.chunk_id}-{u.unit.index:02d}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, u.samples, u.sample_rate, subtype="PCM_16")
        files.setdefault(u.unit.chunk_id, path)
    return files


def write_json(path: Path, data: object) -> Path:
    return atomic_write(path, json.dumps(data, indent=2) + "\n")
