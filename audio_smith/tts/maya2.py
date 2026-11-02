"""Maya 2 Native backend (ARCHITECTURE 6.6, ADR-003/004/016).

Talks to the maya3 server over its OpenAI-style API, or runs the model in-process when
AUDIO_SMITH_MAYA2_MODE=inproc. Cloned voices need a consent record and are registered once
per clip hash. The server only accepts speed 1.0, so rate is applied afterwards with atempo.
"""

import base64
import hashlib
import importlib
from typing import Any

import httpx
import numpy as np

from audio_smith.config import Settings
from audio_smith.errors import SynthesisError, UsageError
from audio_smith.preflight import PreflightIssue
from audio_smith.tts.base import Capabilities, PcmAudio, SynthParams, VoiceRef
from audio_smith.tts.openai_compat import OpenAICompatBackend
from audio_smith.tts.rate import apply_rate
from audio_smith.voices.consent import require_consent

MAYA2_MODEL = "maya3"
MAYA2_CKPT = "maya-research/maya2-native"
MAYA2_LANGUAGES = ["as", "bn", "en", "gu", "hi", "kn", "ml", "mr", "or", "pa", "ta", "te"]
MAYA2_VOICES = [
    "Ahana", "Vaidehi", "Malini", "Charvi", "Jahnavi", "Anirban", "Nakul", "Vasant", "Siddhant", "Satvik",
    "Abhay", "Nivedita", "Ishwari", "Ritvik", "Vrinda", "Sreekar", "Kayal", "Shaunak", "Akshat", "Tanushree",
]  # fmt: skip
MAYA2_SAMPLE_RATE = 24_000
MAYA2_MAX_CHARS = 400
SERVER_SPEED = 1.0
HASH_PREFIX_LEN = 8
HTTP_TIMEOUT_S = 30.0
HEALTH_TIMEOUT_S = 5.0
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
HTTP_LOADING = 503
LAUNCH_CMD = f"python -m maya3.server --ckpt {MAYA2_CKPT} --host 127.0.0.1 --port 8080"
INSTALL_HINT = (
    'uv pip install "maya3 @ git+https://github.com/MayaResearch/maya2-native'
    '@79142d835fc745537fc5ab71a007eba8f425c74c"'
)


class Maya2Backend(OpenAICompatBackend):
    """Maya 2 over HTTP (default) or in-process."""

    def __init__(self, *, base_url: str, mode: str = "http", **kwargs: Any) -> None:
        caps = Capabilities(
            languages=MAYA2_LANGUAGES,
            cloning=True,
            builtin_voices=MAYA2_VOICES,
            sample_rate=MAYA2_SAMPLE_RATE,
            max_chars=MAYA2_MAX_CHARS,
            streaming=True,
            license="Apache-2.0",
            commercial_ok=True,
        )
        super().__init__(
            base_url=base_url,
            api_key=None,
            model=MAYA2_MODEL,
            backend_id="maya2",
            capabilities=caps,
            **kwargs,
        )
        self._mode = mode
        self._registered: set[str] = set()
        self._engine: Any = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "Maya2Backend":
        return cls(base_url=settings.maya2_url, mode=settings.maya2_mode)

    @property
    def root(self) -> str:
        """Server root: the configured URL without its trailing /v1."""
        return self.base_url.removesuffix("/v1")

    # Hooks -----------------------------------------------------------------------------

    def map_params(self, params: SynthParams) -> dict[str, Any]:
        body: dict[str, Any] = {
            "language": params.lang,
            "normalize": params.normalize,
            "speed": SERVER_SPEED,
            "seed": params.seed,
            "temperature": params.temperature,
            "top_k": params.top_k,
            "top_p": params.top_p,
            "repetition_penalty": params.repetition_penalty,
        }
        return {k: v for k, v in body.items() if v is not None}

    def map_voice(self, voice: VoiceRef) -> str:
        if voice.builtin:
            return voice.id
        require_consent(voice)
        return self._ensure_registered(voice)

    # Synthesis -------------------------------------------------------------------------

    def synth(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        if params.lang not in MAYA2_LANGUAGES:
            raise UsageError(
                f"Maya 2 does not support language {params.lang!r}",
                hint=f"Supported languages: {', '.join(MAYA2_LANGUAGES)}",
            )
        if self._mode == "inproc":
            pcm = self._synth_inproc(self.map_text(text), voice, params)
        else:
            pcm = super().synth(text, voice, params)
        return apply_rate(pcm, params.rate)

    # Voice registration ----------------------------------------------------------------

    def _ensure_registered(self, voice: VoiceRef) -> str:
        if voice.reference_wav is None:
            raise SynthesisError(
                f"Cloned voice {voice.id!r} has no reference audio", hint="Re-register the voice."
            )
        audio = voice.reference_wav.read_bytes()
        clip_hash = voice.clip_hash or hashlib.sha256(audio).hexdigest()
        voice_id = f"as-{voice.id}-{clip_hash[:HASH_PREFIX_LEN]}"
        if voice_id in self._registered:
            return voice_id
        if self._mode == "inproc":
            self._load_engine().register_voice(
                voice_id, str(voice.reference_wav), voice.reference_text, voice.lang
            )
        else:
            self._register_http(voice_id, audio, voice)
        self._registered.add(voice_id)
        return voice_id

    def _register_http(self, voice_id: str, audio: bytes, voice: VoiceRef) -> None:
        payload = {
            "voice_id": voice_id,
            "ref_audio_b64": base64.b64encode(audio).decode("ascii"),
            "ref_text": voice.reference_text,
            "lang": voice.lang,
            "mode": "icl_spk" if voice.reference_text else "spk",
            "replace": False,
        }
        try:
            resp = httpx.post(f"{self.root}/v1/voices", json=payload, timeout=HTTP_TIMEOUT_S)
        except httpx.HTTPError as e:
            raise SynthesisError(
                f"Voice registration failed: {e}", hint=f"Is the server up? {LAUNCH_CMD}"
            ) from e
        if resp.status_code in (HTTP_OK, HTTP_CREATED, HTTP_CONFLICT) or "exists" in resp.text.lower():
            return
        raise SynthesisError(
            f"Voice registration rejected ({resp.status_code}): {resp.text[:200]}",
            hint="Check the reference clip and transcript.",
        )

    # In-process mode -------------------------------------------------------------------

    def _load_engine(self) -> Any:
        if self._engine is None:
            try:
                maya3 = importlib.import_module("maya3")
            except ImportError as e:
                raise SynthesisError("The maya3 package is not installed", hint=INSTALL_HINT) from e
            self._engine = maya3.Maya3TTS.from_pretrained(MAYA2_CKPT, max_seats=1)
        return self._engine

    def _synth_inproc(self, text: str, voice: VoiceRef, params: SynthParams) -> PcmAudio:
        name = self.map_voice(voice)
        out = self._load_engine().generate(text, params.lang, name)
        return PcmAudio(samples=np.asarray(out, dtype=np.float32), sample_rate=MAYA2_SAMPLE_RATE)

    # Preflight -------------------------------------------------------------------------

    def preflight(self) -> list[PreflightIssue]:
        if self._mode == "inproc":
            return self._preflight_inproc()
        try:
            resp = httpx.get(f"{self.root}/health", timeout=HEALTH_TIMEOUT_S)
        except httpx.HTTPError:
            return [
                PreflightIssue(
                    severity="error",
                    code="maya2.unreachable",
                    message=f"Maya 2 server not reachable at {self.root}",
                    hint=f"Start it with: {LAUNCH_CMD}",
                )
            ]
        if resp.status_code == HTTP_LOADING:
            return [
                PreflightIssue(
                    severity="error",
                    code="maya2.loading",
                    message="Maya 2 server is up but not ready",
                    hint="model is still loading; retry in a minute.",
                )
            ]
        return []

    def _preflight_inproc(self) -> list[PreflightIssue]:
        try:
            importlib.import_module("maya3")
        except ImportError:
            return [
                PreflightIssue(
                    severity="error",
                    code="maya2.package_missing",
                    message="In-process mode needs the maya3 package",
                    hint=INSTALL_HINT,
                )
            ]
        return []
