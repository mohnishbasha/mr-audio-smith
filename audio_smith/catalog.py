"""Read-only summaries for front doors: voices, profiles, backends, readiness, script previews.

Why: REST and MCP both list the same things, so the shapes live in the core once.
"""

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from audio_smith.config import Settings
from audio_smith.doctor import check_ffmpeg
from audio_smith.errors import PreflightError, ScriptInvalidError
from audio_smith.fetch import FetchResult, fetch
from audio_smith.llm.base import LLMProvider
from audio_smith.preflight import PreflightIssue, has_errors
from audio_smith.profiles import load_all
from audio_smith.script.markdown import parse_script
from audio_smith.tts.base import Capabilities, TTSBackend
from audio_smith.tts.registry import BACKEND_IDS, get_backend
from audio_smith.voices import registry as voice_registry

WORDS_PER_MINUTE = 150
SCRATCH_DIR = "scratch"
Fetcher = Callable[[str, Settings], FetchResult]


class VoiceSummary(BaseModel):
    id: str
    display_name: str
    backends: list[str] = Field(default_factory=list)
    cloned: bool


class ProfileSummary(BaseModel):
    id: str
    version: str
    description: str


class BackendSummary(BaseModel):
    id: str
    available: bool
    languages: list[str] = Field(default_factory=list)
    cloning: bool = False
    license: str = ""


class ReadyReport(BaseModel):
    ok: bool
    checks: dict[str, str]
    failed: str | None = None
    detail: str = ""
    hint: str | None = None


class ScriptPreview(BaseModel):
    script_markdown: str
    chunks: int
    est_minutes: float
    content_hash: str


def _probe(backend_id: str, settings: Settings) -> tuple[TTSBackend | None, list[PreflightIssue]]:
    try:
        backend = get_backend(backend_id, settings)
        return backend, backend.preflight()
    except Exception as e:  # a broken optional backend must not break a listing
        return None, [PreflightIssue(severity="error", code="unavailable", message=str(e))]


def _capabilities(backend: TTSBackend | None) -> Capabilities | None:
    try:
        return backend.capabilities() if backend is not None else None
    except Exception:
        return None


def list_voices_summary(settings: Settings) -> list[VoiceSummary]:
    """Registered (cloned) voices first, then each backend's built-in voices."""
    valid, _ = voice_registry.scan_voices(settings.resolved(settings.voices_dir))
    voices = [
        VoiceSummary(id=v.id, display_name=v.display_name, backends=v.backend_hints, cloned=True)
        for v in valid
    ]
    builtin: dict[str, list[str]] = {}
    for bid in BACKEND_IDS:
        caps = _capabilities(_probe(bid, settings)[0])
        for vid in caps.builtin_voices if caps else []:
            builtin.setdefault(vid, []).append(bid)
    taken = {v.id for v in voices}
    voices += [
        VoiceSummary(id=vid, display_name=vid, backends=bids, cloned=False)
        for vid, bids in builtin.items()
        if vid not in taken
    ]
    return voices


def list_profiles_summary(settings: Settings) -> list[ProfileSummary]:
    profiles = load_all(settings.resolved(settings.profiles_dir))
    return [
        ProfileSummary(id=p.id, version=p.version, description=p.description)
        for p in sorted(profiles.values(), key=lambda p: p.id)
    ]


def list_backends_summary(settings: Settings) -> list[BackendSummary]:
    out: list[BackendSummary] = []
    for bid in BACKEND_IDS:
        backend, issues = _probe(bid, settings)
        caps = _capabilities(backend)
        out.append(
            BackendSummary(
                id=bid,
                available=backend is not None and not has_errors(issues),
                languages=caps.languages if caps else [],
                cloning=caps.cloning if caps else False,
                license=caps.license if caps else "",
            )
        )
    return out


def readiness(settings: Settings) -> ReadyReport:
    """Default backend preflight has no errors and ffmpeg is present (never raises)."""
    _, issues = _probe(settings.default_backend, settings)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        first = errors[0]
        return ReadyReport(
            ok=False,
            checks={"backend": "failed"},
            failed="backend",
            detail=first.message,
            hint=first.hint,
        )
    ffmpeg = check_ffmpeg(settings)
    if not ffmpeg.ok:
        return ReadyReport(
            ok=False,
            checks={"backend": "ok", "ffmpeg": "failed"},
            failed="ffmpeg",
            detail=ffmpeg.detail,
            hint=ffmpeg.hint,
        )
    return ReadyReport(ok=True, checks={"backend": "ok", "model": "loaded", "ffmpeg": "ok"})


def require_ready(settings: Settings) -> ReadyReport:
    """Like readiness but raises PreflightError naming the failed check."""
    report = readiness(settings)
    if not report.ok:
        raise PreflightError(f"Not ready: {report.failed}: {report.detail}", hint=report.hint)
    return report


def check_script_text(text: str) -> int:
    """Parse a Script Markdown document; returns the chunk count or raises ScriptInvalidError."""
    script = parse_script(text)
    if not script.chunks:
        raise ScriptInvalidError("Script has no chunks", hint="Each chunk starts with '## 001'.")
    return len(script.chunks)


def script_preview(
    source: str,
    settings: Settings,
    *,
    profile: str | None = None,
    llm: str | None = None,
    lang: str = "en",
    fetcher: Fetcher | None = None,
    provider: LLMProvider | None = None,
) -> ScriptPreview:
    """Stages 1 and 2 into a scratch directory; returns the script text and its summary."""
    from audio_smith import api  # noqa: PLC0415 - api imports this module

    scratch_root = settings.resolved(settings.out_dir) / SCRATCH_DIR
    scratch_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=scratch_root))
    try:
        res = api.write_script(
            source,
            profile=profile,
            llm=llm,
            lang=lang,
            out=work,
            settings=settings,
            provider=provider,
            fetcher=fetcher or fetch,
        )
        text = res.scripts[lang].read_text(encoding="utf-8")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    chunks = parse_script(text).chunks
    words = sum(len(c.text.split()) for c in chunks)
    return ScriptPreview(
        script_markdown=text,
        chunks=len(chunks),
        est_minutes=round(words / WORDS_PER_MINUTE, 2),
        content_hash=res.content_hash,
    )


def precheck_voice(voice: str | None, backend: str | None, settings: Settings) -> None:
    """Fail fast with ConsentError or UsageError when the requested voice cannot be used."""
    if voice is None:
        return
    engine = get_backend(backend or settings.default_backend, settings)
    voice_registry.resolve(voice, settings, engine.capabilities())
