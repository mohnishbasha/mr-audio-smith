"""Kokoro-82M backend: in-process CPU fallback (ARCHITECTURE 6.5, ADR-014, ADR-017).

Kokoro is small and runs on CPU, so it is the fallback when no Maya 2 server or GPU is
available. It cannot clone voices; only its built-in voices are accepted. The `kokoro`
package is imported lazily so this module loads without the optional extra installed.
"""

import hashlib
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

from audio_smith.config import Settings
from audio_smith.errors import PreflightError, SynthesisError, UsageError
from audio_smith.preflight import PreflightIssue
from audio_smith.tts.base import Capabilities, PcmAudio, SynthParams, VoiceRef, to_float32

KOKORO_REPO = "hexgrad/Kokoro-82M"
SAMPLE_RATE = 24_000
MAX_CHARS = 400
PY_LIMIT = (3, 13)
HASH_CHUNK = 1 << 20
INSTALL_HINT = 'uv tool install "mr-audio-smith[kokoro]"'
LANG_CODES = {"a": "a", "b": "b", "h": "h"}
DEFAULT_VOICES = {"en": "am_michael", "hi": "hm_omega"}
KOKORO_VOICES = [
    "am_michael", "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_onyx", "am_puck", "am_santa",
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore", "af_nicole", "af_nova",
    "af_river", "af_sarah", "af_sky",
    "bm_george", "bm_daniel", "bm_fable", "bm_lewis", "bf_emma", "bf_alice", "bf_isabella", "bf_lily",
    "hm_omega", "hm_psi", "hf_alpha", "hf_beta",
]  # fmt: skip


def verify_weights(path: Path, expected_sha256: str) -> None:
    """Raise when a local weights file does not match its pinned checksum.

    Why: a tampered or truncated model file must never reach inference.
    """
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(HASH_CHUNK):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected_sha256.lower():
        issue = PreflightIssue(
            severity="error",
            code="kokoro_weights_checksum",
            message=f"Kokoro weights checksum mismatch for {path.name}",
            hint="Delete the file and download it again from hexgrad/Kokoro-82M.",
        )
        raise PreflightError(issue.message, hint=issue.hint, issues=[issue])


def _kokoro_importable() -> bool:
    try:
        import kokoro  # noqa: F401, PLC0415
    except ImportError:
        return False
    return True


class KokoroBackend:
    id = "kokoro"
    model = KOKORO_REPO

    def __init__(self, weights_path: Path | None = None, expected_sha256: str | None = None) -> None:
        self._weights_path = weights_path
        self._expected_sha256 = expected_sha256
        self._pipelines: dict[str, Any] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "KokoroBackend":
        """Build from settings; Kokoro needs no settings today, weights come from Hugging Face."""
        del settings
        return cls()

    def capabilities(self) -> Capabilities:
        return Capabilities(
            languages=["en", "hi"],
            cloning=False,
            builtin_voices=list(KOKORO_VOICES),
            sample_rate=SAMPLE_RATE,
            max_chars=MAX_CHARS,
            streaming=False,
            license="Apache-2.0",
            commercial_ok=True,
        )

    def preflight(self) -> list[PreflightIssue]:
        issues: list[PreflightIssue] = []
        if not _kokoro_importable():
            hint = INSTALL_HINT
            if sys.version_info >= PY_LIMIT:
                hint = (
                    "Kokoro needs Python 3.12 (ADR-017); run: "
                    "uv tool install --python 3.12 'mr-audio-smith[kokoro]'"
                )
            issues.append(
                PreflightIssue(
                    severity="error",
                    code="kokoro_missing",
                    message="The kokoro package is not installed",
                    hint=hint,
                )
            )
        if shutil.which("espeak-ng") is None:
            issues.append(
                PreflightIssue(
                    severity="warning",
                    code="espeak_missing",
                    message="espeak-ng not found on PATH (needed for Kokoro phonemes)",
                    hint="brew install espeak-ng (macOS) or apt install espeak-ng (Debian/Ubuntu)",
                )
            )
        if self._weights_path is not None and self._expected_sha256:
            issues.extend(self._weights_issues())
        return issues

    def _weights_issues(self) -> list[PreflightIssue]:
        assert self._weights_path is not None and self._expected_sha256 is not None  # noqa: S101
        try:
            verify_weights(self._weights_path, self._expected_sha256)
        except PreflightError as exc:
            return [i for i in exc.issues if isinstance(i, PreflightIssue)]
        except OSError as exc:
            return [PreflightIssue(severity="error", code="kokoro_weights_unreadable", message=str(exc))]
        return []

    def _voice_name(self, voice: VoiceRef) -> str:
        if voice.builtin and voice.id in KOKORO_VOICES:
            return voice.id
        raise UsageError(
            f"Kokoro cannot clone or use voice {voice.id!r}",
            hint=f"Use one of the built-in voices: {', '.join(KOKORO_VOICES)}",
        )

    def _pipeline(self, lang_code: str) -> Any:
        if lang_code not in self._pipelines:
            try:
                from kokoro import KPipeline  # noqa: PLC0415
            except ImportError as exc:
                raise SynthesisError("The kokoro package is not installed", hint=INSTALL_HINT) from exc
            self._pipelines[lang_code] = KPipeline(lang_code=lang_code, repo_id=KOKORO_REPO)
        return self._pipelines[lang_code]

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        name = self._voice_name(voice)
        pipeline = self._pipeline(LANG_CODES[name[0]])
        chunks: list[Any] = []
        for _graphemes, _phonemes, audio in pipeline(text, voice=name, speed=params.rate):
            if audio is not None:
                chunks.append(np.asarray(audio, dtype=np.float32).reshape(-1))
        if not chunks:
            raise SynthesisError("Kokoro returned no audio", hint="Check the input text is speakable.")
        samples = to_float32(np.concatenate(chunks))
        return PcmAudio(samples=samples, sample_rate=SAMPLE_RATE)
