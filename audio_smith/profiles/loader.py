"""Load profiles: project ./profiles overrides built-ins of the same id (FR-004)."""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from audio_smith.errors import UsageError
from audio_smith.profiles.schema import Profile

BUILTIN_IDS = ("kid-5", "kid-8", "adult-commute", "adult-brief")


def _format_errors(source: str, err: ValidationError) -> str:
    lines = [f"Invalid profile {source}:"]
    for e in err.errors():
        path = ".".join(str(p) for p in e["loc"]) or "<root>"
        lines.append(f"  {path}: {e['msg']}")
    return "\n".join(lines)


def parse_profile(text: str, source: str) -> Profile:
    """Validate YAML text; errors name every failing field path."""
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise UsageError(f"Invalid YAML in {source}: {e}", hint="Fix the YAML syntax.") from e
    if not isinstance(data, dict):
        raise UsageError(
            f"Invalid profile {source}: top level must be a mapping", hint="See docs/ARCHITECTURE.md 5.3."
        )
    try:
        return Profile.model_validate(data)
    except ValidationError as e:
        raise UsageError(_format_errors(source, e), hint="See docs/ARCHITECTURE.md section 5.3.") from e


def load_file(path: Path) -> Profile:
    return parse_profile(path.read_text(encoding="utf-8"), str(path))


def _builtin_texts() -> dict[str, str]:
    base = files("audio_smith.profiles") / "builtin"
    return {pid: (base / f"{pid}.yaml").read_text(encoding="utf-8") for pid in BUILTIN_IDS}


def load_all(project_dir: Path | None = None) -> dict[str, Profile]:
    """All profiles by id; project files win over built-ins with the same id."""
    profiles = {pid: parse_profile(text, f"builtin:{pid}") for pid, text in _builtin_texts().items()}
    if project_dir is not None and project_dir.is_dir():
        for path in sorted(project_dir.glob("*.y*ml")):
            p = load_file(path)
            profiles[p.id] = p
    return profiles


def get_profile(ref: str, project_dir: Path | None = None) -> Profile:
    """Resolve `id` or `id@version`; a pinned version must match exactly."""
    pid, _, version = ref.partition("@")
    profiles = load_all(project_dir)
    if pid not in profiles:
        raise UsageError(f"Unknown profile '{pid}'", hint=f"Known profiles: {', '.join(sorted(profiles))}")
    profile = profiles[pid]
    if version and version != profile.version:
        raise UsageError(
            f"Profile {pid} is version {profile.version}, not {version}", hint="Drop the @version pin."
        )
    for kind, target in profile.tracks.items():
        if target not in profiles:
            raise UsageError(f"Profile {pid} track '{kind}' references unknown profile '{target}'")
    return profile


def json_schema() -> str:
    """JSON Schema for profile YAML, published at schemas/profile.schema.json."""
    schema = Profile.model_json_schema(by_alias=True)
    schema["$id"] = "https://getaudiosmith.com/schemas/profile.schema.json"
    schema["title"] = "audio-smith/profile@1"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"
