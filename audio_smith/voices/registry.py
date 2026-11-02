"""On-disk voice registry and the resolver that gates cloning (ARCHITECTURE 5.5, ADR-010).

Layout: `{voices_dir}/{id}/voice.yaml`, `reference.wav`, `reference.24k.wav`, directory
0700 and files 0600 because clips are biometric-adjacent data. `resolve` is the single
place a voice id becomes a `VoiceRef`, so every front door inherits consent enforcement.
"""

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from audio_smith.config import Settings
from audio_smith.errors import AudioSmithError, ConsentError, UsageError
from audio_smith.paths import atomic_write
from audio_smith.tts.base import Capabilities, VoiceRef
from audio_smith.voices.clipcheck import ClipReport, check_clip, normalize_to_24k
from audio_smith.voices.consent import (
    ConsentRecord,
    file_sha256,
    load_record_data,
    parse_consent,
    reference_path,
    require_consent,
)

VOICE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
RECORD_FILE = "voice.yaml"
REFERENCE_FILE = "reference.wav"
REFERENCE_24K_FILE = "reference.24k.wav"
DIR_MODE = 0o700
FILE_MODE = 0o600
BROAD_BITS = 0o077
ADD_HINT = "mr-audio-smith voice add <id> --clip <wav> --name <speaker> --relationship self"


class ClipcheckInfo(BaseModel):
    duration_s: float
    sample_rate: int
    snr_db: float
    clipping_pct: float


class VoiceRecord(BaseModel):
    """Contents of voice.yaml."""

    id: str
    display_name: str
    backend_hints: list[str] = []
    reference: str = REFERENCE_FILE
    reference_text: str | None = None
    consent: ConsentRecord
    clipcheck: ClipcheckInfo
    clip_hash: str


class VoiceCheck(BaseModel):
    """Result of a full audit of one registered voice."""

    voice_id: str
    consent_error: str | None = None
    clip_problems: list[str] = []
    warnings: list[str] = []

    @property
    def ok(self) -> bool:
        return self.consent_error is None and not self.clip_problems


def _validate_id(voice_id: str) -> None:
    if not VOICE_ID_RE.match(voice_id):
        raise UsageError(
            f"Invalid voice id '{voice_id}'", hint="Use lowercase letters, digits, and hyphens (max 40)."
        )


def voice_dir(voices_dir: Path, voice_id: str) -> Path:
    _validate_id(voice_id)
    return voices_dir / voice_id


def _problem_text(problems: list[str]) -> str:
    return "; ".join(problems)


def add_voice(
    voices_dir: Path,
    voice_id: str,
    clip: Path,
    consent: ConsentRecord,
    *,
    display_name: str,
    reference_text: str | None = None,
    backend_hints: list[str] | None = None,
    replace: bool = False,
) -> VoiceRecord:
    """Validate the clip, store it with a normalized copy, and write the consent record."""
    target = voice_dir(voices_dir, voice_id)
    if target.exists() and not replace:
        raise UsageError(f"Voice '{voice_id}' already exists", hint="Pass --replace to overwrite it.")
    report = check_clip(clip)
    if not report.ok:
        raise UsageError(
            f"Reference clip rejected: {_problem_text(report.problems)}",
            hint="Record 3 to 30 s of clean, unclipped speech at 16 kHz or higher.",
        )
    raw = clip.read_bytes()
    voices_dir.mkdir(parents=True, exist_ok=True)
    target.mkdir(exist_ok=True)
    target.chmod(DIR_MODE)
    atomic_write(target / REFERENCE_FILE, raw, mode=FILE_MODE)
    with tempfile.TemporaryDirectory() as tmp:
        normalize_to_24k(clip, Path(tmp) / REFERENCE_24K_FILE)
        atomic_write(
            target / REFERENCE_24K_FILE, (Path(tmp) / REFERENCE_24K_FILE).read_bytes(), mode=FILE_MODE
        )
    record = VoiceRecord(
        id=voice_id,
        display_name=display_name,
        backend_hints=backend_hints or [],
        reference_text=reference_text,
        consent=consent,
        clipcheck=_info(report),
        clip_hash=file_sha256(target / REFERENCE_FILE),
    )
    text = yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    atomic_write(target / RECORD_FILE, text, mode=FILE_MODE)
    return record


def _info(report: ClipReport) -> ClipcheckInfo:
    return ClipcheckInfo(
        duration_s=report.duration_s,
        sample_rate=report.sample_rate,
        snr_db=report.snr_db,
        clipping_pct=report.clipping_pct,
    )


def get_voice(voices_dir: Path, voice_id: str) -> VoiceRecord:
    """Load one voice record; a missing voice is a UsageError, a broken one a ConsentError."""
    record_path = voice_dir(voices_dir, voice_id) / RECORD_FILE
    if not record_path.is_file():
        raise UsageError(f"Voice '{voice_id}' is not registered", hint=ADD_HINT)
    data = load_record_data(record_path)
    parse_consent(data, voice_id)
    try:
        return VoiceRecord.model_validate(data)
    except ValidationError as e:
        fields = ", ".join(sorted({".".join(str(p) for p in err["loc"]) for err in e.errors()}))
        raise ConsentError(f"Voice record for '{voice_id}' is invalid ({fields})", hint=ADD_HINT) from e


def scan_voices(voices_dir: Path) -> tuple[list[VoiceRecord], dict[str, str]]:
    """Return (valid records, {voice_id: reason}) for every directory in the registry."""
    valid: list[VoiceRecord] = []
    invalid: dict[str, str] = {}
    if not voices_dir.is_dir():
        return valid, invalid
    for child in sorted(voices_dir.iterdir()):
        if not child.is_dir():
            continue
        try:
            valid.append(get_voice(voices_dir, child.name))
        except AudioSmithError as e:
            invalid[child.name] = e.message
    return valid, invalid


def list_voices(voices_dir: Path) -> list[VoiceRecord]:
    return scan_voices(voices_dir)[0]


def remove_voice(voices_dir: Path, voice_id: str) -> None:
    """Delete a voice directory including its clips."""
    target = voice_dir(voices_dir, voice_id)
    if not target.is_dir():
        raise UsageError(f"Voice '{voice_id}' is not registered", hint=ADD_HINT)
    shutil.rmtree(target)


def _permission_warnings(target: Path, fix: bool) -> list[str]:
    """POSIX permission audit; native Windows has no mode bits (WSL2 is the supported path there)."""
    if os.name == "nt":
        return []
    warnings: list[str] = []
    for path, want in [(target, DIR_MODE), *((p, FILE_MODE) for p in sorted(target.iterdir()))]:
        if path.stat().st_mode & BROAD_BITS:
            if fix:
                path.chmod(want)
            warnings.append(
                f"{path.name} permissions are broader than {want:04o}" + (" (fixed)" if fix else "")
            )
    return warnings


def check_voice(voices_dir: Path, voice_id: str, *, fix_permissions: bool = False) -> VoiceCheck:
    """Re-run clip check, consent, hash, and permission audit for a registered voice."""
    target = voice_dir(voices_dir, voice_id)
    if not target.is_dir():
        raise UsageError(f"Voice '{voice_id}' is not registered", hint=ADD_HINT)
    result = VoiceCheck(voice_id=voice_id, warnings=_permission_warnings(target, fix_permissions))
    try:
        record_path = target / RECORD_FILE
        data = load_record_data(record_path)
        clip = reference_path(record_path, data)
        require_consent(_ref_from(record_path, data, voice_id))
        result.clip_problems = check_clip(clip).problems
    except ConsentError as e:
        result.consent_error = e.message
    except UsageError as e:
        result.clip_problems = [e.message]
    return result


def _ref_from(record_path: Path, data: dict[str, Any], voice_id: str) -> VoiceRef:
    clip_hash = data.get("clip_hash")
    return VoiceRef(
        id=voice_id,
        builtin=False,
        record_path=record_path,
        clip_hash=clip_hash if isinstance(clip_hash, str) else None,
    )


def resolve(voice_id: str, settings: Settings, caps: Capabilities) -> VoiceRef:
    """Turn a voice id into a VoiceRef, enforcing consent for anything that is cloned."""
    if voice_id in caps.builtin_voices:
        return VoiceRef(id=voice_id, builtin=True)
    if not caps.cloning:
        names = ", ".join(caps.builtin_voices) or "none"
        raise UsageError(
            f"Voice '{voice_id}' is not a built-in voice and this backend cannot clone",
            hint=f"Built-in voices: {names}.",
        )
    voices_dir = settings.resolved(settings.voices_dir)
    if not VOICE_ID_RE.match(voice_id) or not (voices_dir / voice_id / RECORD_FILE).is_file():
        raise ConsentError(f"Voice '{voice_id}' is not registered; cloning needs consent", hint=ADD_HINT)
    record = get_voice(voices_dir, voice_id)
    target = voices_dir / voice_id
    ref = VoiceRef(
        id=voice_id,
        builtin=False,
        reference_wav=target / REFERENCE_24K_FILE,
        reference_text=record.reference_text,
        clip_hash=record.clip_hash,
        record_path=target / RECORD_FILE,
    )
    require_consent(ref)
    return ref
