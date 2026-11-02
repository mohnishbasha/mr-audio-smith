"""Consent model and the guard every cloning path must pass (ADR-010).

Backends call `require_consent` right before cloning. It re-reads the on-disk voice record
instead of trusting the `VoiceRef`, so a hand-built reference cannot bypass consent. Error
messages never include the consent statement text.
"""

import datetime as dt
import hashlib
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError, field_validator

from audio_smith.errors import ConsentError
from audio_smith.tts.base import VoiceRef

MIN_STATEMENT_CHARS = 20
HASH_CHUNK_BYTES = 1024 * 1024
DEFAULT_SELF_STATEMENT = "This is my own voice. I consent to mr-audio-smith cloning it for narration."
CONSENT_HINT = "Register the voice with `mr-audio-smith voice add <id> --clip <wav> --name <speaker> ...`."


class ConsentRecord(BaseModel):
    """Who the voice belongs to and why cloning it is allowed."""

    speaker_name: str
    relationship: Literal["self", "written_permission"]
    statement: str
    date: dt.date

    @field_validator("speaker_name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("speaker_name must not be empty")
        return v.strip()

    @field_validator("statement")
    @classmethod
    def _statement_long_enough(cls, v: str) -> str:
        if len(v.strip()) < MIN_STATEMENT_CHARS:
            raise ValueError(f"statement must be at least {MIN_STATEMENT_CHARS} characters")
        return v.strip()

    @field_validator("date")
    @classmethod
    def _date_not_future(cls, v: dt.date) -> dt.date:
        if v > dt.date.today():
            raise ValueError("date must not be in the future")
        return v


def file_sha256(path: Path) -> str:
    """Hex SHA-256 of a file, streamed so large clips stay cheap."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def load_record_data(record_path: Path) -> dict[str, Any]:
    """Read voice.yaml as a mapping; any failure is a ConsentError (no record, no clone)."""
    try:
        data = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise ConsentError(f"Voice record {record_path.name} is unreadable", hint=CONSENT_HINT) from e
    if not isinstance(data, dict):
        raise ConsentError(f"Voice record {record_path.name} is malformed", hint=CONSENT_HINT)
    return data


def parse_consent(data: dict[str, Any], voice_id: str) -> ConsentRecord:
    """Validate the consent section, naming failing fields but never their values."""
    try:
        return ConsentRecord.model_validate(data.get("consent"))
    except ValidationError as e:
        fields = ", ".join(sorted({".".join(str(p) for p in err["loc"]) or "consent" for err in e.errors()}))
        raise ConsentError(
            f"Consent record for voice '{voice_id}' is incomplete or invalid ({fields})", hint=CONSENT_HINT
        ) from e


def reference_path(record_path: Path, data: dict[str, Any]) -> Path:
    """Locate the original clip next to voice.yaml; names that escape the directory are refused."""
    name = data.get("reference")
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise ConsentError("Voice record has no valid reference clip name", hint=CONSENT_HINT)
    return record_path.parent / name


def verify_record(record_path: Path, voice_id: str, clip_hash: str | None) -> ConsentRecord:
    """Check consent and that the reference clip still matches the expected hash."""
    data = load_record_data(record_path)
    if data.get("id") != voice_id:
        raise ConsentError(f"Voice record does not belong to voice '{voice_id}'", hint=CONSENT_HINT)
    consent = parse_consent(data, voice_id)
    clip = reference_path(record_path, data)
    try:
        actual = file_sha256(clip)
    except OSError as e:
        raise ConsentError(f"Reference clip for voice '{voice_id}' is missing", hint=CONSENT_HINT) from e
    if clip_hash is None or actual != clip_hash or actual != data.get("clip_hash"):
        raise ConsentError(
            f"Reference clip for voice '{voice_id}' changed since consent was recorded",
            hint="Re-register it with `mr-audio-smith voice add <id> ... --replace`.",
        )
    return consent


def require_consent(voice: VoiceRef) -> None:
    """Raise ConsentError unless a cloned voice has a valid, untampered consent record."""
    if voice.builtin:
        return
    if voice.record_path is None:
        raise ConsentError(f"Voice '{voice.id}' has no consent record; cloning refused", hint=CONSENT_HINT)
    verify_record(voice.record_path, voice.id, voice.clip_hash)
