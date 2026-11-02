"""Environment checks so missing pieces surface before a run fails mid-way.

Each check is a small function from Settings to CheckResult. default_checks() composes the
core checks with the ones contributed by backends, LLM providers, and the voice registry.
"""

import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from audio_smith import proc
from audio_smith.config import Settings

MIN_PYTHON = (3, 12)
MIN_FFMPEG = (6, 0)
MIN_FREE_BYTES = 2 * 1024**3
FFMPEG_TIMEOUT_S = 10
FFMPEG_VERSION_RE = re.compile(r"ffmpeg version n?(\d+)\.(\d+)")


class CheckResult(BaseModel):
    name: str
    ok: bool
    required: bool = True
    detail: str = ""
    hint: str | None = None


class Check(BaseModel):
    name: str
    run: Callable[[Settings], CheckResult]


class DoctorReport(BaseModel):
    ok: bool
    results: list[CheckResult]


def check_python(_: Settings) -> CheckResult:
    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PYTHON
    return CheckResult(
        name="python",
        ok=ok,
        detail=f"{v.major}.{v.minor}.{v.micro}",
        hint=None if ok else "Install Python 3.12 or newer (uv python install 3.12).",
    )


def parse_ffmpeg_version(text: str) -> tuple[int, int] | None:
    m = FFMPEG_VERSION_RE.search(text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def ffmpeg_version(binary: str) -> tuple[int, int] | None:
    return parse_ffmpeg_version(
        proc.run([binary, "-version"], timeout=FFMPEG_TIMEOUT_S).decode(errors="replace")
    )


def check_ffmpeg(_: Settings) -> CheckResult:
    binary = shutil.which("ffmpeg")
    hint = "Install ffmpeg 6 or newer (brew install ffmpeg, apt install ffmpeg)."
    if binary is None:
        return CheckResult(name="ffmpeg", ok=False, detail="not found on PATH", hint=hint)
    ver = ffmpeg_version(binary)
    if ver is None or ver < MIN_FFMPEG:
        return CheckResult(name="ffmpeg", ok=False, detail=f"version {ver} too old or unknown", hint=hint)
    return CheckResult(name="ffmpeg", ok=True, detail=f"{ver[0]}.{ver[1]} at {binary}")


def check_cache_dir(settings: Settings) -> CheckResult:
    path = settings.resolved(settings.cache_dir)
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path):
            pass
    except OSError as e:
        return CheckResult(
            name="cache_dir",
            ok=False,
            detail=str(e),
            hint=f"Make {path} writable or set AUDIO_SMITH_CACHE_DIR.",
        )
    return CheckResult(name="cache_dir", ok=True, detail=str(path))


def _existing_parent(path: Path) -> Path:
    for p in [path, *path.parents]:
        if p.exists():
            return p
    return Path.cwd()


def check_disk(settings: Settings) -> CheckResult:
    free = shutil.disk_usage(_existing_parent(settings.resolved(settings.cache_dir))).free
    ok = free >= MIN_FREE_BYTES
    return CheckResult(
        name="disk_space",
        ok=ok,
        detail=f"{free / 1024**3:.1f} GiB free",
        hint=None if ok else "Free at least 2 GiB or run `mr-audio-smith cache prune --older-than 30d`.",
    )


def core_checks() -> list[Check]:
    return [
        Check(name="python", run=check_python),
        Check(name="ffmpeg", run=check_ffmpeg),
        Check(name="cache_dir", run=check_cache_dir),
        Check(name="disk_space", run=check_disk),
    ]


def default_checks() -> list[Check]:
    """Core checks plus contributions from later stages (backends, LLM, voices)."""
    from audio_smith.llm.checks import llm_check  # noqa: PLC0415

    return [*core_checks(), Check(name="llm", run=llm_check)]


def run_checks(settings: Settings, checks: list[Check]) -> DoctorReport:
    """Run every check; an exception inside a check is reported as a failure, never raised."""
    results: list[CheckResult] = []
    for check in checks:
        try:
            results.append(check.run(settings))
        except Exception as e:
            results.append(
                CheckResult(name=check.name, ok=False, detail=f"check crashed: {e}", hint="Report a bug.")
            )
    ok = all(r.ok for r in results if r.required)
    return DoctorReport(ok=ok, results=results)
