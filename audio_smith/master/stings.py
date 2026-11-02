"""Resolve intro and outro stings from a profile spec."""

from importlib import resources
from pathlib import Path

from audio_smith.errors import MasteringError, UsageError
from audio_smith.paths import ensure_inside

BUILTIN_PREFIX = "builtin:"
STING_SUFFIX = ".wav"
PACKAGED_ASSETS = ("_assets", "stings")
REPO_STINGS = Path(__file__).resolve().parents[2] / "assets" / "stings"


def _builtin_dirs() -> list[Path]:
    """Installed package assets first, then the repo checkout."""
    dirs: list[Path] = []
    try:
        packaged = resources.files("audio_smith").joinpath(*PACKAGED_ASSETS)
        if packaged.is_dir():
            dirs.append(Path(str(packaged)))
    except (ModuleNotFoundError, OSError):  # pragma: no cover - defensive, package always importable
        pass
    dirs.append(REPO_STINGS)
    return dirs


def _builtin(name: str) -> Path:
    if not name or name != Path(name).name or name.startswith("."):
        raise MasteringError(
            f"Invalid built-in sting name '{name}'", hint="Use builtin:chime-soft or builtin:chime-bright."
        )
    for directory in _builtin_dirs():
        candidate = directory / f"{name}{STING_SUFFIX}"
        if candidate.is_file():
            return candidate
    raise MasteringError(f"Unknown built-in sting '{name}'", hint="Available: chime-soft, chime-bright.")


def resolve_sting(spec: str | None, project_root: Path) -> Path | None:
    """Return the audio file for a sting spec, or None when no sting is requested.

    Why: profiles are user-editable, so a relative path must stay inside the project root;
    otherwise a shared profile could make the mastering step read arbitrary files.
    """
    if not spec:
        return None
    if spec.startswith(BUILTIN_PREFIX):
        return _builtin(spec[len(BUILTIN_PREFIX) :])
    try:
        resolved = ensure_inside(project_root, project_root / spec)
    except UsageError as e:
        raise MasteringError(
            f"Sting path '{spec}' is outside the project", hint="Use a path inside the project folder."
        ) from e
    if not resolved.is_file():
        raise MasteringError(
            f"Sting file not found: {spec}", hint="Check the path in the profile's mastering block."
        )
    return resolved
