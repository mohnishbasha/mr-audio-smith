"""MCP tool models and synchronous cores (FR-024, ADR-013).

Everything here is plain Python over `audio_smith.api`; the async MCP layer in `server.py`
runs these in worker threads. Cloned voices go through the same consent guard as the CLI:
the tools never bypass it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from audio_smith import api
from audio_smith.config import Settings, load_settings
from audio_smith.errors import UsageError
from audio_smith.llm.base import LLMProvider
from audio_smith.paths import ensure_inside
from audio_smith.pipeline import TrackOutput
from audio_smith.script.markdown import parse_script
from audio_smith.tts.base import TTSBackend
from audio_smith.tts.runner import ProgressEvent

WORDS_PER_MINUTE = 150
SCRIPT_LANG = "en"
PROGRESS_START = 0.1
PROGRESS_SYNTH_SPAN = 0.85
CONSENT_NOTE = (
    "Cloning requires a voice registered with a consent record (`mr-audio-smith voice add`); "
    "this tool never bypasses consent."
)

ProgressFn = Callable[[float, str], None]


class NarrateIn(BaseModel):
    """Input of mr_audio_smith_narrate."""

    source: str = Field(min_length=1, description="Page URL or local .html/.md path.")
    profile: str | None = Field(default=None, description="Audience profile id, e.g. kid-5.")
    voice: str | None = Field(default=None, description="Built-in or registered voice id.")
    backend: str | None = Field(default=None, description="TTS backend id, e.g. maya2, kokoro, mock.")
    langs: list[str] | None = Field(default=None, description="Language codes to produce.")
    inject_path: str | None = Field(
        default=None, description="HTML file under the server working directory to embed the player in."
    )


class TrackOut(BaseModel):
    lang: str
    file: str
    duration_s: float


class NarrateOut(BaseModel):
    manifest_path: str
    tracks: list[TrackOut]
    warnings: list[str]


class ScriptIn(BaseModel):
    source: str = Field(min_length=1, description="Page URL or local .html/.md path.")
    profile: str | None = Field(default=None, description="Audience profile id.")


class ScriptOut(BaseModel):
    script_path: str
    chunks: int
    est_minutes: float


class RenderIn(BaseModel):
    script_path: str = Field(min_length=1, description="Path to a Script Markdown file.")
    chunks: list[int] | None = Field(default=None, description="Chunk numbers to preview only.")
    voice: str | None = None
    backend: str | None = None


class RenderOut(BaseModel):
    files: list[str]


class VoiceInfo(BaseModel):
    id: str
    display_name: str
    backends: list[str]
    cloned: bool


class ProfileInfo(BaseModel):
    id: str
    version: str
    description: str


class BackendInfo(BaseModel):
    id: str
    available: bool
    languages: list[str]
    cloning: bool
    license: str


class StatusCheck(BaseModel):
    name: str
    status: str
    detail: str
    hint: str | None = None


class StatusOut(BaseModel):
    ok: bool
    checks: list[StatusCheck]
    cloud_providers_active: bool


class RecommendIn(BaseModel):
    source: str | None = None
    description: str | None = None


class RecommendOut(BaseModel):
    profile: str
    backend: str
    reason: str


@dataclass
class ToolEnv:
    """Injection points for tests; production leaves everything None."""

    settings: Settings | None = None
    provider: LLMProvider | None = None
    tts: TTSBackend | None = None
    cwd: Path | None = None

    def resolved_settings(self) -> Settings:
        return self.settings or load_settings()

    def root(self) -> Path:
        return (self.cwd or Path.cwd()).resolve()


def _track_out(out_dir: Path, t: TrackOutput) -> TrackOut:
    return TrackOut(
        lang=t.track.lang, file=str((out_dir / t.track.file).resolve()), duration_s=t.track.duration_s
    )


def _progress_adapter(progress: ProgressFn | None) -> Callable[[ProgressEvent], None] | None:
    if progress is None:
        return None

    def on_event(ev: ProgressEvent) -> None:
        frac = PROGRESS_START + PROGRESS_SYNTH_SPAN * (ev.done / max(ev.total, 1))
        progress(frac, f"{ev.stage} chunk {ev.chunk_id} ({ev.done}/{ev.total})")

    return on_event


def run_narrate(inp: NarrateIn, env: ToolEnv, progress: ProgressFn | None = None) -> NarrateOut:
    """Run the whole pipeline; `inject_path` must stay inside the working directory."""
    inject = ensure_inside(env.root(), env.root() / inp.inject_path) if inp.inject_path else None
    res = api.narrate(
        inp.source,
        profile=inp.profile,
        voice=inp.voice,
        backend=inp.backend,
        langs=inp.langs,
        inject=inject,
        settings=env.resolved_settings(),
        provider=env.provider,
        tts=env.tts,
        progress=_progress_adapter(progress),
    )
    if res.manifest_path is None:
        raise UsageError("Narration produced no manifest", hint="Do not use dry-run options.")
    return NarrateOut(
        manifest_path=str(res.manifest_path.resolve()),
        tracks=[_track_out(res.out_dir, t) for t in res.tracks],
        warnings=res.warnings,
    )


def run_script(inp: ScriptIn, env: ToolEnv) -> ScriptOut:
    """Stages 1 and 2: write the reviewable script."""
    res = api.write_script(
        inp.source,
        profile=inp.profile,
        settings=env.resolved_settings(),
        provider=env.provider,
    )
    path = res.scripts[SCRIPT_LANG].resolve()
    script = parse_script(path.read_text(encoding="utf-8"))
    words = sum(len(c.text.split()) for c in script.chunks)
    return ScriptOut(
        script_path=str(path), chunks=len(script.chunks), est_minutes=round(words / WORDS_PER_MINUTE, 1)
    )


def _script_file(raw: str, env: ToolEnv, settings: Settings) -> Path:
    """Scripts may live under the working directory or the configured output directory."""
    candidate = Path(raw).expanduser()
    for root in (env.root(), settings.out_dir.expanduser().resolve()):
        try:
            return ensure_inside(root, candidate if candidate.is_absolute() else root / candidate)
        except UsageError:
            continue
    raise UsageError(
        "Script path is outside the working and output directories", hint="Use a path the server can see."
    )


def run_render(inp: RenderIn, env: ToolEnv) -> RenderOut:
    """Render a script (or per-chunk previews when `chunks` is given)."""
    settings = env.resolved_settings()
    path = _script_file(inp.script_path, env, settings)
    res = api.render_script(
        path,
        chunks=[str(c) for c in inp.chunks] if inp.chunks else None,
        voice=inp.voice,
        backend=inp.backend,
        settings=settings,
        tts=env.tts,
    )
    files = [p.resolve() for p in res.chunk_files.values()]
    for t in res.tracks:
        files += [t.mp3.resolve(), t.vtt.resolve()]
    return RenderOut(files=[str(p) for p in files])
