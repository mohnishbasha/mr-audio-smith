"""narrate(): the whole pipeline for one page (FR-001 to FR-016, FR-026). Exposed via audio_smith.api."""

import os
import shlex
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from audio_smith import __version__
from audio_smith.api import (
    Fetcher,
    ScriptResult,
    _engine,
    _settings,
    resolve_profile,
    resolve_voice,
    write_script,
)
from audio_smith.blocks import BlockDoc
from audio_smith.config import Settings
from audio_smith.errors import AudioSmithError, ScriptInvalidError
from audio_smith.fetch import fetch
from audio_smith.llm import provider_label
from audio_smith.llm.base import LLMProvider
from audio_smith.master.tags import fetch_cover, http_get_bytes, write_tags
from audio_smith.pipeline import Progress, TrackJob, TrackOutput, produce_track
from audio_smith.proc import run_interactive
from audio_smith.publish.manifest import BackendRef, Manifest, ProfileRef, Timings, write_manifest
from audio_smith.script.markdown import Script, parse_script
from audio_smith.script.validate import validate
from audio_smith.tts.base import TTSBackend, VoiceRef

DEFAULT_EDITOR = "vi"


class NarrateResult(BaseModel):
    manifest_path: Path | None = None
    manifest: Manifest | None = None
    out_dir: Path
    tracks: list[TrackOutput] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    plan: list[str] = Field(default_factory=list)


def approve_script(path: Path, max_chars: int, editor: Callable[[Path], None] | None = None) -> Script:
    """Open the script in $EDITOR, then re-validate; the author's edits are the contract (US-003)."""
    if editor is None:
        cmd = shlex.split(os.environ.get("VISUAL") or os.environ.get("EDITOR") or DEFAULT_EDITOR)
        run_interactive([*cmd, str(path)])
    else:
        editor(path)
    script = parse_script(path.read_text(encoding="utf-8"))
    report = validate(script, max_chunk_chars=max_chars)
    if not report.ok:
        raise ScriptInvalidError(
            "Edited script is invalid", hint="Fix the listed chunks and re-run.", violations=report.errors
        )
    return script


def _tag(track: TrackOutput, doc: BlockDoc, source: str, settings: Settings) -> list[str]:
    album = doc.site_name or urlparse(source).netloc or "mr-audio-smith"
    cover = None
    if doc.image and source.startswith(("http://", "https://")):
        cover = fetch_cover(doc.image, source, lambda url: http_get_bytes(url, settings, max_bytes=1_048_576))
    write_tags(
        track.mp3,
        title=doc.title,
        artist=doc.author or album,
        album=album,
        date=(doc.date or datetime.now(UTC).date().isoformat())[:10],
        cover=cover,
    )
    if cover or not doc.image or not source.startswith(("http://", "https://")):
        return []
    return ["cover art skipped (not same-origin, too large, or unreachable)"]


def _plan_lines(res: ScriptResult) -> list[str]:
    lines = [f"blocks: {res.blocks_path} ({'cached' if res.cache_hits.get('blocks') else 'new'})"]
    for lang, path in res.scripts.items():
        lines.append(f"script {lang}: {path} ({'cached' if res.cache_hits.get('script') else 'generated'})")
    if res.parent_script:
        lines.append(f"parent script: {res.parent_script}")
    return lines


def _jobs(res: ScriptResult, script: Script, settings: Settings, profile: str | None) -> list[TrackJob]:
    prof = resolve_profile(profile, settings)
    jobs = [
        TrackJob(
            script=script,
            profile=prof,
            lang=script.meta.lang,
            kind="main",
            out_dir=res.out_dir,
            stem=res.slug,
        )
    ]
    if res.parent_script is not None and "parent" in prof.tracks:
        pscript = parse_script(res.parent_script.read_text(encoding="utf-8"))
        jobs.append(
            TrackJob(
                script=pscript,
                profile=resolve_profile(prof.tracks["parent"], settings),
                lang=pscript.meta.lang,
                kind="parent",
                out_dir=res.out_dir,
                stem=f"{res.slug}.parent",
            )
        )
    return jobs


def _manifest(
    res: ScriptResult,
    doc: BlockDoc,
    outputs: list[TrackOutput],
    engine: TTSBackend,
    voice: VoiceRef,
    llm: str,
    approved: bool,
    timings: Timings,
    warnings: list[str],
    profile_ref: str,
) -> Manifest:
    pid, _, ver = profile_ref.partition("@")
    chunks = outputs[0].chunks if outputs else []
    return Manifest(
        tool_version=__version__,
        source=doc.source,
        title=doc.title,
        profile=ProfileRef(id=pid, version=ver),
        backend=BackendRef(id=engine.id, model=engine.model),
        llm=provider_label(llm),
        voice_id=voice.id,
        content_hash=res.content_hash,
        created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        approved=approved,
        tracks=[o.track for o in outputs],
        chunks=chunks,
        timings=timings,
        warnings=warnings,
    )


def narrate(
    source: str,
    *,
    profile: str | None = None,
    voice: str | None = None,
    backend: str | None = None,
    out: Path | None = None,
    llm: str | None = None,
    approve: bool = False,
    force: bool = False,
    dry_run: bool = False,
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    tts: TTSBackend | None = None,
    fetcher: Fetcher = fetch,
    editor: Callable[[Path], None] | None = None,
    progress: Progress | None = None,
) -> NarrateResult:
    """Fetch, extract, script, synthesize, master, and publish one page; returns the manifest."""
    s = _settings(settings)
    engine, warnings = _engine(backend, tts, s)
    vref = resolve_voice(voice, engine, s)
    llm_spec = llm or s.llm
    res = write_script(
        source,
        profile=profile,
        llm=llm_spec,
        backend=engine.id,
        voice=vref.id,
        out=out,
        force=force,
        settings=s,
        provider=provider,
        fetcher=fetcher,
    )
    if res.doc is None:  # write_script always attaches it; guard keeps the type checker honest
        raise AudioSmithError("internal: extracted document missing")
    script = parse_script(res.scripts["en"].read_text(encoding="utf-8"))
    prof = resolve_profile(profile, s)
    if approve:
        script = approve_script(res.scripts["en"], prof.speech.max_chunk_chars, editor)
    if dry_run:
        return NarrateResult(out_dir=res.out_dir, plan=_plan_lines(res), warnings=warnings + res.warnings)
    outputs: list[TrackOutput] = []
    for job in _jobs(res, script, s, profile):
        out_track = produce_track(job, engine, vref, s, force=force, progress=progress, clock=time.monotonic)
        if not out_track.cached:
            out_track.warnings += _tag(out_track, res.doc, source, s)
        outputs.append(out_track)
    t_pub = time.monotonic()
    all_warnings = warnings + res.warnings + [w for o in outputs for w in o.warnings]
    timings = Timings(
        extract=res.timings.get("extract", 0.0),
        script=res.timings.get("script", 0.0),
        synth=sum(o.synth_s for o in outputs),
        master=sum(o.master_s for o in outputs),
    )
    manifest = _manifest(
        res, res.doc, outputs, engine, vref, llm_spec, approve, timings, all_warnings, prof.ref
    )
    manifest.timings.publish = round(time.monotonic() - t_pub, 3)
    path = write_manifest(res.out_dir / f"{res.slug}.manifest.json", manifest)
    return NarrateResult(
        manifest_path=path, manifest=manifest, out_dir=res.out_dir, tracks=outputs, warnings=all_warnings
    )
